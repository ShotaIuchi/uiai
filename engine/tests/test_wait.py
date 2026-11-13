"""Scenario `wait` and the AI's "wait" action, with a fake clock: both set the earliest time of the next
screenshot instead of sleeping on the spot, and the settling runs meanwhile."""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from conftest import FakeClock
from uiai import settle as settle_mod
from uiai.drivers import base as base_mod
from uiai.drivers.base import Driver

GRAB_S = 0.05  # how long one screenshot takes


def screen(label: int) -> Image.Image:
    im = Image.new("RGB", (100, 80), "white")
    ImageDraw.Draw(im).rectangle((10, 10, 20 + 10 * label, 60), fill="black")  # 500 px more per label
    return im


class ScreenDriver(Driver):
    """Shows `label` from each `(time, label)` of the timeline on (relative to the start); actions are instant."""
    platform = "web"
    description = "a test screen"

    def __init__(self, clock: FakeClock, timeline: list[tuple[float, int]]):
        super().__init__()
        self.clock, self.t0 = clock, clock.now
        self.timeline = timeline
        self.iw, self.ih = 100, 80
        self.grabs: list[float] = []   # when each screenshot started, relative to the start

    def grab(self) -> Image.Image:
        rel = self.clock.now - self.t0
        self.grabs.append(rel)
        label = [lab for t, lab in self.timeline if t <= rel + 1e-9][-1]
        self.clock.now += GRAB_S
        return screen(label)

    def _do(self, action: dict, app: str) -> str:
        return "ok"

    def shows(self, label: int) -> bool:
        """Whether the last settled frame is `label`."""
        s = self.settler
        return s.same(s._last, s._gray(screen(label)))


@pytest.fixture
def fake_time(monkeypatch):
    c = FakeClock()
    monkeypatch.setattr(settle_mod, "time", c)
    monkeypatch.setattr(base_mod, "time", c)
    return c


def tap(drv: Driver) -> float:
    """Tap and return when it ended (relative to the start)."""
    assert drv.act({"type": "tap", "x": 1, "y": 1}, "app") == "ok"
    return drv.clock.now - drv.t0


def test_scenario_wait_counts_from_the_action_and_the_settling_runs_meanwhile(fake_time):
    drv = ScreenDriver(fake_time, [(0, 0), (1.2, 1)])  # the tap's effect shows 0.2 s after it
    drv.observe()
    fake_time.now = drv.t0 + 1.0
    t_act = tap(drv)
    drv.wait_after_action(1.0)
    obs = drv.observe()
    assert obs.changed is True and drv.shows(1)
    shot = drv.settler.shot_at - drv.t0
    assert shot == pytest.approx(t_act + 1.0)              # not before the wait is over...
    assert fake_time.now - drv.t0 == pytest.approx(t_act + 1.0 + GRAB_S)  # ...and only 1 screenshot after it
    # settled ~0.5 s after the tap; no polling from then until the wait is over
    assert not [t for t in drv.grabs if t_act + 0.6 < t < t_act + 1.0 - 1e-9]


def test_a_change_during_the_wait_is_settled_again(fake_time):
    drv = ScreenDriver(fake_time, [(0, 0), (1.2, 1), (2.5, 2)])  # a second change while waiting
    drv.observe()
    fake_time.now = drv.t0 + 1.0
    t_act = tap(drv)
    drv.wait_after_action(2.0)
    drv.observe()
    assert drv.shows(2)
    assert drv.settler.shot_at - drv.t0 > t_act + 2.0     # the screenshot after the wait changed: settled anew


def test_waits_do_not_add_up_and_count_from_the_last_action(fake_time):
    drv = ScreenDriver(fake_time, [(0, 0)])
    drv.observe()
    t_act = tap(drv)
    fake_time.now += 0.7                                   # time passes after the action (e.g. the AI)
    drv.wait_after_action(2.0)                             # the `do`'s wait
    drv.wait_after_action(1.0)                             # the `then`'s wait: shorter, no effect
    assert drv.settler.not_before - drv.t0 == pytest.approx(t_act + 2.0)
    drv.observe()
    assert drv.settler.shot_at - drv.t0 >= t_act + 2.0 - 1e-9


def test_without_an_action_since_a_reset_the_wait_counts_from_now(fake_time):
    drv = ScreenDriver(fake_time, [(0, 0)])
    drv.observe()
    tap(drv)
    drv.settler.forget()                                   # what a driver's reset does
    fake_time.now += 5.0
    drv.wait_after_action(1.0)
    assert drv.settler.not_before == pytest.approx(fake_time.now + 1.0)


def test_ai_wait_counts_from_the_screenshot_the_ai_saw(fake_time):
    drv = ScreenDriver(fake_time, [(0, 0)])
    drv.observe()
    shot = drv.settler.shot_at
    fake_time.now += 1.2                                   # the AI took 1.2 s to answer "wait"
    before = fake_time.now
    assert drv.act({"type": "wait"}, "app") == "ok"
    assert fake_time.now == before                         # no sleep on the spot
    drv.observe()
    assert fake_time.now - before < 0.5                    # only the settling: 1 s since the shot has passed

    shot = drv.settler.shot_at
    fake_time.now += 0.3                                   # a fast answer
    drv.act({"type": "wait"}, "app")
    drv.observe()
    assert drv.settler.shot_at >= shot + drv.wait_s - 1e-9
    assert drv.settler.acted_at is None                    # "wait" is not a screen action


def test_wait_out_sleeps_until_the_wait_is_over(fake_time):
    drv = ScreenDriver(fake_time, [(0, 0)])
    drv.observe()
    t_act = tap(drv)
    drv.wait_after_action(3.0)
    fake_time.now += 1.0
    drv.wait_out()
    assert fake_time.now - drv.t0 == pytest.approx(t_act + 3.0)
    drv.wait_out()                                         # nothing left
    assert fake_time.now - drv.t0 == pytest.approx(t_act + 3.0)
