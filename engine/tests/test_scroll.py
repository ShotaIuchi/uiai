"""scroll: where the finger goes (from the AI's x,y), and which way (where the view moves)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from uiai.ai.protocol import Ask, build_message, system_prompt
from uiai.drivers.android import AndroidDriver
from uiai.drivers.base import Driver
from uiai.drivers.web import WebDriver

W, H = 1000, 2000


def swipe(**action):
    return Driver.swipe({"type": "scroll", **action}, W, H, 2.0)


@pytest.mark.parametrize("direction, path", [
    ("down", (500, 1400, 500, 600)),   # what is below comes into view: the finger moves up
    ("up", (500, 600, 500, 1400)),
    ("right", (800, 1000, 200, 1000)),  # what is on the right: a swipe to the left
    ("left", (200, 1000, 800, 1000)),
])
def test_without_x_y_the_finger_moves_through_the_middle_of_the_screen(direction, path):
    assert swipe(direction=direction) == pytest.approx(path)


def test_no_direction_is_down_and_0_0_is_no_point():
    assert swipe() == pytest.approx(swipe(direction="down"))
    assert swipe(direction="left", x=0, y=0) == pytest.approx(swipe(direction="left"))  # filled in, not meant


def test_the_finger_starts_at_the_point_the_ai_gave():
    # a row of chips near the top, scrolled sideways: not the list in the middle of the screen
    assert swipe(direction="right", x=250, y=150) == pytest.approx((500, 300, 50, 300))
    # a bottom sheet pulled down to close it
    assert swipe(direction="up", x=250, y=700) == pytest.approx((500, 1400, 500, 1900))  # short of the edge
    assert swipe(direction="down", x="250", y="500") == pytest.approx((500, 1000, 500, 200))


def test_the_finger_keeps_off_the_edges_and_moves_at_least_half_as_far():
    # starts off the edge (back gesture, home indicator, notifications), ends short of it
    x1, y1, x2, y2 = swipe(direction="left", x=0, y=500)
    assert (x1, y1) == pytest.approx((100, 1000)) and x2 == pytest.approx(700)
    assert swipe(direction="down", x=250, y=1000) == pytest.approx((500, 1800, 500, 1000))  # off the bottom edge
    # pulled down from the very bottom: it would hardly move, so it starts further back
    assert swipe(direction="up", x=250, y=990) == pytest.approx((500, 1500, 500, 1900))
    for d in ("down", "up", "left", "right"):
        for x, y in ((0, 0), (500, 1000), (-50, 5000)):
            x1, y1, x2, y2 = swipe(direction=d, x=x, y=y)
            assert 0.05 * W <= min(x1, x2) and max(x1, x2) <= 0.95 * W
            assert 0.05 * H <= min(y1, y2) and max(y1, y2) <= 0.95 * H
            assert abs(x2 - x1) + abs(y2 - y1) >= (0.3 * W if d in ("left", "right") else 0.2 * H) - 1e-6


def test_android_swipes_in_device_pixels_from_the_point():
    drv = AndroidDriver.__new__(AndroidDriver)
    drv.w, drv.h, drv.scale = 1080, 2400, 2.0
    sent = []
    drv._adb = lambda args: sent.append(args) or ""
    assert drv._do({"type": "scroll", "direction": "right", "x": 270, "y": 300}, "app") == "ok"
    assert drv._do({"type": "scroll", "direction": "down"}, "app") == "ok"
    assert sent[0] == ["shell", "input", "swipe", "540", "600", "54", "600", "300"]
    assert sent[1] == ["shell", "input", "swipe", "540", "1680", "540", "720", "300"]


def test_web_scrolls_what_is_under_the_point():
    moves, wheels = [], []
    page = SimpleNamespace(mouse=SimpleNamespace(move=lambda x, y: moves.append((x, y)),
                                                 wheel=lambda dx, dy: wheels.append((dx, dy))))
    drv = WebDriver.__new__(WebDriver)
    drv.iw, drv.ih, drv.page = 1280, 800, page
    drv._do({"type": "scroll", "direction": "down", "x": 300, "y": 600}, "http://x")
    drv._do({"type": "scroll", "direction": "right", "x": 5000, "y": -3}, "http://x")
    drv._do({"type": "scroll", "direction": "up"}, "http://x")
    drv._do({"type": "scroll", "direction": "left", "x": 0, "y": 0}, "http://x")
    assert moves == [(300, 600), (1279, 0), (640, 400), (640, 400)]
    assert wheels == [(0, 800 * 0.6), (1280 * 0.6, 0), (0, -800 * 0.6), (-1280 * 0.6, 0)]


def test_the_ai_is_told_what_x_y_and_direction_mean_for_a_scroll():
    s = system_prompt("a screen", 10, 10, [])
    assert "For scroll, x,y = a point in the area to scroll" in s
    assert '"direction" is where the view moves: "down" brings what is\n  below into view (the finger moves up)' in s
    assert 'use "up"' in s


def test_a_do_asked_again_is_told_so():
    m = build_message(Ask(section="A", do="save", again=True))
    assert "do: save\n(this `do` was reported done: check it on this screen" in m
    assert "then to judge now: []" in m
    assert "reported done" not in build_message(Ask(section="A", do="save"))
