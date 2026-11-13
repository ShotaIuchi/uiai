"""iOS simulator (Mac only): screenshots with `xcrun simctl`, touch and keys with AXe.

AXe (https://github.com/cameroncooke/AXe) takes coordinates in points; the screenshot is in
pixels. The image sent to the AI is scaled to `width` pixels wide and converted to points here.

Text input uses AXe's hardware-keyboard events, which follow the US layout: only ASCII can be
typed. On a simulator whose keyboard is Japanese romaji, plain key presses turn into kana, so
the 英数 (LANG2) key is pressed first to switch the hardware keyboard to alphanumeric input.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import time
from typing import Any

from PIL import Image

from .base import Driver, DriverError, paced

# HID usage codes (keyboard page)
KEYS = {"enter": 40, "return": 40, "escape": 41, "esc": 41, "backspace": 42, "delete": 42, "tab": 43,
        "space": 44, "right": 79, "left": 80, "down": 81, "up": 82}
LANG2 = 145  # 英数: alphanumeric input on a Japanese keyboard; ignored by other layouts

AXE_HINT = "brew install cameroncooke/axe/axe"


def booted_simulators() -> list[dict]:
    """Booted iOS simulators as dicts with `udid` and `name`."""
    if not shutil.which("xcrun"):
        return []
    try:
        r = subprocess.run(["xcrun", "simctl", "list", "devices", "booted", "-j"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=20)
        data = json.loads(r.stdout or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return []
    out = []
    for runtime, devs in data.get("devices", {}).items():
        if "iOS" not in runtime:
            continue
        out += [{"udid": d["udid"], "name": d.get("name", "")} for d in devs if d.get("state") == "Booted"]
    return out


class IOSDriver(Driver):
    platform = "ios"
    description = "an iPhone (iOS simulator)"

    def __init__(self, udid: str | None = None, width: int = 540):
        super().__init__(ignore_top=0.06, ignore_right=0.02)  # status bar, Dynamic Island; scroll indicator
        if not shutil.which("xcrun"):
            raise DriverError("xcrun が見つからない（iOS は Mac と Xcode が必要）")
        if not shutil.which("axe"):
            raise DriverError(f"AXe が見つからない（iOS シミュレータの操作に使う。入れ方: {AXE_HINT}）")
        booted = booted_simulators()
        if udid:
            if udid not in {d["udid"] for d in booted}:
                raise DriverError(f"iOS シミュレータ {udid} が起動していない（xcrun simctl boot {udid}）。"
                                  "iPhone なら USB でつながっていない")
        elif not booted:
            raise DriverError("起動中の iOS シミュレータも、USB でつながった iPhone もない"
                              "（Simulator.app で起動するか、iPhone を USB でつなぐ）")
        elif len(booted) > 1:
            names = ", ".join(f"{d['name']} ({d['udid']})" for d in booted)
            raise DriverError(f"起動中の iOS シミュレータが複数ある。--udid で選ぶ: {names}")
        self.udid = udid or booted[0]["udid"]
        raw = self._grab_raw()
        self.w, self.h = raw.size
        self.pw, self.ph = self._point_size()
        self.iw, self.ih = width, round(self.h * width / self.w)
        self.to_pt = self.pw / width  # AI image pixels -> points

    # -- helpers ---------------------------------------------------------------
    def _run(self, args: list[str], timeout: float = 30, stdin: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, input=stdin)

    def _axe(self, *args: str, stdin: str | None = None) -> str:
        r = self._run(["axe", *args, "--udid", self.udid], stdin=stdin)
        if r.returncode != 0:
            raise RuntimeError(f"axe {args[0]}: {(r.stderr or r.stdout).strip()[:200]}")
        return r.stdout

    def _simctl(self, *args: str) -> subprocess.CompletedProcess:
        return self._run(["xcrun", "simctl", *args])

    def _grab_raw(self) -> Image.Image:
        r = subprocess.run(["xcrun", "simctl", "io", self.udid, "screenshot", "--type=png", "-"],
                           capture_output=True, timeout=30)
        if r.returncode != 0 or not r.stdout:
            raise DriverError("スクリーンショットを取得できない（xcrun simctl io screenshot）")
        return Image.open(io.BytesIO(r.stdout)).convert("RGB")

    def _point_size(self) -> tuple[float, float]:
        """Screen size in points, from the root of the accessibility tree (fallback: @3x)."""
        try:
            tree = json.loads(self._axe("describe-ui"))
            root = tree[0] if isinstance(tree, list) else tree
            f = root.get("frame") or {}
            if f.get("width") and f.get("height"):
                return float(f["width"]), float(f["height"])
        except Exception:  # noqa: BLE001
            pass
        return self.w / 3, self.h / 3

    def _pt(self, x: float, y: float) -> tuple[str, str]:
        return f"{x * self.to_pt:.1f}", f"{y * self.to_pt:.1f}"

    # -- driver contract -------------------------------------------------------
    def grab(self) -> Image.Image:
        return self._grab_raw().resize((self.iw, self.ih))

    def reset(self, app: str, config: Any) -> None:
        for bundle in [app, *getattr(config, "reset", [])]:
            self._simctl("terminate", self.udid, bundle)  # fails harmlessly when not running
        try:
            self._axe("button", "home")
        except Exception:  # noqa: BLE001
            pass
        self.settler.forget()

    def stop_app(self, app: str) -> None:
        self._simctl("terminate", self.udid, app)

    def _tap(self, action: dict) -> bool:
        p = self.xy(action)
        if p is None:
            return False
        x, y = self._pt(*p)
        # "physical" sends a real touch down/up. AXe's default ("automatic") falls back to a
        # simulator tap when it can't tell a switch is under the point, and switches such as
        # Settings > Developer > Dark Appearance ignore that tap.
        self._axe("tap", "-x", x, "-y", y, "--tap-style", "physical")
        return True

    def _do(self, action: dict, app: str) -> str:
        t = action.get("type")
        if t == "tap":
            if not self._tap(action):
                return f"error: tap に座標がない {action}"
        elif t == "input":
            text = str(action.get("text", ""))
            if not text.isascii():
                return "error: iOS の文字入力は ASCII のみ対応（日本語入力は未対応）"
            if self._tap(action):
                time.sleep(0.5)  # let the field take focus
            self._axe("key", str(LANG2))
            if self.type_delay > 0:  # AXe has no typing delay: one call per character
                self.before_first_key()
                paced(text, self.type_delay, lambda ch: self._axe("type", "--stdin", stdin=ch))
            else:
                self._axe("type", "--stdin", stdin=text)
        elif t == "key":
            key = str(action.get("key", "")).strip().lower()
            if key == "home":
                self._axe("button", "home")
            elif key in KEYS or key.isdigit():
                self._axe("key", str(KEYS.get(key, key)))
            else:
                return f"error: 未知のキー {key}"
        elif t == "back":
            # iOS has no back key; the edge swipe is the system back gesture in navigation views
            self._axe("gesture", "swipe-from-left-edge")
        elif t == "scroll":
            d = action.get("direction", "down")
            cx, cy = self.pw / 2, self.ph / 2
            if d in ("left", "right"):
                x1, x2 = (self.pw * 0.8, self.pw * 0.2) if d == "left" else (self.pw * 0.2, self.pw * 0.8)
                pts = (x1, cy, x2, cy)
            else:
                y1, y2 = (0.7, 0.3) if d == "down" else (0.3, 0.7)
                pts = (cx, self.ph * y1, cx, self.ph * y2)
            self._axe("swipe", "--start-x", f"{pts[0]:.1f}", "--start-y", f"{pts[1]:.1f}",
                      "--end-x", f"{pts[2]:.1f}", "--end-y", f"{pts[3]:.1f}")
        elif t == "launch":
            r = self._simctl("launch", self.udid, app)
            if r.returncode != 0:
                return f"error: 起動できない（{app}）: {(r.stderr or r.stdout).strip()[:150]}"
        elif t in ("none", "fail"):
            pass
        else:
            return f"error: 未知の操作 {t}"
        return "ok"
