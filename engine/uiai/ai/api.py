"""Anthropic API backend (design doc 10): calls the Messages API directly with ANTHROPIC_API_KEY.

Chosen with `uiai run --backend api`. Unlike `claude -p`, the conversation is rebuilt on every call:
earlier turns keep their text (the engine's messages and the AI's replies), but only the last
KEEP_IMAGES screenshots are sent; older ones are replaced by a short note. The input therefore grows by
text only, and the part that stays the same in the next call is cached (prompt caching).

- Model aliases follow Claude Code's (checked on 2026-11-12 with `claude -p --model haiku|sonnet`).
  Other names are sent as they are, so a full model ID also works.
- Thinking is left at the API's default for the model. Claude Code may think differently; the effect
  on speed and accuracy has not been measured.
- Standard library only (urllib), so the engine needs no extra dependency.
- One call, retries included, ends within `timeout` seconds (like ClaudeCodeSession). Every failure
  becomes an AIError, with the key masked, so the loop records it as an execution error.

Not yet run against the real API (no API key at hand); the tests use a fake transport.
"""

from __future__ import annotations

import base64
import http.client
import json
import math
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from . import AIError

API_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
MODEL_ALIASES = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
KEEP_IMAGES = 2          # screenshots sent as images: the current one and the one before
# Replies are ~200 tokens of JSON plus any thinking (300-700 tokens through Claude Code). 8192 leaves
# ample room and also fits models whose output limit is 8192; a model with a lower limit is rejected (400).
MAX_TOKENS = 8192
RETRY_STATUS = {408, 429, 500, 502, 503, 504, 529}
MAX_RETRIES = 3
MAX_RETRY_WAIT = 60.0
OMITTED = "(earlier screenshot, no longer shown)"
EMPTY_REPLY = "(empty reply)"

# post(url, headers, body, timeout) -> (status, response headers, response body)
Post = Callable[[str, dict, bytes, float], "tuple[int, dict, bytes]"]


class TransportError(Exception):
    """The request got no complete HTTP response (connection refused or reset, DNS, timeout, cut off).
    retry=False for what another attempt cannot fix (a malformed URL, a certificate that fails to verify)."""

    def __init__(self, message: str, retry: bool = True):
        super().__init__(message)
        self.retry = retry


def resolve_model(name: str) -> str:
    """The model ID sent for `name`: an alias from MODEL_ALIASES, or the name as it is."""
    return MODEL_ALIASES.get(name, name)


def load_key(value: str | None = None) -> str:
    """The API key (`value`, else ANTHROPIC_API_KEY) without surrounding whitespace. AIError, without the
    key in the message, if there is none or it cannot go in a header (urllib would show it in its error)."""
    key = (value if value is not None else os.environ.get("ANTHROPIC_API_KEY", "")).strip()
    if not key:
        raise AIError("環境変数 ANTHROPIC_API_KEY がない（--backend api に必要）")
    if not all(33 <= ord(ch) <= 126 for ch in key):
        raise AIError("ANTHROPIC_API_KEY に使えない文字（空白・改行・ASCII 以外の文字）が入っている")
    return key


def check_base_url(value: str | None = None) -> str:
    """The base URL (`value`, else ANTHROPIC_BASE_URL, else the API's), checked: AIError if unusable."""
    base = (value or os.environ.get("ANTHROPIC_BASE_URL") or "").strip() or API_URL  # blank is unset
    # The value is never shown in a message: it may carry a token (in the query, or as user:password@).
    if "@" in base:  # urllib cannot use credentials in the URL
        raise AIError("ANTHROPIC_BASE_URL にユーザー名・パスワードは入れられない")
    try:
        u = urllib.parse.urlsplit(base)
        ok = u.scheme in ("http", "https") and bool(u.hostname) and (u.port or 0) >= 0  # .port checks the number
    except ValueError:
        ok = False
    if not ok:
        raise AIError("ANTHROPIC_BASE_URL は http:// か https:// で始まる URL にする（値は表示しない）")
    return base.rstrip("/")


