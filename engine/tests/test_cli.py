from __future__ import annotations

import json

import pytest

from uiai import cli, platform

SCENARIO = """
name: ログイン
app: {web: "https://example.com"}
variables:
  email: test@example.com
  password: {env: UIAI_TEST_PW, secret: true}
steps:
  - id: s
    actions:
      - do: "「(email)」と「(password)」でログインする"
      - then: ログインできていること
"""


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    monkeypatch.setattr(platform, "probe", lambda serial=None, udid=None: {"android": False, "ios": False, "web": True})
    monkeypatch.delenv("UIAI_TEST_PW", raising=False)
    p = tmp_path / "login.yaml"
    p.write_text(SCENARIO, encoding="utf-8")
    return p


def test_dry_run_reports_missing_secret_without_running(scenario, tmp_path, capsys):
    code = cli.main(["run", str(scenario), "--dry-run", "--results-dir", str(tmp_path / "r")])
    out = capsys.readouterr().out
    assert code == 2
    assert "値のない変数: password（秘密・環境変数 UIAI_TEST_PW）" in out
    assert not (tmp_path / "r").exists()


def test_dry_run_ok_with_env(scenario, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("UIAI_TEST_PW", "x")
    code = cli.main(["run", str(scenario), "--dry-run", "--results-dir", str(tmp_path / "r")])
    assert code == 0
    assert "web で実行できる" in capsys.readouterr().out


def test_existing_run_id_is_refused(scenario, tmp_path, capsys):
    (tmp_path / "r" / "x").mkdir(parents=True)
    code = cli.main(["run", str(scenario), "--run-id", "x", "--results-dir", str(tmp_path / "r")])
    assert code == 2
    assert "既にある" in capsys.readouterr().out


def _events(tmp_path, evs):
    d = tmp_path / "r" / "run1"
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in evs),
                                    encoding="utf-8")


FAIL = {"type": "fail", "scenario": "S", "platform": "web", "kind": "then", "text": "T{}", "reason": "R"}


