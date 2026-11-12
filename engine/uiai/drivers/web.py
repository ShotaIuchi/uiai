"""Web via Playwright (Chromium), screenshot only."""

from __future__ import annotations

import io
import os
import time
from typing import Any

from PIL import Image

from .base import Driver, DriverError

# Key names the AI uses -> Playwright's. The AI sent "cmd+a" (unknown to Playwright) and "Control+a" (on a
# Mac that moves to the line start instead of selecting all). Shortcut modifiers become ControlOrMeta
# (Meta on macOS, Control elsewhere), which is what a test scenario means by "select all" etc.
KEY_ALIASES = {
    "cmd": "ControlOrMeta", "command": "ControlOrMeta", "meta": "ControlOrMeta", "ctrl": "ControlOrMeta",
    "control": "ControlOrMeta", "alt": "Alt", "option": "Alt", "shift": "Shift",
    "enter": "Enter", "return": "Enter", "esc": "Escape", "escape": "Escape", "tab": "Tab",
    "backspace": "Backspace", "delete": "Delete", "del": "Delete", "space": " ",
    "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight",
    "pageup": "PageUp", "pagedown": "PageDown", "home": "Home", "end": "End",
}


def playwright_key(key: str) -> str:
    """'cmd+a' -> 'ControlOrMeta+a', 'enter' -> 'Enter', 'f5' -> 'F5'. Unknown names pass through."""
    out = []
    for part in [p.strip() for p in key.split("+")] if key.strip() != "+" else ["+"]:
        low = part.lower()
        if low in KEY_ALIASES:
            out.append(KEY_ALIASES[low])
        elif len(part) > 1 and low[0] == "f" and low[1:].isdigit():
            out.append(part.upper())
        else:
            out.append(part)
    return "+".join(out)


class WebDriver(Driver):
    platform = "web"
    description = "a web browser"

    def __init__(self, width: int = 1280, height: int = 800, executable: str | None = None,
                 headed: bool = False):
        super().__init__()
        from playwright.sync_api import Error as PwError, sync_playwright

        self.iw, self.ih = width, height
        self._pw = sync_playwright().start()
        opts: dict = {"headless": not headed}
        executable = executable or os.environ.get("UIAI_BROWSER_PATH")
        if executable:
            opts["executable_path"] = executable
        try:
            self.browser = self._pw.chromium.launch(**opts)
        except PwError as e:
            self._pw.stop()
            raise DriverError("ブラウザを起動できない。`uiai setup` でブラウザを取得する"
                              f"（または --browser-path で指定）: {str(e).splitlines()[0]}") from e
        self.context = None
        self.page = None

    def _new_page(self) -> None:
        if self.context is not None:
            self.context.close()
        self.context = self.browser.new_context(viewport={"width": self.iw, "height": self.ih}, locale="ja-JP")
        self.page = self.context.new_page()

    def reset(self, app: str, config: Any) -> None:
        self._new_page()  # fresh context = no cookies/storage (covers clear_data_before)
        self.settler.forget()

    def stop_app(self, app: str) -> None:
        if self.page is not None:
            self.page.goto("about:blank")

    def close(self) -> None:
        try:
            if self.context is not None:
                self.context.close()
            self.browser.close()
        finally:
            self._pw.stop()

    def grab(self) -> Image.Image:
        if self.page is None:
            self._new_page()
        for i in range(50):  # capture fails while navigating to another site (renderer swap)
            try:
                return Image.open(io.BytesIO(self.page.screenshot(type="jpeg", quality=80))).convert("RGB")
            except Exception:  # noqa: BLE001
                if i == 49:
                    raise
                time.sleep(0.1)
        raise AssertionError("unreachable")

    def _do(self, action: dict, app: str) -> str:
        t = action.get("type")
        p = self.page
        if p is None:
            self._new_page()
            p = self.page
        if t in ("tap", "input"):
            xy = self.xy(action)
            if xy is None and t == "tap":
                return f"error: tap に座標がない {action}"
            if xy is not None:  # input without coordinates types into the focused field
                p.mouse.click(*xy)
            if t == "input":
                p.keyboard.type(str(action.get("text", "")))
        elif t == "key":
            p.keyboard.press(playwright_key(str(action.get("key") or "Enter")))
        elif t == "back":
            p.go_back(wait_until="domcontentloaded", timeout=15000)
        elif t == "scroll":
            d = action.get("direction", "down")
            p.mouse.move(self.iw / 2, self.ih / 2)
            dx = {"left": -1, "right": 1}.get(d, 0) * self.iw * 0.6
            dy = {"down": 1, "up": -1}.get(d, 0) * self.ih * 0.6
            p.mouse.wheel(dx, dy)
        elif t == "launch":
            p.goto(app, wait_until="domcontentloaded", timeout=30000)
        elif t == "wait":
            time.sleep(self.wait_s)
        elif t in ("none", "fail"):
            pass
        else:
            return f"error: 未知の操作 {t}"
        return "ok"
