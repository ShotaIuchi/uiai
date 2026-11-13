"""Platform drivers: capture, tap, type, key, scroll, back, launch, reset."""

from __future__ import annotations

from .base import Driver, DriverError


def make_driver(platform: str, *, serial: str | None = None, udid: str | None = None, team: str | None = None,
                browser_path: str | None = None, headed: bool = False) -> Driver:
    if platform == "android":
        from .android import AndroidDriver
        return AndroidDriver(serial)
    if platform == "web":
        from .web import WebDriver
        return WebDriver(executable=browser_path, headed=headed)
    if platform == "ios":
        return _ios_driver(udid, team)
    raise DriverError(f"未知のプラットフォーム: {platform}")


def _ios_driver(udid: str | None, team: str | None) -> Driver:
    """The USB iPhone or booted simulator named by `udid`, else the only one there is (an iPhone wins only
    when no simulator is booted: with both, --udid decides)."""
    from .ios import IOSDriver, booted_simulators
    from .ios_device import IOSDeviceDriver, usb_devices
    from .usbmux import normalize_udid

    devices = usb_devices()
    if udid:
        if any(normalize_udid(d["udid"]) == normalize_udid(udid) for d in devices):
            return IOSDeviceDriver(udid, team)
        return IOSDriver(udid)
    if devices:
        sims = booted_simulators()
        if sims:
            names = [f"{d['udid']}（iPhone・USB）" for d in devices] + [f"{s['udid']}（{s['name']}）" for s in sims]
            raise DriverError("USB でつながった iPhone と、起動中の iOS シミュレータの両方がある。--udid で選ぶ: "
                              + ", ".join(names))
        return IOSDeviceDriver(None, team)
    return IOSDriver(None)


__all__ = ["Driver", "DriverError", "make_driver"]
