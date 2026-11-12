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


def test_a_trailing_newline_in_the_key_is_removed(monkeypatch):
    """A secret pasted with a newline: urllib would refuse the header with the key in its message."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env\n")
    t = FakeTransport(reply())
    ApiSession("haiku", "SYSTEM", post=t).ask("x")
    assert t.calls[0]["headers"]["x-api-key"] == "sk-env"


def test_a_key_of_only_whitespace_is_no_key():
    with pytest.raises(AIError, match="ANTHROPIC_API_KEY がない"):
        api.load_key(" \n")


@pytest.mark.parametrize("key", ["sk-a b", "sk-a\nb", "sk-ä"])
def test_a_key_that_cannot_go_in_a_header_is_refused_without_showing_it(key):
    with pytest.raises(AIError, match="使えない文字") as e:
        ApiSession("haiku", "SYSTEM", api_key=key, post=FakeTransport(reply()))
    assert key not in str(e.value)


@pytest.mark.parametrize("url", ["proxy.local:8080", "http://proxy:abc", "https://", "ftp://proxy"])
def test_a_malformed_base_url_is_refused(monkeypatch, url):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", url)
    with pytest.raises(AIError, match="http:// か https://"):
        session(FakeTransport(reply()))


def test_the_config_check_names_every_problem(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "proxy.local")
    with pytest.raises(AIError) as e:
        api.check_config()
    assert "ANTHROPIC_API_KEY がない" in str(e.value) and "ANTHROPIC_BASE_URL" in str(e.value)


def test_a_blank_base_url_is_unset(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "  ")
    t = FakeTransport(reply())
    session(t).ask("x")
    assert t.calls[0]["url"] == "https://api.anthropic.com/v1/messages"


def test_a_malformed_base_url_is_not_shown_since_it_may_carry_a_token(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "gateway.corp/v1?key=SECRET")
    with pytest.raises(AIError) as e:
        session(FakeTransport(reply()))
    assert "SECRET" not in str(e.value)


def test_a_base_url_with_credentials_is_refused_without_showing_them(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://user:pa55word@proxy.local")
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    with pytest.raises(AIError, match="ユーザー名・パスワード") as e:
        api.check_config()
    assert "pa55word" not in str(e.value)


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


@pytest.mark.parametrize("content", [[], [{"type": "text", "text": " \n "}]])
def test_an_empty_reply_is_returned_as_it_is_but_kept_non_empty_in_the_history(content):
    t = FakeTransport(reply(content=content), reply())
    s = session(t)
    assert s.ask("x")[0].strip() == ""
    s.ask("y")
    assert t.body()["messages"][1]["content"][0]["text"] == api.EMPTY_REPLY


def test_an_empty_screenshot_is_never_sent_as_an_image():
    t = FakeTransport(reply())
    session(t).ask("x", b"")
    assert t.body()["messages"][0]["content"][0] == {"type": "text", "text": api.OMITTED}


def test_a_lone_surrogate_in_the_text_does_not_break_the_request():
    t = FakeTransport(reply())
    session(t).ask("bad \ud800 char")
    assert t.body()["messages"][0]["content"][0]["text"] == "bad ? char"


def test_only_the_screenshots_still_sent_are_kept_in_memory():
    s = session(FakeTransport(reply()))
    for i in range(5):
        s.ask(str(i), f"JPEG{i}".encode())
    s.ask("text only")
    assert [img for _, img, _ in s.turns] == [b"", b"", b"", b"JPEG3", b"JPEG4", None]


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


@pytest.mark.parametrize("value", ["nan", "inf", "soon"])
def test_a_retry_after_that_is_not_a_number_of_seconds_falls_back_to_backoff(value):
    sleeps: list[float] = []
    t = FakeTransport(error(429, headers={"retry-after": value}), reply())
    session(t, sleeps=sleeps).ask("x")
    assert sleeps == [1.0]


def test_retry_after_is_capped():
    sleeps: list[float] = []
    t = FakeTransport(error(429, headers={"retry-after": "3600"}), reply())
    session(t, sleeps=sleeps).ask("x")
    assert sleeps == [api.MAX_RETRY_WAIT]


def test_a_key_echoed_in_an_error_body_is_masked_before_the_message_is_shortened():
    """A key straddling the cut would otherwise survive in part."""
    t = FakeTransport(error(400, "invalid_request_error", "x" * 290 + KEY))
    with pytest.raises(AIError) as e:
        session(t).ask("x")
    assert KEY[:8] not in str(e.value)


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


def test_a_transport_error_that_another_attempt_cannot_fix_is_not_retried():
    sleeps: list[float] = []
    t = FakeTransport(TransportError("certificate verify failed", retry=False))
    with pytest.raises(AIError, match="接続できない: certificate verify failed"):
        session(t, sleeps=sleeps).ask("x")
    assert sleeps == [] and len(t.calls) == 1


def test_urllib_transport_does_not_retry_a_malformed_url():
    with pytest.raises(TransportError) as e:
        api.urllib_post("http://127.0.0.1:abc/v1/messages", {}, b"{}", 5)
    assert e.value.retry is False


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


@pytest.mark.parametrize("body", [b"[]", b'"ok"', b"{}", b'{"content": "text"}'])
def test_a_success_body_of_the_wrong_shape_is_an_error(body):
    s = session(FakeTransport((200, {}, body)))
    with pytest.raises(AIError, match="形が想定と違う"):
        s.ask("x")
    assert s.turns == []


def test_a_reply_cut_off_at_the_output_limit_is_an_error():
    body = {"content": [{"type": "text", "text": '{"verify": ['}], "stop_reason": "max_tokens"}
    s = session(FakeTransport((200, {}, json.dumps(body).encode())))
    with pytest.raises(AIError, match="max_tokens"):
        s.ask("x")
    assert s.turns == []


@pytest.mark.parametrize("stop,says", [("refusal", "拒否"), ("model_context_window_exceeded", "入力の上限")])
def test_a_refused_or_overflowing_reply_is_an_error_not_an_empty_answer(stop, says):
    """Otherwise the loop takes the empty reply as unreadable and fails the app under test (exit 1)."""
    body = {"content": [], "stop_reason": stop}
    s = session(FakeTransport((200, {}, json.dumps(body).encode())))
    with pytest.raises(AIError, match=says):
        s.ask("x")
    assert s.turns == []


def test_odd_content_items_and_usage_values_are_ignored():
    body = {"content": ["text", None, {"type": "text", "text": 5}, {"type": "text", "text": "{}"}],
            "usage": {"input_tokens": "10", "output_tokens": 3}}
    text, meta = session(FakeTransport((200, {}, json.dumps(body).encode()))).ask("x")
    assert text == "{}" and meta["in_tokens"] == 0 and meta["out_tokens"] == 3


def test_any_other_transport_failure_becomes_an_ai_error_with_the_key_masked():
    t = FakeTransport(ValueError(f"Invalid header value {KEY!r}"))
    with pytest.raises(AIError, match=r"呼び出せない（ValueError）") as e:
        session(t).ask("x")
    assert KEY not in str(e.value) and "****" in str(e.value)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += s


def test_one_call_with_its_retries_ends_within_the_timeout():
    """Like ClaudeCodeSession, the timeout bounds the whole call, not each attempt."""
    clock = FakeClock()
    timeouts: list[float] = []

    def slow_overload(url, headers, body, timeout):
        timeouts.append(timeout)
        clock.now += 50
        return error(529, "overloaded_error", headers={"retry-after": "10"})

    s = ApiSession("haiku", "SYSTEM", timeout=120, api_key=KEY, post=slow_overload, sleep=clock.sleep, clock=clock)
    with pytest.raises(AIError, match="120 秒以内に応答が得られない"):
        s.ask("x")
    assert timeouts == [120, 60]  # each attempt only gets the time that is left
    assert clock.now <= 120


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
        srv.server_close()
    assert text == '{"ok": true}' and meta["out_tokens"] == 5
    assert sleeps == [0.0]
    assert [x["path"] for x in seen] == ["/v1/messages"] * 2 and seen[0]["key"] == KEY


def _server(handler_cls):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_a_redirect_is_not_followed_so_the_key_stays_with_the_configured_host():
    reached: list[dict] = []

    class Elsewhere(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            reached.append(dict(self.headers))
            self.send_response(200)
            self.end_headers()

        do_POST = do_GET  # noqa: N815

        def log_message(self, *args):
            pass

    other = _server(Elsewhere)

    class Redirect(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{other.server_port}/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    srv = _server(Redirect)
    try:
        s = ApiSession("haiku", "SYSTEM", api_key=KEY, base_url=f"http://127.0.0.1:{srv.server_port}")
        with pytest.raises(AIError, match="リダイレクトを返した（302") as e:
            s.ask("x")
    finally:
        for x in (srv, other):
            x.shutdown()
            x.server_close()
    assert reached == [] and KEY not in str(e.value)


def test_a_slowly_trickling_response_still_ends_at_the_timeout():
    """urllib's own timeout is per socket operation; a byte every 0.2 s would never trip it."""
    import time

    class Trickle(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            try:
                for _ in range(20):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.2)
            except OSError:
                pass

        def log_message(self, *args):
            pass

    srv = _server(Trickle)
    try:
        t0 = time.monotonic()
        with pytest.raises(TransportError, match="以内に応答が終わらない"):
            api.urllib_post(f"http://127.0.0.1:{srv.server_port}/v1/messages", {}, b"{}", 1.0)
        assert time.monotonic() - t0 < 1.5
    finally:
        srv.shutdown()
        srv.server_close()


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
    assert res.backend == "api" and res.model_id == "claude-haiku-5-5"  # recorded from the session that ran
    from uiai import report

    assert "- モデル: haiku（Anthropic API・claude-haiku-5-5）" in report._meta_lines(res)[4]
    assert len(drv.acts) == 2
    assert len(transports) == 1
    calls = transports[0].calls
    assert all(c["body"]["model"] == "claude-haiku-5-5" for c in calls)
    assert res.calls[-1]["in_tokens"] == 1500 * len(calls[-1]["body"]["messages"])
    sent_images = [sum(k == "image" for m in c["body"]["messages"] for k in kinds(m)) for c in calls]
    assert max(sent_images) <= api.KEEP_IMAGES