def check_config() -> None:
    """What ApiSession needs from the environment (key, base URL): AIError, naming every problem, if it is
    not usable. `uiai run` calls it before anything starts, so a bad setting stops the run once."""
    problems = []
    for check in (load_key, check_base_url):
        try:
            check()
        except AIError as e:
            problems.append(str(e))
    if problems:
        raise AIError("。".join(problems))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A 3xx comes back as it is: following it would send the key to wherever Location points."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _urllib_post(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        try:
            # Built per request: it reads the proxy settings from the environment as they are now
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
                return r.status, dict(r.headers.items()), r.read()
        except urllib.error.HTTPError as e:  # before the outer OSError: it is a subclass of URLError
            return e.code, dict(e.headers.items()) if e.headers else {}, e.read()
    except (OSError, http.client.HTTPException) as e:  # URLError, timeouts, resets; IncompleteRead, BadStatusLine
        reason = getattr(e, "reason", None) or e
        fixed = isinstance(reason, ssl.SSLCertVerificationError) or isinstance(e, http.client.InvalidURL)
        raise TransportError(str(reason) or type(e).__name__, retry=not fixed) from e


def urllib_post(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, dict, bytes]:
    """POST that ends within `timeout` seconds in all. urllib's own timeout applies to each socket
    operation, so a slowly trickling response could run far past it; the request runs in a thread
    instead, and one still running at the deadline is left to end on its own."""
    done: dict = {}

    def run() -> None:
        try:
            done["result"] = _urllib_post(url, headers, body, timeout)
        except BaseException as e:  # noqa: BLE001 — handed to the caller
            done["error"] = e

    th = threading.Thread(target=run, daemon=True, name="uiai-api")
    th.start()
    th.join(timeout)
    if th.is_alive():
        raise TransportError(f"{timeout:.0f} 秒以内に応答が終わらない")
    if "error" in done:
        raise done["error"]
    return done["result"]


def _error_message(raw: bytes) -> str:
    """Not shortened: the caller masks the key first, then shortens (a cut key would escape the mask)."""
    try:
        err = json.loads(raw)["error"]
        return f"{err.get('type', '')}: {err.get('message', '')}"
    except (ValueError, KeyError, TypeError, AttributeError):
        return raw[:65536].decode("utf-8", "replace")


def _retry_after(headers: dict) -> float | None:
    """`headers` with lowercase names."""
    try:
        f = float(headers.get("retry-after", ""))
    except ValueError:
        return None
    return min(max(f, 0.0), MAX_RETRY_WAIT) if math.isfinite(f) else None


def _count(v: object) -> int:
    return v if isinstance(v, int) else 0


def _image(jpeg: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(jpeg).decode()}}


