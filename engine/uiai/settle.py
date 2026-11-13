"""Screen settling: after an action, wait for the screen to CHANGE, then to be STILL.

Without the change-wait, a still-unchanged screen right after a tap looks "settled".
Thresholds were tuned in the prototype (commit 225da4f; see docs/design/ai-loop-redesign.md 4.x):
  - `changed`: > 20 differing pixels (typed characters and toggles count as a change)
  - `same`: <= max(50, 0.03% of the area) differing pixels (a blinking text cursor is
    still "same", a spinner is not)
  - a pixel differs if its grayscale difference is > 24
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from typing import Callable

from PIL import Image, ImageChops


@dataclass
class Observation:
    jpeg: bytes
    width: int
    height: int
    changed: bool | None   # did the screen change after the last action? (None: no action before)
    black: bool            # (almost) entirely black, e.g. a FLAG_SECURE screen on Android
    polls: int
    seconds: float


class Settler:
    poll_interval = 0.1    # min interval between frames (fast grabbers would otherwise see slow animations as still)
    stable_frames = 2      # consecutive "same" comparisons required (= still for >= ~0.2 s)
    change_timeout = 2.0
    stable_timeout = 3.0

    def __init__(self, ignore_top: float = 0.0, ignore_right: float = 0.0):
        self.ignore_top = ignore_top   # top fraction ignored (status bar clock etc.)
        # right fraction ignored: Android/iOS show a scroll indicator for ~1 s after the content
        # stopped, which made the stale check re-ask the AI for nothing (phase 3)
        self.ignore_right = ignore_right
        self.acted = False
        self.acted_at: float | None = None  # when the last screen action ended (None: none since the start/a reset)
        self.shot_at: float | None = None   # when the last settled frame was grabbed
        self.not_before = 0.0               # the next settled frame is grabbed no earlier than this (see hold)
        self._last = None              # cropped grayscale of the last settled frame

    # -- pixel comparison ---------------------------------------------------
    def _gray(self, im: Image.Image) -> Image.Image:
        top = int(im.height * self.ignore_top)
        right = im.width - int(im.width * self.ignore_right)
        return im.crop((0, top, right, im.height)).convert("L")

    @staticmethod
    def _diff_px(a: Image.Image, b: Image.Image) -> int:
        return ImageChops.difference(a, b).point(lambda p: 255 if p > 24 else 0).histogram()[255]

    def same(self, a: Image.Image, b: Image.Image) -> bool:
        return self._diff_px(a, b) <= max(50, int(b.width * b.height * 0.0003))

    def changed(self, a: Image.Image, b: Image.Image) -> bool:
        return self._diff_px(a, b) > 20

    # -- public -------------------------------------------------------------
    def mark_acted(self) -> None:
        self.acted = True
        self.acted_at = time.time()

    def forget(self) -> None:
        """Drop the reference frame (e.g. after a reset)."""
        self._last = None
        self.acted = False
        self.acted_at = self.shot_at = None
        self.not_before = 0.0

    def hold(self, until: float) -> None:
        """Grab the next settled frame no earlier than `until` (a time.time() value). The settling runs
        meanwhile, so its time is not added on top. Of several holds, the latest one counts."""
        self.not_before = max(self.not_before, until)

    def wait_out(self) -> None:
        """Sleep until a pending hold is over (when something else than a screenshot comes next, e.g. a reset)."""
        left = self.not_before - time.time()
        if left > 0:
            time.sleep(left)

    def settle(self, grab: Callable[[], Image.Image]) -> Observation:
        want_change = self.acted and self._last is not None
        acted, self.acted = self.acted, False
        saw_change: bool | None = None if not acted or self._last is None else False
        begin = start = time.time()
        prev, polls, still = None, 0, 0
        while True:
            t0 = time.time()
            im = grab()
            g = self._gray(im)
            polls += 1
            elapsed = time.time() - start
            if want_change:
                if self.changed(self._last, g):
                    want_change, saw_change = False, True
                elif elapsed > self.change_timeout:
                    want_change = False
                prev = g
            else:
                still = still + 1 if prev is not None and self.same(prev, g) else 0
                if still >= self.stable_frames or elapsed > self.change_timeout + self.stable_timeout:
                    if t0 >= self.not_before:
                        break
                    # Settled before the hold is over: look again once it is, without polling meanwhile. A
                    # frame like this one then ends it; a changed one starts the stillness check over (with
                    # stable_timeout counted from there).
                    time.sleep(max(0.0, self.not_before - time.time()))
                    start, still = time.time() - self.change_timeout, self.stable_frames - 1
                prev = g
            time.sleep(max(0.0, self.poll_interval - (time.time() - t0)))
        if saw_change is False and self._last is not None and not self.same(self._last, g):
            saw_change = True  # changed slowly (below the change threshold per frame)
        self._last, self.shot_at = g, t0
        out = io.BytesIO()
        im.save(out, "JPEG", quality=80)
        lo, hi = g.getextrema()
        return Observation(out.getvalue(), im.width, im.height, saw_change, hi <= 12,
                           polls, round(time.time() - begin, 2))

    def is_stale(self, grab: Callable[[], Image.Image]) -> bool:
        """True if the screen changed since the frame the AI judged (e.g. a popup appeared meanwhile)."""
        if self._last is None:
            return False
        return not self.same(self._last, self._gray(grab()))

    def watch(self, grab: Callable[[], Image.Image], seconds: float) -> bool:
        """Keep looking for `seconds`. True if the screen changed from the last settled frame."""
        if self._last is None or seconds <= 0:
            return False
        end = time.time() + seconds
        while time.time() < end:
            t0 = time.time()
            if not self.same(self._last, self._gray(grab())):
                return True
            time.sleep(max(0.0, self.poll_interval - (time.time() - t0)))
        return False
