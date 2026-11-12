"""Driver contract shared by all platforms.

Coordinates in actions are in the coordinates of the screenshot sent to the AI;
each driver converts them to device coordinates.
"""

from __future__ import annotations

from typing import Any

from PIL import Image

from ..settle import Observation, Settler

# Actions that change (or may change) the screen; the next observation waits for a change first.
SCREEN_ACTIONS = ("tap", "input", "key", "back", "scroll", "launch")
# Actions aimed at what the AI saw; skipped if the screen changed meanwhile.
STALE_CHECKED = ("tap", "input", "key", "back", "scroll")
STALE = "stale"


class DriverError(Exception):
    """The environment is not usable (device missing, browser not installed...)."""


class Driver:
    platform = ""           # "android" | "web"
    description = ""        # for the AI prompt, e.g. "an Android device"
    detect_black = False    # report an all-black screen instead of letting the AI guess
    wait_s = 1.0            # duration of a "wait" action
    iw = ih = 0             # size of the screenshot sent to the AI

    def __init__(self, ignore_top: float = 0.0):
        self.settler = Settler(ignore_top)

    # -- to implement --------------------------------------------------------
    def grab(self) -> Image.Image:
        """Current screen as an RGB image of size (iw, ih)."""
        raise NotImplementedError

    def reset(self, app: str, config: Any) -> None:
        """Clean start state before a scenario (or a section with on_failure=next_section)."""

    def stop_app(self, app: str) -> None:
        pass

    def close(self) -> None:
        pass

    def _do(self, action: dict, app: str) -> str:
        """Perform one action; return "ok" or an error description."""
        raise NotImplementedError

    # -- common --------------------------------------------------------------
    def observe(self) -> Observation:
        return self.settler.settle(self.grab)

    def watch(self, seconds: float) -> bool:
        return self.settler.watch(self.grab, seconds)

    def act(self, action: dict, app: str, check_stale: bool = False) -> str:
        """Perform an action. With check_stale, a screen that changed after the AI's screenshot
        (a popup appeared during the ~1 s the AI took) is reported as "stale" and nothing is done."""
        t = action.get("type")
        if check_stale and t in STALE_CHECKED:
            try:
                if self.settler.is_stale(self.grab):
                    return STALE
            except Exception:  # noqa: BLE001 - the action itself will report problems
                pass
        try:
            result = self._do(action, app)
        except Exception as e:  # noqa: BLE001 - report to the log and the AI, keep going
            result = f"error: {str(e)[:200]}"
        if t in SCREEN_ACTIONS:
            self.settler.mark_acted()
        return result

    @staticmethod
    def xy(action: dict) -> tuple[float, float] | None:
        try:
            return float(action["x"]), float(action["y"])
        except (KeyError, TypeError, ValueError):
            return None