def test_watch_prints_failures_and_stops_at_run_end(tmp_path, capsys):
    _events(tmp_path, [{"type": "run_start"}, {**FAIL, "text": "一つ目"}, {"type": "warning", "text": "W"},
                       {"type": "run_end", "exit_code": 1, "summary": {"fail": 1}, "report": "x"}])
    code = cli.main(["watch", "--run", "run1", "--results-dir", str(tmp_path / "r"), "--wait", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert "一つ目" in out and "警告:" not in out and "実行終了" in out


def test_watch_skip_and_resume_hint(tmp_path, capsys):
    _events(tmp_path, [{"type": "run_start"}, {**FAIL, "text": "一つ目"}, {**FAIL, "text": "二つ目"}])
    code = cli.main(["watch", "--run", "run1", "--results-dir", str(tmp_path / "r"), "--wait", "1",
                     "--skip", "2", "--timeout", "1"])
    out = capsys.readouterr().out
    assert code == 3
    assert "一つ目" not in out and "二つ目" in out
    assert "uiai watch --run run1 --skip 3" in out


# --------------------------------------------------------------------------- parallel runs
import re  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

from conftest import FakeDriver  # noqa: E402


class FakeSession:
    """Stands in for ClaudeCodeSession: passes every `then`, does one tap per `do`."""

    def __init__(self, model, system):
        pass

    def ask(self, text, image=None):
        thens = json.loads(re.search(r"then to judge now: (\[.*\])", text).group(1))
        only = "only judge" in text
        return json.dumps({"verify": [{"then": t, "pass": True, "reason": ""} for t in thens],
                           "action": {"type": "none" if only else "tap", "x": 1, "y": 1},
                           "purpose": "step", "done": True}), {"wall_s": 0, "api_s": 0, "in_tokens": 1, "out_tokens": 1}

    def close(self):
        pass


class SlowDriver(FakeDriver):
    def __init__(self, label, log):
        super().__init__()
        self.label, self.log = label, log

    def act(self, action, app, check_stale=False):
        self.log.append((self.label, threading.current_thread().name))
        time.sleep(0.2)
        return super().act(action, app, check_stale)

    def close(self):
        pass


@pytest.fixture
def parallel_env(tmp_path, monkeypatch):
    import uiai.ai.claude_code as cc
    import uiai.drivers as drivers

    log, made = [], []

    def make_driver(p, serial=None, udid=None, browser_path=None, headed=False):
        if serial == "BAD":
            raise drivers.DriverError("つながらない")
        d = SlowDriver(serial or p, log)
        made.append(d)
        return d

    monkeypatch.setattr(drivers, "make_driver", make_driver)
    monkeypatch.setattr(cc, "ClaudeCodeSession", FakeSession)
    monkeypatch.setattr(platform, "android_serials", lambda: ["A", "B"])
    monkeypatch.setattr(platform, "booted_udids", lambda: [])
    files = []
    for i in range(4):
        p = tmp_path / f"s{i}.yaml"
        p.write_text(f'name: "S{i}"\napp: {{android: "com.example.app"}}\nsteps:\n  - id: a\n    actions:\n'
                     f'      - do: "開く"\n      - then: "表示されていること"\n', encoding="utf-8")
        files.append(str(p))
    return files, log, made


def test_parallel_spreads_scenarios_over_all_connected_devices(parallel_env, tmp_path, capsys):
    files, log, made = parallel_env
    t0 = time.time()
    code = cli.main(["run", *files, "--parallel", "--results-dir", str(tmp_path / "r"), "--run-id", "p",
                     "--rejudge-model", "none"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert {label for label, _ in log} == {"A", "B"}          # both devices ran scenarios
    assert time.time() - t0 < 4 * 0.2 * 0.9 + 1.5              # roughly halved, not sequential
    assert "[A] ▶" in out and "[B] ▶" in out
    summary = (tmp_path / "r" / "p" / "summary.md").read_text(encoding="utf-8")
    assert [summary.index(f"S{i}") for i in range(4)] == sorted(summary.index(f"S{i}") for i in range(4))


def test_a_device_that_cannot_start_leaves_its_scenarios_to_the_others(parallel_env, tmp_path, capsys, monkeypatch):
    files, log, made = parallel_env
    monkeypatch.setattr(platform, "android_serials", lambda: ["A", "BAD"])
    code = cli.main(["run", *files, "--parallel", "--serial", "BAD", "--serial", "A",
                     "--results-dir", str(tmp_path / "r"), "--run-id", "p", "--rejudge-model", "none"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert {label for label, _ in log} == {"A"} and "[BAD] ✗ 使えない: つながらない" in out


def test_without_a_working_device_the_scenarios_are_not_run(parallel_env, tmp_path, capsys, monkeypatch):
    files, log, made = parallel_env
    monkeypatch.setattr(platform, "android_serials", lambda: ["BAD"])  # listed by adb, but cannot be opened
    code = cli.main(["run", *files[:2], "--parallel", "--serial", "BAD",
                     "--results-dir", str(tmp_path / "r"), "--run-id", "p", "--rejudge-model", "none"])
    out = capsys.readouterr().out
    assert code == 2 and out.count("実行できる端末がない（BAD: つながらない）") == 4  # when skipped + final list


def test_several_devices_need_parallel(parallel_env, tmp_path, capsys):
    files, *_ = parallel_env
    code = cli.main(["run", files[0], "--serial", "A", "--serial", "B", "--results-dir", str(tmp_path / "r")])
    assert code == 2 and "--parallel" in capsys.readouterr().out


def test_without_parallel_scenarios_run_in_order_on_one_device(parallel_env, tmp_path, capsys):
    files, log, made = parallel_env
    code = cli.main(["run", *files, "--results-dir", str(tmp_path / "r"), "--run-id", "p", "--rejudge-model", "none"])
    out = capsys.readouterr().out
    assert code == 0 and len(made) == 1 and "[" not in out.split("run id")[1].split("\n")[2]
    assert [out.index(f"▶ S{i}") for i in range(4)] == sorted(out.index(f"▶ S{i}") for i in range(4))


def test_no_more_devices_are_started_than_there_are_scenarios(parallel_env, tmp_path, capsys):
    files, log, made = parallel_env
    code = cli.main(["run", files[0], "--parallel", "--results-dir", str(tmp_path / "r"), "--run-id", "p",
                     "--rejudge-model", "none"])
    assert code == 0 and len(made) == 1 and "android 1 台（A）" in capsys.readouterr().out


# ---------------------------------------------------------------------------- AI backend


def test_backend_api_needs_a_key(parallel_env, tmp_path, capsys, monkeypatch):
    files, *_ = parallel_env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for extra in ([], ["--dry-run"]):
        code = cli.main(["run", files[0], "--backend", "api", "--results-dir", str(tmp_path / "r"), *extra])
        assert code == 2 and "ANTHROPIC_API_KEY" in capsys.readouterr().out
    assert not (tmp_path / "r").exists()


def test_an_unknown_backend_from_the_environment_is_refused(parallel_env, tmp_path, capsys, monkeypatch):
    files, *_ = parallel_env
    monkeypatch.setenv("UIAI_BACKEND", "nope")
    code = cli.main(["run", files[0], "--results-dir", str(tmp_path / "r")])
    assert code == 2 and "nope" in capsys.readouterr().out


@pytest.mark.parametrize("args,env", [(["--backend", "api"], {}), ([], {"UIAI_BACKEND": "api"})])
def test_backend_api_runs_on_api_sessions(parallel_env, tmp_path, capsys, monkeypatch, args, env):
    import uiai.ai.api as api
    import uiai.ai.claude_code as cc

    files, *_ = parallel_env
    made = []

    class FakeApi(FakeSession):
        def __init__(self, model, system):
            made.append(model)

    class NoClaudeCode:
        def __init__(self, *a, **kw):
            raise AssertionError("claude -p must not be started with --backend api")

    monkeypatch.setattr(api, "ApiSession", FakeApi)
    monkeypatch.setattr(cc, "ClaudeCodeSession", NoClaudeCode)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    code = cli.main(["run", files[0], "--results-dir", str(tmp_path / "r"), "--run-id", "p", *args])
    out = capsys.readouterr().out
    assert code == 0, out
    assert made == ["haiku"] and "AI: Anthropic API" in out
    (result,) = (tmp_path / "r" / "p").glob("*/result.json")
    assert json.loads(result.read_text(encoding="utf-8"))["backend"] == "api"
    assert "haiku（Anthropic API）" in (result.parent / "report.md").read_text(encoding="utf-8")


def test_default_backend_is_claude_code(parallel_env, tmp_path, capsys, monkeypatch):
    files, *_ = parallel_env
    monkeypatch.delenv("UIAI_BACKEND", raising=False)
    code = cli.main(["run", files[0], "--results-dir", str(tmp_path / "r"), "--run-id", "p"])
    assert code == 0
    (result,) = (tmp_path / "r" / "p").glob("*/result.json")
    assert json.loads(result.read_text(encoding="utf-8"))["backend"] == "claude-code"
    assert "Anthropic API" not in capsys.readouterr().out
