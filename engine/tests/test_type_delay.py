"""Typing speed: config.type_delay / --type-delay (ms between characters) on every platform."""

from __future__ import annotations

import pytest

from test_ios_device import FakeWDA
from uiai import cli
from uiai.drivers import base
from uiai.drivers.android import US_KEYS, AndroidDriver
from uiai.drivers.ios import LANG2, IOSDriver
from uiai.drivers.ios_device import IOSDeviceDriver
from uiai.drivers.web import WebDriver
from uiai.scenario import check_file, load

STEPS = "steps: [{id: s, actions: [{do: a}, {then: b}]}]"


class Clock:
    """Fake time for paced(): sleeping and slow sends move it forward."""

    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(base, "time", c)
    return c


# ---------------------------------------------------------------- scenario


def test_config_type_delay_is_read_in_ms_and_defaults_to_fastest(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text(f"name: n\napp: com.example.app\nconfig: {{type_delay: 80}}\n{STEPS}", encoding="utf-8")
    assert load(p).config.type_delay == 80
    p.write_text(f"name: n\napp: com.example.app\n{STEPS}", encoding="utf-8")
    assert load(p).config.type_delay == 0


@pytest.mark.parametrize("value,ok", [("0", True), ("150.5", True), ("-1", False), ("fast", False), ("true", False)])
def test_config_type_delay_must_be_a_number_of_ms(tmp_path, value, ok):
    p = tmp_path / "s.yaml"
    p.write_text(f"name: n\napp: com.example.app\nconfig: {{type_delay: {value}}}\n{STEPS}", encoding="utf-8")
    issues = [i for i in check_file(p) if i.where == "config.type_delay"]
    assert (issues == []) == ok
    assert ok or issues[0].code == "E015"


# ---------------------------------------------------------------- CLI -> driver


@pytest.fixture
def run_env(tmp_path, monkeypatch):
    import uiai.drivers as drivers
    from uiai import platform
    from test_cli import FakeSession
    import uiai.ai.claude_code as cc
    from conftest import FakeDriver

    made = []

    def make_driver(p, **kw):
        made.append(FakeDriver())
        return made[-1]

    monkeypatch.setattr(drivers, "make_driver", make_driver)
    monkeypatch.setattr(cc, "ClaudeCodeSession", FakeSession)
    monkeypatch.setattr(platform, "android_serials", lambda: ["A"])
    monkeypatch.setattr(platform, "booted_udids", lambda: [])

    def run(config: str, *args: str) -> float:
        f = tmp_path / "s.yaml"
        f.write_text(f'name: S\napp: {{android: "com.example.app"}}\n{config}'
                     'steps:\n  - id: a\n    actions:\n      - do: "開く"\n      - then: "出る"\n', encoding="utf-8")
        made.clear()
        code = cli.main(["run", str(f), "--results-dir", str(tmp_path / "r"), "--rejudge-model", "none", *args])
        assert code == 0
        return made[0].type_delay

    return run


def test_the_option_overrides_the_scenario_and_reaches_the_driver_in_seconds(run_env):
    assert run_env("") == 0
    assert run_env("config: {type_delay: 120}\n") == pytest.approx(0.12)
    assert run_env("config: {type_delay: 120}\n", "--type-delay", "50") == pytest.approx(0.05)
    assert run_env("config: {type_delay: 120}\n", "--type-delay", "0") == 0  # 0 is a value, not "unset"


@pytest.mark.parametrize("bad", ["-1", "x", "nan", "inf"])
def test_the_option_needs_a_number_of_ms(bad, capsys):
    with pytest.raises(SystemExit) as e:
        cli.build_parser().parse_args(["run", "s.yaml", "--type-delay", bad])
    assert e.value.code == 2 and "ミリ秒" in capsys.readouterr().err


# ---------------------------------------------------------------- pacing


def test_keys_start_no_closer_than_the_delay_and_slow_keys_add_no_pause(clock):
    sent = []

    def send(ch):
        sent.append((ch, round(clock.now - 1000, 3)))
        clock.now += 0.15 if ch == "s" else 0.01  # "s" takes longer than the delay

    base.paced("absc", 0.1, send)
    assert sent == [("a", 0), ("b", 0.1), ("s", 0.2), ("c", 0.35)]


# ---------------------------------------------------------------- Android


class FakeU2:
    def __init__(self, clock=None):
        self.sent: list = []
        self.times: list[float] = []   # when each key was pressed (with a fake clock)
        self.clock = clock

    def press(self, code, meta=None):
        self.sent.append((code, meta))
        if self.clock:
            self.times.append(round(self.clock.now - 1000, 3))

    def send_keys(self, text):
        self.sent.append(text)


def android(delay: float, clock=None) -> tuple[AndroidDriver, FakeU2, list]:
    d = AndroidDriver.__new__(AndroidDriver)
    base.Driver.__init__(d)
    adb: list = []
    d._u2, d.type_delay, d._adb = FakeU2(clock), delay, lambda args, timeout=30: adb.append(args) or ""
    return d, d._u2, adb


def test_android_types_ascii_key_by_key_with_shift(clock):
    d, u2, adb = android(0.1)
    assert d.act({"type": "input", "text": "Hi! a_B\n\r"}, "app") == "ok"
    assert u2.sent == [(36, 1), (37, 0), (8, 1), (62, 0), (29, 0), (69, 1), (30, 1), (66, 0), "\r"]
    assert adb == [] and clock.now == pytest.approx(1000 + 0.1 * 9)  # 9 keys, the first one waits too


def test_the_first_key_also_waits_the_delay(clock):
    # a key sent right after the field was cleared was dropped now and then on an emulator
    d, u2, adb = android(0.4, clock)
    d.act({"type": "input", "text": "xyz"}, "app")
    assert u2.times == [0.4, 0.8, 1.2]


def test_android_key_table_covers_printable_ascii_on_the_us_layout():
    assert all(chr(c) in US_KEYS for c in range(0x20, 0x7F))
    assert [US_KEYS[c] for c in "aZ09)(~`|\\\"'"] == [
        (29, 0), (54, 1), (7, 0), (16, 0), (7, 1), (16, 1), (68, 1), (68, 0), (73, 1), (73, 0), (75, 1), (75, 0)]


def test_android_types_an_ascii_secret_instead_of_pasting_it(clock):
    # pasted text shows for a moment in the clipboard notice and the keyboard's suggestions
    d, u2, adb = android(0)
    d.act({"type": "input", "text": "pw 1$", "secret": True}, "app")
    d.act({"type": "input", "text": "秘密", "secret": True}, "app")  # cannot be typed: pasted
    assert adb == [["shell", "input text 'pw%s1$'"]] and u2.sent == ["秘密"]  # quoted for the device's shell
    d, u2, adb = android(0.1)
    d.act({"type": "input", "text": "Pw", "secret": True}, "app")  # with a delay, key events as for any text
    assert adb == [] and u2.sent == [(44, 1), (51, 0)]


def test_android_pastes_without_a_delay_and_non_ascii_always(clock):
    d, u2, adb = android(0)
    d.act({"type": "input", "text": "a b!"}, "app")
    d.act({"type": "input", "text": ""}, "app")  # nothing to paste: the clipboard is left alone
    assert u2.sent == ["a b!"] and adb == [] and clock.now == 1000
    d, u2, adb = android(0.1)
    d.act({"type": "input", "text": "東京 tower"}, "app")
    assert u2.sent == ["東京 tower"] and adb == []


# ---------------------------------------------------------------- iOS simulator


def test_simulator_types_one_axe_call_per_character(clock):
    d = IOSDriver.__new__(IOSDriver)
    base.Driver.__init__(d)
    calls = []
    d._axe = lambda *a, stdin=None: calls.append((a, stdin, round(clock.now - 1000, 3))) or ""
    d.type_delay = 0.2
    d.act({"type": "input", "text": "ab"}, "app")
    assert calls == [(("key", str(LANG2)), None, 0), (("type", "--stdin"), "a", 0.2), (("type", "--stdin"), "b", 0.4)]
    calls.clear()
    d.type_delay = 0
    d.act({"type": "input", "text": "ab"}, "app")
    assert [(c[1], c[2]) for c in calls] == [(None, 0.4), ("ab", 0.4)]  # no wait at all without a delay


# ---------------------------------------------------------------- iPhone (WebDriverAgent)


@pytest.fixture
def iphone():
    f = FakeWDA()
    d = IOSDeviceDriver(client=f.client())
    f.calls.clear()
    yield d, f
    f.srv.shutdown()


@pytest.mark.parametrize("delay,frequency", [(0, None), (0.1, 10), (0.3, 3), (0.35, 2), (1.0, 1)])
def test_iphone_lets_wda_pace_the_keys_in_whole_characters_per_second(iphone, clock, delay, frequency):
    d, wda = iphone
    d.type_delay = delay
    d.act({"type": "input", "text": "abc"}, "app")
    body = {"value": ["abc"], **({"frequency": frequency} if frequency else {})}
    assert wda.posts() == [("wda/keys", body)]
    assert clock.now == pytest.approx(1000 + delay)  # before the first key


def test_iphone_slower_than_one_key_a_second_sends_each_character(iphone, clock):
    d, wda = iphone
    d.type_delay = 2.5
    d.act({"type": "input", "text": "ab"}, "app")
    assert wda.posts() == [("wda/keys", {"value": ["a"]}), ("wda/keys", {"value": ["b"]})]
    assert clock.now == pytest.approx(1000 + 2.5 * 2)


# ---------------------------------------------------------------- Web


def test_web_hands_the_delay_to_playwright_in_ms(clock):
    typed = []

    class Keyboard:
        def type(self, text, delay=0):
            typed.append((text, delay, round(clock.now - 1000, 3)))

    d = WebDriver.__new__(WebDriver)
    base.Driver.__init__(d)
    d.page = type("Page", (), {"keyboard": Keyboard()})()
    d.type_delay = 0.08
    d.act({"type": "input", "text": "ab"}, "app")
    assert typed == [("ab", pytest.approx(80), 0.08)]  # the first key waits too: Playwright starts with a keydown
