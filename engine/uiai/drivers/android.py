"""Android via adb, screenshot only (no UI tree).

Text is pasted into the focused field by uiautomator2: its server (u2.jar, started with
app_process, no app installed) sets the clipboard and pastes. adb alone cannot do it: the shell
has no clipboard command, and `adb shell input text` fails on anything but ASCII. Side effects:
the device clipboard is overwritten, and Android may show a "pasted from your clipboard" toast.
If that route fails, uiautomator2 installs its own input method app (com.github.uiautomator).
The first input connects to uiautomator2 (~3.4 s); later ones reuse the connection.

Right after a paste, Android shows a clipboard notice and Gboard offers the pasted text in its
suggestion strip, for about a second: a screenshot then would carry the text to the AI. So ASCII
text holding a secret value is typed with `adb shell input text` instead (non-ASCII secrets can
only be pasted).

With a typing delay (config.type_delay), ASCII is typed one key event at a time through
uiautomator2 (key code + shift, US layout), since `input keyevent --delay` cannot hold shift and
every `input` call costs about 0.5 s. Other text is still pasted all at once.
"""

from __future__ import annotations

import io
import shlex
import shutil
import subprocess
import time
from typing import Any

from PIL import Image

from .base import Driver, DriverError, paced

KEYS = {"enter": 66, "back": 4, "tab": 61, "delete": 67, "backspace": 67, "del": 112, "home": 3,
        "search": 84, "escape": 111, "esc": 111, "space": 62, "up": 19, "down": 20, "left": 21, "right": 22}
SHIFT = 1  # KeyEvent.META_SHIFT_ON


def _us_keys() -> dict[str, tuple[int, int]]:
    """Character -> (key code, meta state) on the US layout of Android's virtual keyboard (Generic.kcm)."""
    keys = {" ": (62, 0), "\n": (66, 0), "\t": (61, 0)}
    for i, c in enumerate("0123456789"):
        keys[c] = (7 + i, 0)
    for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"):
        keys[c], keys[c.upper()] = (29 + i, 0), (29 + i, SHIFT)
    symbols = ",.`-=[]\\;'/"
    for c, code in zip(symbols, (55, 56, 68, 69, 70, 71, 72, 73, 74, 75, 76)):
        keys[c] = (code, 0)
    for c, base in zip(")!@#$%^&*(" + "<>~_+{}|:\"?", "0123456789" + symbols):
        keys[c] = (keys[base][0], SHIFT)
    return keys


US_KEYS = _us_keys()


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

    def _u2_device(self) -> Any:
        if self._u2 is None:
            import uiautomator2  # only needed for text input

            self._u2 = uiautomator2.connect(self.serial)
        return self._u2

    def _paste_text(self, text: str) -> None:
        self._u2_device().send_keys(text)

    def _type_keys(self, text: str) -> None:
        """ASCII, one key event per character, type_delay apart (each takes ~0.15 s anyway)."""
        u2 = self._u2_device()  # connected before the first key's wait: the first connection takes ~3.4 s
        self.before_first_key()

        def send(ch: str) -> None:
            key = US_KEYS.get(ch)
            if key is None:  # a control character without a key: paste it
                u2.send_keys(ch)
            else:
                u2.press(*key)

        paced(text, self.type_delay, send)

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
            if self.type_delay > 0 and text.isascii():
                self._type_keys(text)  # key events: nothing goes through the clipboard
            elif action.get("secret") and text.isascii():
                self._adb(["shell", "input text " + shlex.quote(text.replace(" ", "%s"))])
            elif text:
                self._paste_text(text)  # all at once (non-ASCII text whatever the typing delay)
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
