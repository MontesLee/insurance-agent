"""Incremental agent_decide message extraction — 28.K.29-A.

The planning agent loop's FINAL user-facing answer (and its ask_user
clarify question) arrives as the `message` argument of an
`agent_decide` tool call — i.e. as JSON tool-call ARGUMENT fragments on
the provider's streaming channel. The provider adapter forwards those
raw fragments (kind=tool_args); THIS module turns them into the
user-visible answer stream, incrementally, without waiting for the
arguments to complete:

    scan_decide(accumulated_raw) -> (action_so_far, message_raw_so_far)

Policy rules enforced by the CONSUMER (agent loop), not here:
  * only action in {finish, ask_user} may surface its message — a
    call_tool decision's message (when present) is internal;
  * every OTHER tool's arguments NEVER surface (raw args stay
    internal, spec §7).

The scanner is JSON-aware (string/escape state + depth) so a `"message"`
occurrence INSIDE another string value (e.g. inside `reason`) can never
be mistaken for the key. Truncated input is first-class: the message
value is returned up to the last complete character.
"""
from __future__ import annotations

from typing import Optional, Tuple

_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"',
                   "\\": "\\", "/": "/", "b": "\b", "f": "\f"}


def scan_decide(raw: str) -> Tuple[Optional[str], str]:
    """Scan (possibly incomplete) agent_decide arguments JSON text.

    Returns (action_value_so_far|None, message_raw_value_so_far).
    `message_raw` is the JSON string CONTENT between quotes, NOT yet
    unescaped — use visible_message() for that.
    """
    action: Optional[str] = None
    message = ""
    i, n = 0, len(raw)
    depth = 0
    in_str = False
    escape = False
    # key currently being read at depth 1 (outside strings)
    key_buf: list = []
    reading_key = False
    active_value = None          # "action" | "message" | None
    value_buf: list = []

    def _finish_value():
        nonlocal active_value, action, message
        if active_value == "action":
            action = "".join(value_buf)
        elif active_value == "message":
            message = "".join(value_buf)
        active_value = None
        value_buf.clear()

    while i < n:
        ch = raw[i]
        if in_str:
            if escape:
                escape = False
                if active_value is not None:
                    # keep the RAW escape (two chars) — unescaping is a
                    # separate, truncation-aware step
                    value_buf.append("\\" + ch)
                i += 1
                continue
            if ch == "\\":
                escape = True
                # the escape CHAR PAIR is appended by the next iteration
                # (or dropped as incomplete at the end of input)
                i += 1
                continue
            if ch == '"':
                in_str = False
                if active_value is not None:
                    _finish_value()
                elif reading_key:
                    key = "".join(key_buf)
                    reading_key = False
                    key_buf.clear()
                    if depth == 1 and key in ("action", "message"):
                        active_value = key
                i += 1
                continue
            if active_value is not None:
                value_buf.append(ch)
            elif reading_key:
                key_buf.append(ch)
            i += 1
            continue
        # outside a string
        if ch == '"':
            in_str = True
            # a string outside a value position at depth 1 = a KEY
            reading_key = (depth == 1 and active_value is None)
            i += 1
            continue
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            if active_value is not None and depth == 1:
                _finish_value()
            depth -= 1
            i += 1
            continue
        if ch == "," and active_value is not None and depth == 1:
            _finish_value()
        i += 1

    # truncated mid-value: expose what is safely complete
    if active_value is not None and value_buf:
        partial = "".join(value_buf)
        if active_value == "action":
            action = _drop_incomplete_escape(partial)
        else:
            message = _drop_incomplete_escape(partial)
    return action, message


def _drop_incomplete_escape(s: str) -> str:
    """A trailing lone backslash or partial \\u sequence cannot be
    completed yet — cut the value there (the next fragment completes
    it and the prefix-diff emitter picks the rest up)."""
    # odd number of trailing backslashes = the last one is unterminated
    trail = 0
    while trail < len(s) and s[len(s) - 1 - trail] == "\\":
        trail += 1
    if trail % 2 == 1:
        return s[:-1]
    # partial \uXXXX: a backslash-u with fewer than 4 hex digits at the
    # tail (not itself inside a complete escape pair)
    if len(s) >= 2 and s[-2] == "\\" and s[-1] == "u":
        return s[:-2]
    for ln in range(3, 6):     # \u + 1..3 hex digits at the tail
        tail = s[-ln:]
        if len(tail) == ln and tail[0] == "\\" and tail[1] == "u" \
                and all(c in "0123456789abcdefABCDEF" for c in tail[2:]):
            return s[:-ln]
    return s


def visible_message(message_raw: str) -> str:
    """Unescape a JSON string CONTENT (between quotes) with the same
    truncation rule: an incomplete trailing escape yields a value that
    stops just before it."""
    out: list = []
    i, n = 0, len(message_raw)
    while i < n:
        ch = message_raw[i]
        if ch == "\\":
            if i + 1 >= n:
                break                       # incomplete escape at the cut
            nxt = message_raw[i + 1]
            if nxt == "u":
                if i + 6 > n:
                    break                   # partial \uXXXX
                try:
                    out.append(chr(int(message_raw[i + 2:i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    i += 2
                    continue
            out.append(_SIMPLE_ESCAPES.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)
