"""Real iPhone on USB (Mac only), through WebDriverAgent (wda.py): screenshots, touches, typing, buttons, apps.

WDA takes coordinates in points; the screenshot is in pixels. As with the simulator, the image sent to the AI
is scaled to `width` pixels wide and converted to points here.

If WDA already answers on the iPhone (started from Xcode, or by another tool), it is used as is. Otherwise it
is built and started for the session and stopped again by close().
"""

from __future__ import annotations

import io
import os
import sys
import time
from typing import Any

from PIL import Image

from . import usbmux
from .base import Driver, DriverError
from .wda import WDA_PORT, WDAClient, WDAError, WDARunner, choose_team, wait_ready, xcode_teams

# keys that are typed as characters (WDA has no key events on iOS)
KEY_TEXT = {"enter": "\n", "return": "\n", "tab": "\t", "space": " ", "backspace": "\b", "delete": "\b",
            "escape": "\x1b", "esc": "\x1b"}


def usb_devices() -> list[dict]:
    """iPhones (and iPads) attached by USB: [{"id", "udid", "connection"}]. Empty without usbmuxd."""
    if sys.platform != "darwin":
        return []
    try:
        return [d for d in usbmux.devices() if d["connection"] == "USB"]
    except usbmux.UsbmuxError:
        return []


def pick_device(devs: list[dict], udid: str | None) -> dict:
    if udid:
        for d in devs:
            if usbmux.normalize_udid(d["udid"]) == usbmux.normalize_udid(udid):
                return d
        raise DriverError(f"iPhone {udid} が USB でつながっていない")
    if not devs:
        raise DriverError("USB でつながった iPhone がない（つないでロックを解除し、「このコンピュータを信頼」を選ぶ）")
    if len(devs) > 1:
        raise DriverError("USB でつながった iPhone が複数ある。--udid で選ぶ: " + ", ".join(d["udid"] for d in devs))
    return devs[0]


class IOSDeviceDriver(Driver):
    platform = "ios"
    description = "an iPhone"

    def __init__(self, udid: str | None = None, team: str | None = None, width: int = 540,
                 client: WDAClient | None = None):
        """client: an already connected WDA (the tests); otherwise the USB iPhone `udid` (or the only one)."""
        super().__init__(ignore_top=0.06, ignore_right=0.02)  # status bar, Dynamic Island; scroll indicator
        self.runner: WDARunner | None = None
        self.udid = udid or ""
        self.wda = client if client is not None else self._open(udid, team)
        try:
            self.wda.start_session()
            raw = self._grab_raw()
            self.pw, self.ph = self.wda.window_size()
        except (WDAError, OSError) as e:
            self.close()
            raise DriverError(f"WebDriverAgent を使えない: {e}") from e
        self.w, self.h = raw.size
        self.iw, self.ih = width, round(self.h * width / self.w)
        self.to_pt = self.pw / width  # AI image pixels -> points

    def _open(self, udid: str | None, team: str | None) -> WDAClient:
        dev = pick_device(usb_devices(), udid)
        self.udid = usbmux.xcode_udid(dev["udid"])

        def connect():
            # usbmuxd numbers a device anew when it is plugged in again: look it up for every connection
            d = next((d for d in usb_devices()
                      if usbmux.normalize_udid(d["udid"]) == usbmux.normalize_udid(self.udid)), None)
            if d is None:
                raise usbmux.UsbmuxError(f"iPhone {self.udid} が USB でつながっていない（外れた？）")
            return usbmux.connect(d["id"], WDA_PORT)

        client = WDAClient(connect)
        if client.ready():
            return client
        self.runner = WDARunner(self.udid, choose_team(xcode_teams(), team or os.environ.get("UIAI_IOS_TEAM")))
        try:
            self.runner.build()
            self.runner.start()
            wait_ready(client, self.runner)
        except BaseException:
            self.runner.stop()
            raise
        return client

    # -- helpers ---------------------------------------------------------------
    def _grab_raw(self) -> Image.Image:
        try:
            return Image.open(io.BytesIO(self.wda.screenshot())).convert("RGB")
        except (WDAError, OSError, ValueError) as e:
            raise DriverError(f"スクリーンショットを取得できない（WebDriverAgent）: {e}") from e

    def _pt(self, x: float, y: float) -> tuple[float, float]:
        return round(x * self.to_pt, 1), round(y * self.to_pt, 1)

    def _tap(self, action: dict) -> bool:
        p = self.xy(action)
        if p is None:
            return False
        self.wda.tap(*self._pt(*p))
        return True

    # -- driver contract -------------------------------------------------------
    def grab(self) -> Image.Image:
        return self._grab_raw().resize((self.iw, self.ih))

    def reset(self, app: str, config: Any) -> None:
        for bundle in [app, *getattr(config, "reset", [])]:
            try:
                self.wda.terminate(bundle)  # fails harmlessly when not running
            except WDAError:
                pass
        try:
            self.wda.home()
        except WDAError:
            pass
        self.settler.forget()

    def stop_app(self, app: str) -> None:
        self.wda.terminate(app)

    def close(self) -> None:
        try:
            if self.wda.sid:
                self.wda.call("DELETE", f"/session/{self.wda.sid}", timeout=10)
        except (WDAError, OSError):
            pass
        finally:
            self.wda.close()
            if self.runner is not None:
                self.runner.stop()

    def _do(self, action: dict, app: str) -> str:
        t = action.get("type")
        if t == "tap":
            if not self._tap(action):
                return f"error: tap に座標がない {action}"
        elif t == "input":
            if self._tap(action):
                time.sleep(0.5)  # let the field take focus
            self.wda.type_text(str(action.get("text", "")))
        elif t == "key":
            key = str(action.get("key", "")).strip().lower()
            if key == "home":
                self.wda.home()
            elif key in KEY_TEXT:
                self.wda.type_text(KEY_TEXT[key])
            else:
                return f"error: 未知のキー {key}"
        elif t == "back":
            # iOS has no back key; the edge swipe is the system back gesture in navigation views
            self.wda.drag(2, self.ph / 2, self.pw * 0.7, self.ph / 2, ms=250)
        elif t == "scroll":
            d = action.get("direction", "down")
            cx, cy = self.pw / 2, self.ph / 2
            if d in ("left", "right"):
                x1, x2 = (self.pw * 0.8, self.pw * 0.2) if d == "left" else (self.pw * 0.2, self.pw * 0.8)
                self.wda.drag(x1, cy, x2, cy)
            else:
                y1, y2 = (0.7, 0.3) if d == "down" else (0.3, 0.7)
                self.wda.drag(cx, self.ph * y1, cx, self.ph * y2)
        elif t == "launch":
            try:
                self.wda.launch(app)
            except WDAError as e:
                return f"error: 起動できない（{app}）: {str(e)[:150]}"
        elif t in ("none", "fail"):
            pass
        else:
            return f"error: 未知の操作 {t}"
        return "ok"
