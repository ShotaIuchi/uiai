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

    def reset(self, app, cfg):
        self.resets += 1

    def stop_app(self, app):
        pass

    def observe(self):
        return Observation(b"jpeg", self.iw, self.ih, None, self.black, 1, 0.0)

    def watch(self, secs):
        self.watched.append(secs)
        return self.watch_results.pop(0) if self.watch_results else False

    def act(self, action, app, check_stale=False):
        self.checked_stale = check_stale
        if check_stale and self.stale and self.stale.pop(0):
            return "stale"
        self.acts.append(action)
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
            "wall_s": 0.1, "api_s": 0.1, "in_tokens": 10, "out_tokens": 5}

    def close(self):
        self.closed = True


def reply(action=None, verify=None, done=True, purpose="step", **kw):
    return {"verify": verify or [], "action": action or {"type": "tap", "x": 1, "y": 2},
            "purpose": purpose, "done": done, **kw}


def v(text, ok=True, **kw):
    return {"then": text, "pass": ok, "reason": "r", **kw}


@pytest.fixture
def clock(monkeypatch):
    c = FakeClock()
    monkeypatch.setattr(loop_mod, "time", c)
    return c


@pytest.fixture
def make_run(tmp_path, clock):
    def _make(yaml_text: str, script, driver=None, values=None):
        p = tmp_path / "s.yaml"
        p.write_text(yaml_text, encoding="utf-8")
        sc = load(p)
        vals, _ = resolve_variables(sc, values or {}, interactive=False)
        red = Redactor([vals[n] for n in sc.secret_names if n in vals])
        out = tmp_path / "out"
        out.mkdir(exist_ok=True)
        ev = EventLog(tmp_path / "events.jsonl", red)
        drv = driver or FakeDriver()
        ai = FakeAI(script)
        runner = ScenarioRunner(sc, "web", "http://x", drv, lambda system: ai, vals, out, ev, red, "haiku",
                                printer=lambda s: None)
        res = runner.run()
        ev.close()
        events = [json.loads(ln) for ln in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        return res, drv, ai, events

    return _make
