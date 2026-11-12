from __future__ import annotations

import json

from uiai.events import EventLog, describe


class FullDisk:
    """Fails `fails` writes, then writes to `real`."""

    def __init__(self, real, fails):
        self.real, self.fails = real, fails

    def write(self, s):
        if self.fails:
            self.fails -= 1
            raise OSError(28, "No space left on device")
        self.real.write(s)

    def flush(self):
        self.real.flush()

    def close(self):
        self.real.close()


def test_a_full_disk_does_not_stop_the_events_and_later_ones_are_still_written(tmp_path, capsys):
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    seen = []
    log.listeners.append(seen.append)
    log._f = FullDisk(log._f, fails=2)
    for r in ("a", "b", "c"):
        log.emit("error", reason=r)
    log.emit("run_end", exit_code=0)
    log.close()
    assert [e.get("reason") for e in seen] == ["a", "b", "c", None]  # notifications still go out
    assert "No space left" in log.write_error
    assert capsys.readouterr().err.count("書けないイベントは抜ける") == 1  # said once
    written = [json.loads(ln)["type"] for ln in path.read_text(encoding="utf-8").splitlines()]
    assert written == ["error", "run_end"]  # space came back: the end of the run still gets there


def test_a_lone_surrogate_from_the_ai_is_written_and_a_broken_notifier_does_not_stop_the_others(tmp_path, capsys):
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    seen = []

    def broken(ev):
        ev["reason"].encode("utf-8")  # raises on the lone surrogate

    log.listeners += [broken, seen.append]
    log.emit("fail", reason="bad \ud83d")
    log.close()
    assert json.loads(path.read_text(encoding="utf-8"))["reason"] == "bad ?"
    assert len(seen) == 1 and "通知に失敗した（UnicodeEncodeError）" in capsys.readouterr().err


def test_the_run_end_line_counts_unwritten_reports():
    line = describe({"type": "run_end", "exit_code": 2, "summary": {"pass": 1, "report_errors": 1}})
    assert "合格 1" in line and "記録失敗 1" in line and "終了コード 2" in line
    assert "記録失敗" not in describe({"type": "run_end", "exit_code": 0, "summary": {"pass": 1}})
