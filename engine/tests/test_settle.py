from __future__ import annotations

from PIL import Image, ImageDraw

from uiai.settle import Settler


def frame(bar: bool) -> Image.Image:
    im = Image.new("RGB", (540, 1200), "white")
    if bar:  # a scroll indicator along the right edge
        ImageDraw.Draw(im).rectangle((533, 300, 537, 1000), fill="black")
    return im


def test_scroll_indicator_on_right_edge_is_ignored():
    s = Settler(ignore_top=0.03, ignore_right=0.02)
    assert s.same(s._gray(frame(True)), s._gray(frame(False)))


def test_right_edge_counts_without_ignore():
    s = Settler(ignore_top=0.03)
    assert not s.same(s._gray(frame(True)), s._gray(frame(False)))
