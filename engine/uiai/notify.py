"""Webhook notifications (Slack, Teams...): {"text": "..."} POSTs.

At most LIMIT failures are sent one by one per run; the rest are held and sent together
at the end (design doc 9).
"""

from __future__ import annotations

import json
import sys
import urllib.request

from .events import NOTIFY, describe


class Webhook:
    LIMIT = 10

    def __init__(self, url: str, timeout: float = 10.0):
        self.url, self.timeout = url, timeout
        self.sent = 0
        self.held: list[str] = []
        self.failures = 0

    def post(self, text: str) -> None:
        req = urllib.request.Request(self.url, data=json.dumps({"text": text}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=self.timeout).read()
        except Exception as e:  # noqa: BLE001 - a broken webhook must not break the run
            print(f"[uiai] Webhook に送れない: {e}", file=sys.stderr)

    def __call__(self, ev: dict) -> None:
        if ev["type"] in NOTIFY:
            self.failures += 1
            line = describe(ev)
            if self.sent < self.LIMIT:
                self.sent += 1
                self.post(line)
            else:
                self.held.append(line)
        elif ev["type"] == "run_end" and self.failures:
            text = describe(ev)
            if self.held:
                shown = self.held[:20]
                text += f"\n未送信の失敗 {len(self.held)} 件:\n" + "\n".join(shown)
                if len(self.held) > len(shown):
                    text += f"\n…ほか {len(self.held) - len(shown)} 件"
            self.post(text)
