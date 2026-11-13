"""Which platform(s) to run a scenario on (design doc 11.1)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .scenario import PLATFORMS, is_web_target

LABEL = {"android": "Android", "ios": "iOS", "web": "Web"}


class PlatformError(Exception):
    pass


def candidates(app: Any) -> list[str]:
    """Platforms the scenario's `app` allows.

    A plain string that is not a URL/.html means "the same identifier on Android and iOS"
    (existing schema), so both are candidates.
    """
    if isinstance(app, dict):
        return [p for p in PLATFORMS if p in app]
    if is_web_target(str(app)):
        return ["web"]
    return ["android", "ios"]


def _run(cmd: list[str], timeout: float = 15) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def android_serials() -> list[str]:
    if not shutil.which("adb"):
        return []
    return [ln.split("\t")[0] for ln in _run(["adb", "devices"]).splitlines()[1:] if ln.endswith("\tdevice")]


def booted_udids() -> list[str]:
    if sys.platform != "darwin":
        return []
    from .drivers.ios import booted_simulators

    return [d["udid"] for d in booted_simulators()]


def ios_device_udids() -> list[str]:
    """iPhones attached by USB (Mac only)."""
    from .drivers.ios_device import usb_devices

    return [d["udid"] for d in usb_devices()]


def ios_udids() -> list[str]:
    """Everything iOS that can run now: USB iPhones, then booted simulators."""
    return ios_device_udids() + booted_udids()


def _as_list(v: str | list[str] | None) -> list[str]:
    return [] if not v else [v] if isinstance(v, str) else list(v)


def probe(serial: str | list[str] | None = None, udid: str | list[str] | None = None) -> dict[str, bool]:
    """What can run right now: connected Android device, USB iPhone or booted iOS simulator, Web (always).
    With serials/UDIDs given, at least one of them must be available (the others fail when opened)."""
    from .drivers.usbmux import normalize_udid

    want_s, want_u = _as_list(serial), _as_list(udid)
    serials, ios = android_serials(), {normalize_udid(u) for u in ios_udids()}
    return {"android": any(s in serials for s in want_s) if want_s else bool(serials),
            "ios": any(normalize_udid(u) in ios for u in want_u) if want_u else bool(ios),
            "web": True}


def resolve(app: Any, requested: str | None, available: dict[str, bool], ons: Any = ()) -> list[str]:
    """The platform(s) the run is for. `ons`: each section's `on` (None: the run's platform). The platforms
    named there have to be available too, and when choosing automatically they are not candidates for the
    run itself (an Android test with a Web section runs on Android). If every section names one, the run is
    for the first section's."""
    ons = list(ons)
    side = {o for o in ons if o}
    cands = candidates(app)
    names = "・".join(LABEL[p] for p in cands)
    if requested and requested != "all":
        if requested not in cands:
            raise PlatformError(f"シナリオの `app` は {names} 向けで、{LABEL.get(requested, requested)} では実行できない")
        if not available.get(requested):
            raise PlatformError(f"{LABEL[requested]} の実行対象が見つからない（{_hint(requested)}）")
        _check_side(requested, side, available)
        return [requested]
    main = _main(cands, ons)
    usable = [p for p in main if available.get(p)]
    if not usable:
        raise PlatformError(f"実行できる対象がない（候補: {'・'.join(LABEL[p] for p in main)}。"
                            + "、".join(_hint(p) for p in main) + "）")
    if requested == "all" or len(usable) == 1:
        for p in usable:
            _check_side(p, side, available)
        return usable
    raise PlatformError(f"複数のプラットフォームで実行できる（{'・'.join(LABEL[p] for p in usable)}）。"
                        "--platform で 1 つ選ぶか、all を指定する")


def _main(cands: list[str], ons: list) -> list[str]:
    """The candidates for the run itself, before looking at what is available (see resolve)."""
    if ons and all(ons):
        return [ons[0]]
    side = {o for o in ons if o}
    return [p for p in cands if p not in side] or cands


def default_platform(app: Any, ons: Any) -> str | None:
    """The platform a run without --platform is for, if only one is possible."""
    main = _main(candidates(app), list(ons))
    return main[0] if len(main) == 1 else None


def _check_side(main: str, side: Any, available: dict[str, bool]) -> None:
    for p in sorted(set(side) - {main}):
        if not available.get(p):
            raise PlatformError(f"`on: {p}` のセクションがあるが、{LABEL[p]} の実行対象が見つからない（{_hint(p)}）")


def _hint(p: str) -> str:
    return {"android": "Android 端末・エミュレータを adb で接続する",
            "ios": "iOS シミュレータを起動するか、iPhone を USB でつなぐ（Mac のみ。シミュレータの操作には AXe が要る）",
            "web": ""}[p]


def target(app: Any, platform: str, scenario_dir: Path) -> str:
    """The app identifier for the platform. Web paths are resolved relative to the scenario file."""
    raw = str(app[platform] if isinstance(app, dict) else app)
    if platform != "web" or re.match(r"^[a-z][a-z0-9+.-]+:", raw, re.I):
        return raw
    m = re.match(r"^([^?#]*)(.*)$", raw)
    path, rest = m.group(1), m.group(2)
    return (scenario_dir / path).resolve().as_uri() + rest