class ApiSession:
    """Same interface as ClaudeCodeSession: ask(text, image) -> (reply, meta), close()."""

    backend = "api"

    def __init__(self, model: str, system: str, timeout: float = 120.0, *, api_key: str | None = None,
                 base_url: str | None = None, post: Post | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        key = load_key(api_key)
        self.url = check_base_url(base_url) + "/v1/messages"
        self.model_id = resolve_model(model)  # recorded in the result (loop.open_session)
        self.system = system
        self.timeout = timeout
        self._key = key
        self._headers = {"content-type": "application/json", "x-api-key": key, "anthropic-version": API_VERSION}
        self._post = post or urllib_post
        self._sleep = sleep
        self._clock = clock
        # Earlier calls: (text, screenshot, reply). The screenshot is None if the turn had none. Only the last
        # KEEP_IMAGES keep their bytes; older ones become b"" (it had one, which is no longer sent).
        self.turns: list[tuple[str, bytes | None, str]] = []

    def request(self, text: str, image: bytes | None) -> dict:
        """The request body for one more turn (the earlier turns, then this one)."""
        turns: list[tuple[str, bytes | None, str | None]] = [*self.turns, (text, image, None)]
        shown = [i for i, t in enumerate(turns) if t[1] is not None][-KEEP_IMAGES:]
        messages: list[dict] = []
        for i, (t, img, reply) in enumerate(turns):
            content = []
            if img is not None:  # the turn had a screenshot; it is sent only if among the last ones (and kept)
                content.append(_image(img) if i in shown and img else {"type": "text", "text": OMITTED})
            content.append({"type": "text", "text": t})
            messages.append({"role": "user", "content": content})
            if reply is not None:
                messages.append({"role": "assistant", "content": [{"type": "text", "text": reply}]})
        # Cache breakpoint at the end of the part that the next call sends unchanged: everything before
        # the first turn still sent with its screenshot (that screenshot is dropped in a later call).
        stable = (shown[0] if shown else len(turns) - 1) - 1
        if stable >= 0:
            messages[2 * stable + 1]["content"][-1]["cache_control"] = {"type": "ephemeral"}
        return {"model": self.model_id, "max_tokens": MAX_TOKENS,
                "system": [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
                "messages": messages}

    def ask(self, text: str, image: bytes | None = None) -> tuple[str, dict]:
        # "replace": a stray lone surrogate in the text must not raise outside the error handling below
        body = json.dumps(self.request(text, image), ensure_ascii=False).encode("utf-8", "replace")
        start = self._clock()
        deadline = start + self.timeout
        problem = ""
        for attempt in range(MAX_RETRIES + 1):
            wait = None
            t0 = self._clock()
            try:
                status, headers, raw = self._post(self.url, self._headers, body, max(deadline - t0, 0.1))
            except TransportError as e:
                problem = f"API に接続できない: {self._mask(str(e))}"
                if not e.retry:
                    raise AIError(problem) from None
            except Exception as e:  # noqa: BLE001 — anything else would escape the loop (and could show the key)
                raise AIError(f"API を呼び出せない（{type(e).__name__}）: {self._mask(str(e))[:300]}") from None
            else:
                if status == 200:
                    return self._done(text, image, raw, start, self._clock() - t0)
                headers = {k.lower(): v for k, v in headers.items()}
                problem = f"API がエラーを返した（{status}）: {self._mask(_error_message(raw))[:300]}"
                if 300 <= status < 400:
                    location = self._mask(headers.get("location", ""))[:200]
                    problem = (f"API がリダイレクトを返した（{status}。転送先: {location or '不明'}）。"
                               "キーを別の宛先に送らないため従わない。ANTHROPIC_BASE_URL を確かめる")
                if status not in RETRY_STATUS:
                    raise AIError(problem)
                wait = _retry_after(headers)
            if attempt == MAX_RETRIES:
                break
            pause = wait if wait is not None else float(2 ** attempt)
            if self._clock() + pause >= deadline:
                raise AIError(f"{problem}（やり直しても {self.timeout:.0f} 秒以内に応答が得られない）")
            self._sleep(pause)
        raise AIError(f"{problem}（{MAX_RETRIES} 回やり直してもだめだった）")

    def _mask(self, s: str) -> str:
        return s.replace(self._key, "****")

    def _shown(self, raw: bytes) -> str:
        """The start of a response body for an error message: key masked before it is shortened."""
        return repr(self._mask(raw[:65536].decode("utf-8", "replace"))[:200])

    def _done(self, text: str, image: bytes | None, raw: bytes, start: float, api_s: float) -> tuple[str, dict]:
        try:
            res = json.loads(raw)
        except ValueError:
            raise AIError(f"API の応答を読めない: {self._shown(raw)}") from None
        content = res.get("content") if isinstance(res, dict) else None
        if not isinstance(content, list):
            raise AIError(f"API の応答の形が想定と違う: {self._shown(raw)}")
        # Not a normal reply: say so (an execution error) rather than hand on a broken or empty one, which the
        # loop would take for an unreadable answer and record as a failure of the app under test.
        stop = res.get("stop_reason")
        if stop == "max_tokens":
            raise AIError(f"AI の出力が上限（max_tokens = {MAX_TOKENS}）に達して途中で切れた")
        if stop == "refusal":
            raise AIError("AI が応答を拒否した（stop_reason: refusal）")
        if stop == "model_context_window_exceeded":
            raise AIError("会話がモデルの入力の上限を超えた（stop_reason: model_context_window_exceeded）")
        reply = "".join(c["text"] for c in content
                        if isinstance(c, dict) and c.get("type") == "text" and isinstance(c.get("text"), str))
        # The reply goes back into the next request, where an empty or whitespace-only text block would
        # be rejected.
        self.turns.append((text, image, reply.strip() or EMPTY_REPLY))
        for i in [i for i, t in enumerate(self.turns) if t[1]][:-KEEP_IMAGES]:
            self.turns[i] = (self.turns[i][0], b"", self.turns[i][2])
        usage = res.get("usage") if isinstance(res.get("usage"), dict) else {}
        return reply, {
            "wall_s": round(self._clock() - start, 2),
            "api_s": round(api_s, 2),
            "in_tokens": _count(usage.get("input_tokens")) + _count(usage.get("cache_read_input_tokens"))
            + _count(usage.get("cache_creation_input_tokens")),
            "out_tokens": _count(usage.get("output_tokens")),
        }

    def close(self) -> None:
        """Nothing to stop: every call is a separate HTTP request."""
