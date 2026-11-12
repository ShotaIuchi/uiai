"""Platform drivers: capture, tap, type, key, scroll, back, launch, reset."""

from __future__ import annotations

from .base import Driver, DriverError


def make_driver(platform: str, *, serial: str | None = None, udid: str | None = None,
                browser_path: str | None = None, headed: bool = False) -> Driver:
    if platform == "android":
        from .android import AndroidDriver
        return AndroidDriver(serial)
    if platform == "web":
        from .web import WebDriver
        return WebDriver(executable=browser_path, headed=headed)
    if platform == "ios":
        from .ios import IOSDriver
        return IOSDriver(udid)
    raise DriverError(f"未知のプラットフォーム: {platform}")


__all__ = ["Driver", "DriverError", "make_driver"]
