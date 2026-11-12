"""Android via adb, screenshot only (no UI tree)."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import time
from typing import Any

from PIL import Image

from .base import Driver, DriverError

KEYS = {"enter": 66, "back": 4, "tab": 61, "delete": 67, "backspace": 67, "del": 112, "home": 3,
        "search": 84, "escape": 111, "esc": 111, "space": 62, "up": 19, "down": 20, "left": 21, "right": 22}


class AndroidDriver(Driver):
    platform = "android"
    description = "an Android device"
    detect_black = True

    def __init__(self, serial: str | None = None, width: int = 540):
        super().__init__(ignore_top=0.03)  # status bar (clock, notifications)
        if not shutil.which("adb"):
            raise DriverError("adb が見つからない（Android SDK Platform-Tools を入れて PATH に通す）")
        self.base = ["adb"] + (["-s", serial] if serial else [])
        state = self._adb(["get-state"]).strip()
        if state != "device":
            raise DriverError(f"Android 端末に接続できない（adb get-state: {state or 'なし'}）")
        self.w, self.h = self._grab_raw().size
        self.iw, self.ih = width, round(self.h * width / self.w)
        self.scale = self.w / width

    def _adb(self, args: list[str], timeout: float = 30) -> str:
        r = subprocess.run(self.base + args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.stdout + (r.stderr if r.returncode else "")

    def _grab_raw(self) -> Image.Image:
        b = subprocess.run(self.base + ["exec-out", "screencap"], capture_output=True, timeout=30).stdout
        if len(b) < 12:
            raise DriverError("スクリーンショットを取得できない（adb exec-out screencap）")
        w, h = int.from_bytes(b[0:4], "little"), int.from_bytes(b[4:8], "little")
        hdr = 16 if len(b) >= 16 + w * h * 4 else 12  # Android 9+ has a 16-byte header
        return Image.frombuffer("RGBA", (w, h), b[hdr:hdr + w * h * 4], "raw", "RGBA", 0, 1).convert("RGB")

    def grab(self) -> Image.Image:
        return self._grab_raw().resize((self.iw, self.ih))

    def reset(self, app: str, config: Any) -> None:
        self._adb(["shell", "input", "keyevent", "3"])  # home
        for pkg in [app, *getattr(config, "reset", [])]:
            self._adb(["shell", "am", "force-stop", pkg])
        if getattr(config, "clear_data_before", False):
            self._adb(["shell", "pm", "clear", app])
        self.settler.forget()

    def stop_app(self, app: str) -> None:
        self._adb(["shell", "am", "force-stop", app])

    def _tap(self, action: dict) -> bool:
        p = self.xy(action)
        if p is None:
            return False
        self._adb(["shell", "input", "tap", str(int(p[0] * self.scale)), str(int(p[1] * self.scale))])
        return True

    def _do(self, action: dict, app: str) -> str:
        t = action.get("type")
        if t == "tap":
            if not self._tap(action):
                return f"error: tap に座標がない {action}"
        elif t == "input":
            text = str(action.get("text", ""))
            if not text.isascii():
                return "error: Android の文字入力は ASCII のみ対応（日本語入力は未対応）"
            self._tap(action)  # without coordinates: type into the focused field
            self._adb(["shell", "input text " + shlex.quote(text.replace(" ", "%s"))])
        elif t == "key":
            key = str(action.get("key", "")).strip()
            code = KEYS.get(key.lower()) or (key if key.isdigit() or key.upper().startswith("KEYCODE_") else None)
            if code is None:
                return f"error: 未知のキー {key}"
            self._adb(["shell", "input", "keyevent", str(code)])
        elif t == "back":
            self._adb(["shell", "input", "keyevent", "4"])
        elif t == "scroll":
            d = action.get("direction", "down")
            cx, cy = self.w // 2, self.h // 2
            if d in ("left", "right"):
                x1, x2 = (int(self.w * 0.8), int(self.w * 0.2)) if d == "left" else (int(self.w * 0.2), int(self.w * 0.8))
                args = [str(x1), str(cy), str(x2), str(cy)]
            else:
                y1, y2 = (0.7, 0.3) if d == "down" else (0.3, 0.7)
                args = [str(cx), str(int(self.h * y1)), str(cx), str(int(self.h * y2))]
            self._adb(["shell", "input", "swipe", *args, "300"])
        elif t == "launch":
            out = self._adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
            if "No activities found" in out or "Error" in out:
                return f"error: 起動できない（{app}）"
        elif t == "wait":
            time.sleep(self.wait_s)
        elif t in ("none", "fail"):
            pass
        else:
            return f"error: 未知の操作 {t}"
        return "ok"
