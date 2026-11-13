from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uiai import loop as loop_mod  # noqa: E402
from uiai.events import EventLog  # noqa: E402
from uiai.loop import ScenarioRunner  # noqa: E402
from uiai.redact import Redactor  # noqa: E402
from uiai.scenario import load, resolve_variables  # noqa: E402
from uiai.settle import Observation  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s

    def strftime(self, fmt):
        return "2026-01-01 00:00:00"


class FakeDriver:
    platform = "web"
    description = "a test screen"
    detect_black = False
    iw, ih = 100, 80

    def __init__(self):
        self.acts: list[dict] = []
        self.resets = 0
        self.black = False
        self.watch_results: list[bool] = []
        self.watched: list[float] = []
        self.stale: list[bool] = []
        self.trace: list[str] = []   # observe / act:<type> / wait:<s> / wait_out / reset / stop_app, in order

    def reset(self, app, cfg):
        self.resets += 1
        self.trace.append("reset")

    def stop_app(self, app):
        self.trace.append("stop_app")

    def wait_after_action(self, seconds):
        if seconds:
            self.trace.append(f"wait:{seconds:g}")

    def wait_out(self):
        self.trace.append("wait_out")

    def observe(self):
        self.trace.append("observe")
        return Observation(b"jpeg", self.iw, self.ih, None, self.black, 1, 0.0)

    def watch(self, secs):
        self.watched.append(secs)
        return self.watch_results.pop(0) if self.watch_results else False

    def act(self, action, app, check_stale=False):
        self.checked_stale = check_stale
        if check_stale and self.stale and self.stale.pop(0):
            return "stale"
        self.acts.append(action)
        self.trace.append(f"act:{action.get('type')}")
        return "ok"


class FakeAI:
    """`script(msg, n)` returns the reply dict (or raw string) for the n-th call."""

    def __init__(self, script):
        self.script = script
        self.msgs: list[str] = []
        self.closed = False

    def ask(self, text, image=None):
        self.msgs.append(text)
        r = self.script(text, len(self.msgs))
        return (r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)), {
            "wall_s": 0.1, "api_s": 0.1, "in_tokens": 1000 * len(self.msgs), "out_tokens": 5}  # grows per call

    def close(self):
        self.closed = True


def reply(action=None, verify=None, done=True, purpose="step", **kw):
    return {"verify": verify or [], "action": action or {"type": "tap", "x": 1, "y": 2},
            "purpose": purpose, "done": done, **kw}


def v(text, ok=True, **kw):
    return {"then": text, "pass": ok, "reason": "r", **kw}


@pytest.fixture(autouse=True)
def _no_outside_settings(monkeypatch):
    """The developer's shell must not change what the tests do (UIAI_BACKEND=api with a real key would
    send billed requests; ANTHROPIC_BASE_URL would change the URL; a proxy would take the requests to the
    local test servers). Tests that need one set it."""
    proxies = [p for n in ("http", "https", "all", "no") for p in (f"{n}_proxy", f"{n.upper()}_PROXY")]
    for name in ("UIAI_BACKEND", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "UIAI_WEBHOOK_URL", "UIAI_NOTIFY",
                 *proxies):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def clock(monkeypatch):
    c = FakeClock()
    monkeypatch.setattr(loop_mod, "time", c)
    return c


@pytest.fixture
def make_run(tmp_path, clock):
    def _make(yaml_text: str, script, driver=None, values=None, fresh_ai=False, rejudge=None, factory=None):
        """fresh_ai: each conversation gets its own FakeAI (returned as a list); `script(msg, n)` then
        sees n counted per conversation. Otherwise one FakeAI serves every conversation.
        rejudge: `rejudge(msg)` -> reply (dict, str, or an exception to raise) of the re-judge model; the
        FakeAIs it answered through are in `runner.rejudges`.
        factory: `factory(system)` -> session, used instead of FakeAI (`script` is then ignored)."""
        p = tmp_path / "s.yaml"
        p.write_text(yaml_text, encoding="utf-8")
        sc = load(p)
        vals, _ = resolve_variables(sc, values or {}, interactive=False)
        red = Redactor([vals[n] for n in sc.secret_names if n in vals])
        out = tmp_path / "out"
        out.mkdir(exist_ok=True)
        ev = EventLog(tmp_path / "events.jsonl", red)
        drv = driver or FakeDriver()
        if factory is not None:
            ai = None
        elif fresh_ai:
            ai = []

            def factory(system):
                ai.append(FakeAI(script))
                return ai[-1]
        else:
            ai = FakeAI(script)

            def factory(system):
                return ai
        rejudges: list[FakeAI] = []

        def rejudge_factory(system):
            def answer(msg, n):
                r = rejudge(msg)
                if isinstance(r, Exception):
                    raise r
                return r
            rejudges.append(FakeAI(answer))
            return rejudges[-1]
        runner = ScenarioRunner(sc, "web", "http://x", drv, factory, vals, out, ev, red, "haiku",
                                printer=lambda s: None, rejudge_factory=rejudge_factory if rejudge else None,
                                rejudge_model="sonnet")
        runner.rejudges = rejudges
        res = runner.run()
        ev.close()
        events = [json.loads(ln) for ln in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        return res, drv, ai, events

    return _make
