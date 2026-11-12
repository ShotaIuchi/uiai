"""OS desktop notifications (design doc 9), for runs outside Claude Code. Opt-in: `uiai run --notify`.

Failures are shown one by one, at most LIMIT per run; the run's summary is shown at the end.
macOS: osascript. Linux: notify-send. Windows: a toast from Windows PowerShell 5.1 (unverified).
The text goes through argv / environment variables, never into the script source, so scenario text
cannot change the command.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Callable

from .events import NOTIFY, describe

MAC_SCRIPT = ["on run argv", "display notification (item 2 of argv) with title (item 1 of argv)", "end run"]
WIN_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$x = $t.GetElementsByTagName('text')
$x.Item(0).AppendChild($t.CreateTextNode($env:UIAI_NOTIFY_TITLE)) > $null
$x.Item(1).AppendChild($t.CreateTextNode($env:UIAI_NOTIFY_BODY)) > $null
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($t))
"""
MAX_BODY = 240


def command(title: str, body: str, platform: str = sys.platform) -> tuple[list[str], dict | None] | str:
    """(argv, env) for the platform, or an error message if notifications are not available."""
    if platform == "darwin":
        args = ["osascript"]
        for line in MAC_SCRIPT:
            args += ["-e", line]
        return args + [title, body], None
    if platform.startswith("win"):
        ps = shutil.which("powershell")  # Windows PowerShell 5.1: pwsh 7 cannot load WinRT types this way
        if not ps:
            return "powershell が見つからない"
        env = dict(os.environ, UIAI_NOTIFY_TITLE=title, UIAI_NOTIFY_BODY=body)
        return [ps, "-NoProfile", "-NonInteractive", "-Command", WIN_SCRIPT], env
    if not shutil.which("notify-send"):
        return "notify-send が見つからない（libnotify-bin などのパッケージに入っている）"
    return ["notify-send", "--app-name=uiai", title, body], None


def send(title: str, body: str) -> str | None:
    """Show one notification. Returns an error message, or None."""
    cmd = command(title, body[:MAX_BODY])
    if isinstance(cmd, str):
        return cmd
    argv, env = cmd
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=15, env=env)
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    return None if r.returncode == 0 else ((r.stderr or r.stdout).strip()[:200] or f"終了コード {r.returncode}")


class DesktopNotifier:
    """EventLog listener."""

    LIMIT = 5

    def __init__(self, sender: Callable[[str, str], str | None] = send):
        self.sender = sender
        self.shown = 0
        self.failures = 0
        self.warned = False

    def notify(self, title: str, body: str) -> None:
        err = self.sender(title, body)
        if err and not self.warned:  # a broken notifier must not break (or flood) the run
            self.warned = True
            print(f"[uiai] デスクトップ通知を出せない: {err}", file=sys.stderr)

    def __call__(self, ev: dict) -> None:
        if ev["type"] in NOTIFY:
            self.failures += 1
            if self.shown < self.LIMIT:
                self.shown += 1
                self.notify("uiai: 失敗", describe(ev).removeprefix("[uiai] "))
        elif ev["type"] == "run_end":
            body = describe(ev).removeprefix("[uiai] ")
            if self.failures > self.shown:
                body = f"通知していない失敗 {self.failures - self.shown} 件。" + body
            self.notify("uiai: 実行終了", body)
