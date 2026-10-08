import { useEffect, useState } from "react";
import { api, ApiError, CONSUMER_KEY_STORAGE } from "../../api/client";
import { clearStoredChats, setChatStorageScope } from "../../state/chatState";

/**
 * IDENTITY GATE (28.G) — the minimal consumer identity surface.
 *
 * The stored credential is an authentication SECRET sent to the server;
 * the subject (and therefore conversation storage scoping) comes from the
 * SERVER's whoami response — never from client-supplied identity. In the
 * documented no-keys local-dev mode whoami answers local-dev and the chat
 * renders without a gate (frozen dev behavior). Switching identity never
 * shows the previous subject's transcripts (per-subject storage scope).
 */
export function IdentityGate({ onIdentity }: { onIdentity: () => void }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      localStorage.setItem(CONSUMER_KEY_STORAGE, value.trim());
      const who = await api.whoami();
      if (!who.subject) throw new Error("no subject");
      setChatStorageScope(who.subject);
      onIdentity();
    } catch (e) {
      localStorage.removeItem(CONSUMER_KEY_STORAGE);
      setError(
        e instanceof ApiError && e.status === 401
          ? "密钥无效或已失效。"
          : "暂时无法验证，请稍后再试。",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4" data-testid="identity-gate">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-[15px] font-semibold text-slate-800">保险顾问助手</p>
        <p className="mt-1 text-[12.5px] text-slate-500">
          请输入你的访问密钥开始使用（由服务方提供）。
        </p>
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !busy && void submit()}
          placeholder="访问密钥"
          className="mt-4 w-full rounded-lg border border-slate-200 px-3 py-2 text-[13px] outline-none focus:border-slate-400"
          data-testid="identity-key-input"
          aria-label="访问密钥"
        />
        {error ? <p className="mt-2 text-[12px] text-red-500">{error}</p> : null}
        <button
          type="button"
          disabled={busy || !value.trim()}
          onClick={() => void submit()}
          className="mt-3 w-full rounded-lg bg-slate-800 px-4 py-2 text-[13px] font-medium text-white disabled:opacity-40"
          data-testid="identity-submit"
        >
          {busy ? "验证中…" : "开始使用"}
        </button>
      </div>
    </div>
  );
}

/** Resolve the current identity; decides gate vs chat. `refresh` re-runs
 *  the resolution (e.g. after a key was submitted in the gate). */
export function useConsumerIdentity(): {
  state: "loading" | "gate" | "ready";
  subject: string | null;
  signOut: () => void;
  refresh: () => void;
} {
  const [state, setState] = useState<"loading" | "gate" | "ready">("loading");
  const [subject, setSubject] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    api.whoami()
      .then((who) => {
        if (!alive) return;
        setChatStorageScope(who.subject ?? "local");
        setSubject(who.subject);
        setState("ready");
      })
      .catch(() => {
        if (!alive) return;
        // unreachable server in dev mode → let the chat surface handle
        // connection errors; a 401 (keys mode, no/invalid key) gates
        // via the webui:unauthorized event below.
        setState((prev) => (prev === "gate" ? prev : "ready"));
      });
    const onUnauthorized = () => {
      if (!alive) return;
      setSubject(null);
      setState("gate");
    };
    window.addEventListener("webui:unauthorized", onUnauthorized);
    return () => {
      alive = false;
      window.removeEventListener("webui:unauthorized", onUnauthorized);
    };
  }, [nonce]);

  const signOut = () => {
    try {
      clearStoredChats(); // current subject's local transcripts
      localStorage.removeItem(CONSUMER_KEY_STORAGE);
    } catch { /* ignore */ }
    setChatStorageScope("local");
    setSubject(null);
    setState("gate");
  };

  return { state, subject, signOut, refresh: () => setNonce((n) => n + 1) };
}
