from __future__ import annotations

from uiai import desktop
from uiai.desktop import DesktopNotifier, command


def fail_ev(i):
    return {"type": "fail", "kind": "then", "scenario": "s", "platform": "web", "section": "A",
            "text": f"t{i}", "reason": "r"}


def test_failures_are_shown_up_to_the_limit_and_the_rest_is_counted_at_the_end():
    sent = []
    n = DesktopNotifier(lambda title, body: sent.append((title, body)))
    for i in range(DesktopNotifier.LIMIT + 2):
        n(fail_ev(i))
    n({"type": "warning", "message": "w"})  # warnings are not shown one by one
    n({"type": "run_end", "summary": {"fail": 1}, "exit_code": 1})
    assert [t for t, _ in sent] == ["uiai: 失敗"] * DesktopNotifier.LIMIT + ["uiai: 実行終了"]
    assert sent[0][1].startswith("then 不合格: s @ web / A / 「t0」")
    assert sent[-1][1].startswith("通知していない失敗 2 件。実行終了")


def test_a_notifier_error_is_reported_once_and_does_not_raise(capsys):
    n = DesktopNotifier(lambda title, body: "no display")
    n(fail_ev(0))
    n(fail_ev(1))
    assert capsys.readouterr().err.count("デスクトップ通知を出せない: no display") == 1


def test_text_is_passed_as_arguments_not_inside_the_script():
    tricky = 'a" & do shell script "touch /tmp/x'
    argv, env = command("uiai", tricky, platform="darwin")
    assert argv[0] == "osascript" and argv[-1] == tricky and all(tricky not in a for a in argv[:-1])


def test_linux_without_notify_send_reports_why(monkeypatch):
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
    assert "notify-send" in command("t", "b", platform="linux")
