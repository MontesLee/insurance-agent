"""28.K.28 Chat E2E latency benchmark driver (instrumentation phase).

Drives the REAL chat pipeline on the live backend exactly the way the
browser does — one fresh chat per run, POST the message, then tail the
SSE stream to the terminal event — and records CLIENT-side timings:

    t0              just before POST /messages (user submit)
    ack_ms          HTTP 201 received (run registered)
    first_event_ms  first SSE runtime event arrival (any)
    first_content   first agent_stream_delta kind=content arrival
    first_reasoning first agent_stream_delta kind=reasoning arrival
    terminal_ms     run_completed / run_failed arrival

Cases A-E, N runs each, SEQUENTIAL (no parallel load: we are measuring
latency, not throughput; burst-parallel would trip provider rate limits
and skew every number). Client JSON per run -> tmp/obs/perf-bench/.

Keys come from tmp/_relaunch.env (never printed, never committed).
Usage:  python tools/perf/benchmark_chat.py [--base http://127.0.0.1:8123]
                                        [--runs 3] [--cases A,B,C,D,E]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "tmp", "obs", "perf-bench")
KEYS_FILE = os.path.join(ROOT, "tmp", "pilot-keys", "api_keys.env")

CASES = {
    "A": "百万医疗险和重疾险有什么区别？",
    "B": "帮我解释一下百万医疗险的免赔额和续保条件是怎么规定的。",
    "C": "我们一家三口，我35岁月入2万有社保，妻子32岁有社保，孩子3岁，"
         "想看看家庭保障有什么明显缺口，应该怎么配置？",
    "D": "我是35岁男性，已婚，有一个3岁的孩子，家庭年收入30万，还有房贷"
         "100万，我和妻子都只有社保，没有任何商业保险。请给我做一份完整的"
         "家庭保障规划分析，包括风险分析、保障缺口识别和具体的保障配置"
         "建议，并生成规划报告。",
    "E": "请详细对比分析百万医疗险、重疾险和惠民保三种产品在保障责任、"
         "免赔额、续保条件和适用人群方面的区别，尽量详细完整。",
}

TERMINAL = ("run_completed", "run_failed")
RUN_ID_RE = re.compile(r"run_[0-9a-f]+")


def load_key() -> str:
    """probe-alpha consumer key from the pilot key file (quiet)."""
    with open(KEYS_FILE, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if s.startswith("export "):
                s = s[len("export "):].strip()
            if not s.startswith("INSURANCE_AGENT_API_KEYS="):
                continue
            val = s.split("=", 1)[1].strip().strip("'\"")
            for part in val.split(","):
                seg = part.split(":")
                if len(seg) == 3 and seg[1] == "CONSUMER" \
                        and seg[2] == "probe-alpha":
                    return seg[0]
    raise SystemExit("probe-alpha key not found in tmp/pilot-keys/"
                     "api_keys.env")


def run_one(client: httpx.Client, key: str, case_id: str, text: str,
            idx: int) -> dict:
    chat = client.post("/api/chats", headers={
        "Authorization": "Bearer %s" % key}).json()
    chat_id = chat["chat_id"]

    rec: dict = {"case": case_id, "run_index": idx,
                 "submit_wall": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                              time.gmtime())}
    t0 = time.perf_counter()
    ack = client.post("/api/chats/%s/messages" % chat_id,
                      headers={"Authorization": "Bearer %s" % key},
                      json={"text": text})
    rec["ack_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    if ack.status_code != 200:
        rec["error"] = "post %s: %s" % (ack.status_code, ack.text[:120])
        return rec
    run_id = ack.json()["run_id"]
    rec["run_id"] = run_id

    url = "/api/runs/%s/stream?key=%s" % (run_id, key)
    first_event = first_content = first_reasoning = terminal = None
    deltas = keepalives = events = 0
    status = result_status = None
    t_read0 = time.perf_counter()
    with client.stream("GET", url, headers={
            "Authorization": "Bearer %s" % key},
            timeout=httpx.Timeout(connect=10.0, read=960.0,
                                  write=30.0, pool=10.0)) as resp:
        if resp.status_code != 200:
            rec["error"] = "stream %s" % resp.status_code
            return rec
        now = lambda: round((time.perf_counter() - t0) * 1000.0, 1)  # noqa: E731
        data_buf = ""

        def _dispatch(payload: str) -> bool:
            """Returns True when the terminal event was seen."""
            nonlocal first_event, first_content, first_reasoning
            nonlocal terminal, status, result_status, events, deltas
            try:
                ev = json.loads(payload)
            except ValueError:
                return False
            et = ev.get("event_type")
            if et == "agent_stream_delta":
                deltas += 1
                k = (ev.get("data") or {}).get("kind")
                if k == "content" and first_content is None:
                    first_content = now()
                if k == "reasoning" and first_reasoning is None:
                    first_reasoning = now()
                return False
            events += 1
            if first_event is None:
                first_event = now()
            if et in TERMINAL:
                terminal = now()
                status = ev.get("status")
                result_status = (ev.get("data") or {}).get("result_status")
                return True
            return False

        for line in resp.iter_lines():
            if line == "":                       # SSE event delimiter
                if data_buf:
                    if _dispatch(data_buf):
                        break
                    data_buf = ""
                continue
            if line.startswith(":"):
                keepalives += 1
                continue
            if line.startswith("data:"):
                data_buf = line[5:].strip()
                continue
            # `event:` / `id:` lines carry nothing we need here
    rec.update({
        "first_event_ms": first_event,
        "first_reasoning_delta_ms": first_reasoning,
        "first_content_delta_ms": first_content,
        "terminal_ms": terminal,
        "stream_events": events,
        "stream_deltas": deltas,
        "keepalives": keepalives,
        "status": status,
        "result_status": result_status,
        "read_elapsed_ms": round((time.perf_counter() - t_read0) * 1000, 1),
    })
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8123")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--cases", default="A,B,C,D,E")
    ap.add_argument("--out", default=None,
                    help="isolation: write client JSONs under this "
                         "sub-directory of the bench dir (28.K.31-A)")
    ap.add_argument("--gap-s", type=float, default=2.0,
                    help="pause between runs (provider friendliness)")
    args = ap.parse_args()

    key = load_key()
    out_dir = os.path.join(OUT_DIR, args.out) if args.out else OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    client = httpx.Client(base_url=args.base, timeout=30.0)

    health = client.get("/api/health").json()
    print("[bench] backend %s" % health.get("status"), flush=True)

    manifest = []
    for case_id in [c.strip().upper() for c in args.cases.split(",")]:
        text = CASES[case_id]
        for idx in range(1, args.runs + 1):
            print("[bench] case %s run %d/%d ..." % (
                case_id, idx, args.runs), flush=True)
            t_start = time.strftime("%H:%M:%S")
            rec = run_one(client, key, case_id, text, idx)
            rec["started_at"] = t_start
            tag = "%s_%d" % (case_id, idx)
            path = os.path.join(out_dir, "client_%s.json" % tag)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False, indent=1)
            manifest.append({"tag": tag, "path": path})
            print("[bench]   -> %s run=%s ack=%sms first_evt=%s "
                  "first_content=%s terminal=%s status=%s/%s" % (
                      tag, rec.get("run_id"), rec.get("ack_ms"),
                      rec.get("first_event_ms"),
                      rec.get("first_content_delta_ms"),
                      rec.get("terminal_ms"), rec.get("status"),
                      rec.get("result_status")), flush=True)
            time.sleep(args.gap_s)
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    print("[bench] done: %d runs" % len(manifest), flush=True)


if __name__ == "__main__":
    sys.exit(main())
