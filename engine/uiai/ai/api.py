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

Not yet run against the real API (no API key at hand); the tests use a fake transport.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from typing import Callable

from . import AIError

API_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
MODEL_ALIASES = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
KEEP_IMAGES = 2          # screenshots sent as images: the current one and the one before
MAX_TOKENS = 16000       # replies are ~200 tokens of JSON (plus any thinking); a low cap would cut them off
RETRY_STATUS = {408, 429, 500, 502, 503, 504, 529}
MAX_RETRIES = 3
MAX_RETRY_WAIT = 60.0
OMITTED = "(earlier screenshot, no longer shown)"
EMPTY_REPLY = "(empty reply)"

# post(url, headers, body, timeout) -> (status, response headers, response body)
Post = Callable[[str, dict, bytes, float], "tuple[int, dict, bytes]"]


class TransportError(Exception):
    """The request got no HTTP response (connection refused or reset, DNS, timeout)."""


def urllib_post(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:  # before URLError: it is a subclass
        return e.code, dict(e.headers.items()) if e.headers else {}, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise TransportError(str(getattr(e, "reason", e))) from e


def _error_message(raw: bytes) -> str:
    try:
        err = json.loads(raw)["error"]
        return f"{err.get('type', '')}: {err.get('message', '')}"[:300]
    except (ValueError, KeyError, TypeError, AttributeError):
        return raw[:300].decode("utf-8", "replace")


def _retry_after(headers: dict) -> float | None:
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return min(max(float(v), 0.0), MAX_RETRY_WAIT)
            except ValueError:
                return None
    return None


def _image(jpeg: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(jpeg).decode()}}


class ApiSession:
    """Same interface as ClaudeCodeSession: ask(text, image) -> (reply, meta), close()."""

    def __init__(self, model: str, system: str, timeout: float = 120.0, *, api_key: str | None = None,
                 base_url: str | None = None, post: Post | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise AIError("環境変数 ANTHROPIC_API_KEY がない（--backend api に必要）")
        self.model = MODEL_ALIASES.get(model, model)
        self.system = system
        self.timeout = timeout
        self._headers = {"content-type": "application/json", "x-api-key": key, "anthropic-version": API_VERSION}
        base = base_url or os.environ.get("ANTHROPIC_BASE_URL") or API_URL
        self.url = base.rstrip("/") + "/v1/messages"
        self._post = post or urllib_post
        self._sleep = sleep
        self.turns: list[tuple[str, bytes | None, str]] = []  # earlier calls: (text, screenshot, reply)

    def request(self, text: str, image: bytes | None) -> dict:
        """The request body for one more turn (the earlier turns, then this one)."""
        turns: list[tuple[str, bytes | None, str | None]] = [*self.turns, (text, image, None)]
        shown = [i for i, t in enumerate(turns) if t[1] is not None][-KEEP_IMAGES:]
        messages: list[dict] = []
        for i, (t, img, reply) in enumerate(turns):
            content = []
            if img is not None:
                content.append(_image(img) if i in shown else {"type": "text", "text": OMITTED})
            content.append({"type": "text", "text": t})
            messages.append({"role": "user", "content": content})
            if reply is not None:
                messages.append({"role": "assistant", "content": [{"type": "text", "text": reply}]})
        # Cache breakpoint at the end of the part that the next call sends unchanged: everything before
        # the first turn still sent with its screenshot (that screenshot is dropped in a later call).
        stable = (shown[0] if shown else len(turns) - 1) - 1
        if stable >= 0:
            messages[2 * stable + 1]["content"][-1]["cache_control"] = {"type": "ephemeral"}
        return {"model": self.model, "max_tokens": MAX_TOKENS,
                "system": [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
                "messages": messages}

    def ask(self, text: str, image: bytes | None = None) -> tuple[str, dict]:
        body = json.dumps(self.request(text, image), ensure_ascii=False).encode("utf-8")
        start = time.time()
        problem = ""
        for attempt in range(MAX_RETRIES + 1):
            wait = None
            t0 = time.time()
            try:
                status, headers, raw = self._post(self.url, self._headers, body, self.timeout)
            except TransportError as e:
                problem = f"API に接続できない: {e}"
            else:
                if status == 200:
                    return self._done(text, image, raw, start, time.time() - t0)
                problem = f"API がエラーを返した（{status}）: {_error_message(raw)}"
                if status not in RETRY_STATUS:
                    raise AIError(problem)
                wait = _retry_after(headers)
            if attempt < MAX_RETRIES:
                self._sleep(wait if wait is not None else float(2 ** attempt))
        raise AIError(f"{problem}（{MAX_RETRIES} 回やり直してもだめだった）")

    def _done(self, text: str, image: bytes | None, raw: bytes, start: float, api_s: float) -> tuple[str, dict]:
        try:
            res = json.loads(raw)
        except ValueError as e:
            raise AIError(f"API の応答を読めない: {raw[:200]!r}") from e
        reply = "".join(c.get("text", "") for c in res.get("content") or [] if c.get("type") == "text")
        # The reply goes back into the next request; an empty text block would be rejected there.
        self.turns.append((text, image, reply or EMPTY_REPLY))
        usage = res.get("usage") or {}
        return reply, {
            "wall_s": round(time.time() - start, 2),
            "api_s": round(api_s, 2),
            "in_tokens": (usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0),
            "out_tokens": usage.get("output_tokens") or 0,
        }

    def close(self) -> None:
        """Nothing to stop: every call is a separate HTTP request."""
