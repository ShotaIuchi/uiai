"""Anthropic API backend (uiai/ai/api.py) against fake HTTP responses: request shape, the screenshot
window, prompt-cache breakpoints, usage, retries, errors, and a whole scenario through the loop."""

from __future__ import annotations

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uiai.ai import AIError  # noqa: E402
from uiai.ai import api  # noqa: E402
from uiai.ai.api import ApiSession, TransportError  # noqa: E402

KEY = "sk-test-0123456789"


def reply(text="{}", usage=None, content=None):
    body = {"type": "message", "role": "assistant", "stop_reason": "end_turn",
            "content": content if content is not None else [{"type": "text", "text": text}],
            "usage": usage or {"input_tokens": 10, "output_tokens": 5}}
    return 200, {"content-type": "application/json"}, json.dumps(body).encode()


def error(status, typ="api_error", msg="boom", headers=None):
    return status, headers or {}, json.dumps({"type": "error", "error": {"type": typ, "message": msg}}).encode()


class FakeTransport:
    """Answers with the scripted responses in order (a callable is called with the request body)."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, headers, body, timeout):
        req = json.loads(body)
        self.calls.append({"url": url, "headers": headers, "body": req, "timeout": timeout})
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r(req) if callable(r) else r

    def body(self, n=-1):
        return self.calls[n]["body"]


def session(transport, model="haiku", sleeps=None, **kw):
    return ApiSession(model, "SYSTEM", api_key=KEY, post=transport,
                      sleep=(sleeps.append if sleeps is not None else lambda s: None), **kw)


def kinds(message):
    return [c["type"] for c in message["content"]]


# ---------------------------------------------------------------------------- request


def test_request_carries_model_system_screenshot_and_key():
    t = FakeTransport(reply('{"ok": 1}'))
    text, meta = session(t).ask("screen 1", b"JPEG1")
    assert text == '{"ok": 1}'
    c = t.calls[0]
    assert c["url"] == "https://api.anthropic.com/v1/messages"
    assert c["headers"]["x-api-key"] == KEY and c["headers"]["anthropic-version"] == "2023-06-01"
    b = c["body"]
    assert b["model"] == "claude-haiku-5-5" and b["max_tokens"] == api.MAX_TOKENS
    assert b["system"] == [{"type": "text", "text": "SYSTEM", "cache_control": {"type": "ephemeral"}}]
    assert "thinking" not in b  # left at the API's default
    (m,) = b["messages"]
    assert m["role"] == "user" and kinds(m) == ["image", "text"]
    assert m["content"][0]["source"] == {"type": "base64", "media_type": "image/jpeg", "data": "SlBFRzE="}
    assert m["content"][1]["text"] == "screen 1"


@pytest.mark.parametrize("name,sent", [("haiku", "claude-haiku-5-5"), ("sonnet", "claude-sonnet-5-5"),
                                       ("claude-opus-5-5", "claude-opus-5-5"), ("my-model", "my-model")])
def test_aliases_are_resolved_and_other_names_sent_as_they_are(name, sent):
    t = FakeTransport(reply())
    session(t, model=name).ask("x")
    assert t.body()["model"] == sent


def test_base_url_from_the_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.local:8080/")
    t = FakeTransport(reply())
    session(t).ask("x")
    assert t.calls[0]["url"] == "http://proxy.local:8080/v1/messages"


def test_missing_key_is_an_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AIError, match="ANTHROPIC_API_KEY"):
        ApiSession("haiku", "SYSTEM", post=FakeTransport(reply()))


def test_key_from_the_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    t = FakeTransport(reply())
    ApiSession("haiku", "SYSTEM", post=t).ask("x")
    assert t.calls[0]["headers"]["x-api-key"] == "sk-env"


# ---------------------------------------------------------------------------- conversation


def test_only_the_last_two_screenshots_are_sent_and_every_reply_is_kept():
    t = FakeTransport(lambda req: reply(f"reply {len(req['messages']) // 2 + 1}")[:3])
    s = session(t)
    for i in range(1, 5):
        s.ask(f"screen {i}", f"JPEG{i}".encode())
    msgs = t.body()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"] * 3 + ["user"]
    assert [kinds(m) for m in msgs[0::2]] == [["text", "text"], ["text", "text"], ["image", "text"], ["image", "text"]]
    assert msgs[0]["content"][0]["text"] == api.OMITTED and msgs[0]["content"][1]["text"] == "screen 1"
    assert [m["content"][0]["text"] for m in msgs[1::2]] == ["reply 1", "reply 2", "reply 3"]
    assert msgs[6]["content"][1]["text"] == "screen 4"


def test_cache_breakpoint_sits_after_the_part_the_next_call_repeats():
    t = FakeTransport(reply())
    s = session(t)

    def marked(body):
        return [i for i, m in enumerate(body["messages"]) if any("cache_control" in c for c in m["content"])]

    s.ask("1", b"a")
    s.ask("2", b"b")
    assert marked(t.body(0)) == [] and marked(t.body(1)) == []  # turns 1 and 2 still carry their screenshots
    s.ask("3", b"c")
    assert marked(t.body()) == [1]  # the reply to turn 1, whose screenshot is now dropped
    s.ask("4", b"d")
    assert marked(t.body()) == [3]
    # The next call starts with the same content as the cached part (everything up to the marked reply).
    # The marker itself moves on each call; the cache matches the content, not where the marker is.
    def content(msgs):
        return json.dumps([{**m, "content": [{k: v for k, v in c.items() if k != "cache_control"}
                                             for c in m["content"]]} for m in msgs])

    assert content(t.body(2)["messages"][:2]) == content(t.body(3)["messages"][:2])


def test_a_text_only_turn_does_not_push_a_screenshot_out():
    """The loop asks again without a screenshot when a reply was not JSON."""
    t = FakeTransport(reply("not json"), reply("{}"), reply("{}"))
    s = session(t)
    s.ask("1", b"a")
    s.ask("again")
    s.ask("2", b"b")
    msgs = t.body()["messages"]
    assert [kinds(m) for m in msgs[0::2]] == [["image", "text"], ["text"], ["image", "text"]]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant", "user"]


def test_thinking_blocks_are_not_part_of_the_reply_and_usage_counts_cached_input():
    usage = {"input_tokens": 100, "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 300,
             "output_tokens": 42}
    t = FakeTransport(reply(usage=usage, content=[{"type": "thinking", "thinking": "hmm", "signature": "s"},
                                                  {"type": "text", "text": '{"a":'}, {"type": "text", "text": "1}"}]))
    s = session(t)
    text, meta = s.ask("x", b"j")
    assert text == '{"a":1}'
    assert meta["in_tokens"] == 2400 and meta["out_tokens"] == 42
    assert set(meta) == {"wall_s", "api_s", "in_tokens", "out_tokens"}
    s.ask("y")
    assert t.body()["messages"][1]["content"] == [{"type": "text", "text": '{"a":1}'}]


def test_an_empty_reply_is_returned_empty_but_kept_non_empty_in_the_history():
    t = FakeTransport(reply(content=[]), reply())
    s = session(t)
    assert s.ask("x")[0] == ""
    s.ask("y")
    assert t.body()["messages"][1]["content"][0]["text"] == api.EMPTY_REPLY


# ---------------------------------------------------------------------------- errors and retries


def test_overloaded_and_rate_limited_calls_are_retried_with_backoff_or_retry_after():
    sleeps: list[float] = []
    t = FakeTransport(error(529, "overloaded_error"), error(429, "rate_limit_error", headers={"Retry-After": "7"}),
                      reply("{}"))
    assert session(t, sleeps=sleeps).ask("x")[0] == "{}"
    assert sleeps == [1.0, 7.0]
    assert len(t.calls) == 3


def test_gives_up_after_the_retries():
    sleeps: list[float] = []
    t = FakeTransport(error(500))
    with pytest.raises(AIError, match=r"500.*3 回やり直しても"):
        session(t, sleeps=sleeps).ask("x")
    assert sleeps == [1.0, 2.0, 4.0] and len(t.calls) == 4


def test_retry_after_is_capped():
    sleeps: list[float] = []
    t = FakeTransport(error(429, headers={"retry-after": "3600"}), reply())
    session(t, sleeps=sleeps).ask("x")
    assert sleeps == [api.MAX_RETRY_WAIT]


@pytest.mark.parametrize("status,typ", [(400, "invalid_request_error"), (401, "authentication_error"),
                                        (403, "permission_error"), (404, "not_found_error")])
def test_client_errors_are_not_retried_and_do_not_reveal_the_key(status, typ):
    sleeps: list[float] = []
    t = FakeTransport(error(status, typ, "bad thing"))
    with pytest.raises(AIError) as e:
        session(t, sleeps=sleeps).ask("x")
    assert f"（{status}）" in str(e.value) and typ in str(e.value) and "bad thing" in str(e.value)
    assert KEY not in str(e.value)
    assert sleeps == [] and len(t.calls) == 1


def test_an_unreadable_error_body_is_shown_as_text():
    t = FakeTransport((502, {}, b"<html>Bad Gateway</html>"), (400, {}, b"plain"))
    with pytest.raises(AIError, match="plain"):
        session(t).ask("x")


def test_connection_errors_are_retried():
    t = FakeTransport(TransportError("connection refused"), reply("{}"))
    assert session(t).ask("x")[0] == "{}"
    t = FakeTransport(TransportError("connection refused"))
    with pytest.raises(AIError, match="接続できない: connection refused"):
        session(t).ask("x")


def test_a_failed_call_leaves_the_conversation_as_it_was():
    t = FakeTransport(reply("{}"), error(400), reply("{}"))
    s = session(t)
    s.ask("1", b"a")
    with pytest.raises(AIError):
        s.ask("2", b"b")
    s.ask("3", b"c")
    msgs = t.body()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[2]["content"][1]["text"] == "3"


def test_unreadable_success_body_is_an_error():
    with pytest.raises(AIError, match="読めない"):
        session(FakeTransport((200, {}, b"not json"))).ask("x")


# ---------------------------------------------------------------------------- real HTTP (local server)


def test_urllib_transport_against_a_local_server():
    """The default transport: status codes, headers and bodies from a real HTTP server on localhost."""
    seen: list[dict] = []
    answers = [error(529, "overloaded_error", headers={"Retry-After": "0"}), reply('{"ok": true}')]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append({"path": self.path, "key": self.headers["x-api-key"], "body": json.loads(body)})
            status, headers, data = answers.pop(0)
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        sleeps: list[float] = []
        s = ApiSession("haiku", "SYSTEM", api_key=KEY, base_url=f"http://127.0.0.1:{srv.server_port}",
                       sleep=sleeps.append)
        text, meta = s.ask("x", b"j")
    finally:
        srv.shutdown()
    assert text == '{"ok": true}' and meta["out_tokens"] == 5
    assert sleeps == [0.0]
    assert [x["path"] for x in seen] == ["/v1/messages"] * 2 and seen[0]["key"] == KEY


def test_urllib_transport_reports_a_refused_connection():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = srv.server_port
    srv.server_close()  # nothing listens there any more
    with pytest.raises(TransportError):
        api.urllib_post(f"http://127.0.0.1:{port}/v1/messages", {}, b"{}", 5)


# ---------------------------------------------------------------------------- through the loop


def test_a_scenario_runs_through_the_api_backend(make_run):
    """The loop drives ApiSession like ClaudeCodeSession: every `then` passes, one tap per `do`."""
    transports: list[FakeTransport] = []

    def answer(req):
        last = req["messages"][-1]["content"][-1]["text"]
        thens = json.loads(re.search(r"then to judge now: (\[.*\])", last).group(1))
        only = "only judge" in last
        out = {"verify": [{"then": t, "pass": True, "reason": "ok"} for t in thens],
               "action": {"type": "none" if only else "tap", "x": 1, "y": 1}, "purpose": "step", "done": True}
        return reply(json.dumps(out), usage={"input_tokens": 1500 * len(req["messages"]), "output_tokens": 80})

    def factory(system):
        transports.append(FakeTransport(answer))
        return ApiSession("haiku", system, api_key=KEY, post=transports[-1])

    res, drv, _, events = make_run(
        'name: t\napp: "http://x"\nsteps:\n  - id: A\n    actions:\n      - do: "tap A"\n'
        '      - then: "A shown"\n      - do: "tap B"\n      - then: "B shown"\n', None, factory=factory)
    assert res.status == "pass", [s.status for s in res.steps]
    assert len(drv.acts) == 2
    assert len(transports) == 1
    calls = transports[0].calls
    assert all(c["body"]["model"] == "claude-haiku-5-5" for c in calls)
    assert res.calls[-1]["in_tokens"] == 1500 * len(calls[-1]["body"]["messages"])
    sent_images = [sum(k == "image" for m in c["body"]["messages"] for k in kinds(m)) for c in calls]
    assert max(sent_images) <= api.KEEP_IMAGES
