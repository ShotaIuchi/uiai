"""Driver contract shared by all platforms.

Coordinates in actions are in the coordinates of the screenshot sent to the AI;
each driver converts them to device coordinates.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable, TypeVar

from PIL import Image

from ..settle import Observation, Settler

# Actions that change (or may change) the screen; the next observation waits for a change first.
SCREEN_ACTIONS = ("tap", "input", "key", "back", "scroll", "launch")
# Actions aimed at what the AI saw; skipped if the screen changed meanwhile.
STALE_CHECKED = ("tap", "input", "key", "back", "scroll")
STALE = "stale"


T = TypeVar("T")


class DriverError(Exception):
    """The environment is not usable (device missing, browser not installed...)."""


def paced(items: Iterable[T], interval: float, send: Callable[[T], object]) -> None:
    """send() each item, starting each one no earlier than `interval` seconds after the previous one started.
    A send that takes longer than the interval is not followed by an extra pause."""
    due = 0.0
    for item in items:
        now = time.time()
        if now < due:
            time.sleep(due - now)
            now = due
        send(item)
        due = now + interval


class Driver:
    platform = ""           # "android" | "web"
    description = ""        # for the AI prompt, e.g. "an Android device"
    detect_black = False    # report an all-black screen instead of letting the AI guess
    wait_s = 1.0            # a "wait" action: the next screenshot is this long after the one the AI saw
    type_delay = 0.0        # seconds between typed characters (config.type_delay, --type-delay); 0 = fastest
    iw = ih = 0             # size of the screenshot sent to the AI

    def __init__(self, ignore_top: float = 0.0, ignore_right: float = 0.0):
        self.settler = Settler(ignore_top, ignore_right)

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

    def wait_after_action(self, seconds: float) -> None:
        """Scenario `wait`: take the next screenshot no earlier than `seconds` after the last screen action
        ended (from now if there was none since the start or a reset). The settling runs meanwhile."""
        if seconds > 0:
            since = self.settler.acted_at
            self.settler.hold((since if since is not None else time.time()) + seconds)

    def wait_out(self) -> None:
        """Sleep until a pending `wait` is over, before something else than a screenshot (a reset, the end)."""
        self.settler.wait_out()

    def before_first_key(self) -> None:
        """With a typing delay, the first key also comes `type_delay` after what was done before it (the tap on
        the field...). On an Android emulator, a key sent right after the field was cleared was dropped now and
        then (1 in 4 runs); `input text`, whose first key comes ~0.5 s later, never dropped it."""
        if self.type_delay > 0:
            time.sleep(self.type_delay)

    def act(self, action: dict, app: str, check_stale: bool = False) -> str:
        """Perform an action. With check_stale, a screen that changed after the AI's screenshot
        (a popup appeared during the ~1 s the AI took) is reported as "stale" and nothing is done."""
        t = action.get("type")
        if t == "wait":
            # The AI wants a fresher screen. Answering took it about 1 s already, so the time counts from
            # the screenshot it saw: usually nothing is left to wait.
            shot = self.settler.shot_at
            self.settler.hold((shot if shot is not None else time.time()) + self.wait_s)
            return "ok"
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
