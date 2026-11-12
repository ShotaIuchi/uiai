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
    monkeypatch.setattr(platform, "probe", lambda serial=None: {"android": False, "ios": False, "web": True})
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
