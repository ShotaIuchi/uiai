from __future__ import annotations

import pytest

from uiai.drivers.web import playwright_key


@pytest.mark.parametrize("given, expected", [
    ("cmd+a", "ControlOrMeta+a"),
    ("Control+a", "ControlOrMeta+a"),
    ("ctrl+shift+z", "ControlOrMeta+Shift+z"),
    ("enter", "Enter"),
    ("Return", "Enter"),
    ("esc", "Escape"),
    ("down", "ArrowDown"),
    ("f5", "F5"),
    ("PageDown", "PageDown"),
    ("a", "a"),
    ("+", "+"),
])
def test_ai_key_names_become_playwright_key_names(given, expected):
    assert playwright_key(given) == expected
