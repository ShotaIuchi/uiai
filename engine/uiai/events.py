"""Event stream (events.jsonl): the source of real-time failure notifications.

Event types:
  run_start, scenario_start, fail, warning, error, scenario_end, run_end
Only `fail` and `error` are notified one by one; `warning` and not-run steps are summarised
at the end (design doc 9).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .redact import Redactor

NOTIFY = ("fail", "error")


class EventLog:
    def __init__(self, path: Path, redactor: Redactor | None = None):
        self.path = path
        self.redact = redactor or Redactor()
        self.listeners: list[Callable[[dict], None]] = []
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(path, "a", encoding="utf-8")

    def emit(self, type_: str, **data: Any) -> dict:
        ev = self.redact({"ts": datetime.now().astimezone().isoformat(timespec="seconds"), "type": type_, **data})
        with self._lock:
            self._f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            self._f.flush()
        for fn in self.listeners:
            fn(ev)
        return ev

    def close(self) -> None:
        self._f.close()


def describe(ev: dict) -> str:
    """One human-readable line for a notification."""
    where = f"{ev.get('scenario', '')}" + (f" @ {ev['platform']}" if ev.get("platform") else "")
    if ev["type"] == "error":
        return f"[uiai] 実行エラー: {where}: {ev.get('reason', '')}"
    if ev["type"] == "fail":
        kind = "then 不合格" if ev.get("kind") == "then" else "do 失敗"
        line = f"[uiai] {kind}: {where} / {ev.get('section', '')} / 「{ev.get('text', '')}」: {ev.get('reason', '')}"
        if ev.get("read"):
            line += f"（読み取った文字: {ev['read']}）"
        if ev.get("not_run"):
            line += f"（残り {ev['not_run']} ステップは未実行）"
        return line
    if ev["type"] == "warning":
        return f"[uiai] 警告: {where} / {ev.get('section', '')} / 「{ev.get('text', '')}」: {ev.get('message', '')}"
    if ev["type"] == "scenario_end":
        return f"[uiai] シナリオ終了: {where}: {ev.get('status', '')}（{ev.get('seconds', '')} 秒）"
    if ev["type"] == "run_end":
        s = ev.get("summary", {})
        return (f"[uiai] 実行終了: 合格 {s.get('pass', 0)}・警告付き合格 {s.get('pass_warn', 0)}・"
                f"不合格 {s.get('fail', 0)}・エラー {s.get('error', 0) + s.get('skipped', 0)}"
                f"（終了コード {ev.get('exit_code')}）{ev.get('report', '')}")
    return json.dumps(ev, ensure_ascii=False)
