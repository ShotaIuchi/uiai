"""Android via adb, screenshot only (no UI tree).

ASCII text goes through `adb shell input text`, which cannot type anything else. Other text
(Japanese...) is pasted into the focused field by uiautomator2: its server (u2.jar, started
with app_process, no app installed) sets the clipboard and pastes. Side effects: the device
clipboard is overwritten, and Android may show a "pasted from your clipboard" toast. If that
route fails, uiautomator2 installs its own input method app (com.github.uiautomator).
"""

from __future__ import annotations

import io
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
        super().__init__(ignore_top=0.03, ignore_right=0.02)  # status bar; fading scroll bar
        if not shutil.which("adb"):
            raise DriverError("adb が見つからない（Android SDK Platform-Tools を入れて PATH に通す）")
        self.base = ["adb"] + (["-s", serial] if serial else [])
        self.serial = serial
        self._u2: Any = None
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
        """Full-size screenshot. PNG (-p): ~0.2 MB instead of ~10 MB raw pixels per frame, which matters on a
        USB-connected device. The device spends the time encoding: on an emulator, where the transfer is
        local, a frame took 0.24 s instead of 0.14 s."""
        b = subprocess.run(self.base + ["exec-out", "screencap", "-p"], capture_output=True, timeout=30).stdout
        try:
            return Image.open(io.BytesIO(b)).convert("RGB")
        except OSError as e:  # empty, truncated or not a PNG (UnidentifiedImageError is an OSError)
            raise DriverError("スクリーンショットを取得できない（adb exec-out screencap -p）") from e

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

    def close(self) -> None:
        if self._u2 is not None:
            try:
                self._u2.stop_uiautomator()
            except Exception:  # noqa: BLE001
                pass
            self._u2 = None

    def _paste_text(self, text: str) -> None:
        if self._u2 is None:
            import uiautomator2  # only needed for non-ASCII input

            self._u2 = uiautomator2.connect(self.serial)
        self._u2.send_keys(text)

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
            if self._tap(action):  # without coordinates: type into the focused field
                time.sleep(0.3)
            if text.isascii():
                self._adb(["shell", "input text " + shlex.quote(text.replace(" ", "%s"))])
            else:
                self._paste_text(text)
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
        elif t in ("none", "fail"):
            pass
        else:
            return f"error: 未知の操作 {t}"
        return "ok"
