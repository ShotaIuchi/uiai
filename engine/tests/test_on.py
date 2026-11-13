"""`on:` on a section: run it on another device (e.g. an Android test waits for something on the Web)."""

from __future__ import annotations

import json
import threading

import pytest

from conftest import FakeAI, FakeDriver, reply, v
from uiai import cli, platform
from uiai.events import describe
from uiai.platform import PlatformError, resolve
from uiai.redact import Redactor
from uiai.report import write_scenario
from uiai.scenario import check_file, load

SWITCH = """
name: t
app: {android: com.example.app, web: "http://w"}
steps:
  - id: A
    actions:
      - do: "send a request"
      - then: "sent"
  - id: B
    on: web
    actions:
      - do: "open the admin page"
      - then: "the request is listed"
  - id: C
    actions:
      - do: "open the result"
      - then: "approved"
"""


class Tagged(list):
    """A driver's trace that writes into one list shared by every device, tagged with the device."""

    def __init__(self, shared, tag):
        super().__init__()
        self.shared, self.tag = shared, tag

    def append(self, x):
        self.shared.append(f"{self.tag}:{x}")


def devices(shared=None):
    shared = [] if shared is None else shared
    main, web = FakeDriver(), FakeDriver()
    main.description, web.description = "an Android phone", "a web browser"
    main.trace, web.trace = Tagged(shared, "android"), Tagged(shared, "web")
    return main, web, shared


def passing(msg, n):
    thens = json.loads(msg.split("then to judge now: ")[1].split("\n")[0]) if "then to judge now: " in msg else []
    return reply({"type": "none" if "only judge" in msg else "tap", "x": 1, "y": 1},
                 verify=[v(t) for t in thens])


# ---------------------------------------------------------------- scenario


def test_on_is_read_per_section(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text(SWITCH, encoding="utf-8")
    sc = load(p)
    assert [s.on for s in sc.sections] == [None, "web", None] and sc.on_platforms == {"web"}


@pytest.mark.parametrize("app,on,code", [
    ('{android: com.example.app, web: "http://w"}', "web", None),
    ('{android: com.example.app, web: "http://w"}', "ios", "E018"),
    ("com.example.app", "ios", None),          # a package name is for Android and iOS
    ("com.example.app", "web", "E018"),
    ('"http://w"', "android", "E018"),
    ('{android: com.example.app, web: "http://w"}', "mac", "E017"),
    ('{android: com.example.app, web: "http://w"}', "[web]", "E017"),
])
def test_on_must_name_a_platform_the_app_has(tmp_path, app, on, code):
    p = tmp_path / "s.yaml"
    p.write_text(f"name: n\napp: {app}\nsteps: [{{id: s, on: {on}, actions: [{{do: a}}, {{then: b}}]}}]",
                 encoding="utf-8")
    codes = [i.code for i in check_file(p) if i.code in ("E017", "E018")]
    assert codes == ([code] if code else [])


def test_replaying_sections_of_another_device_is_warned(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text(SWITCH + "  - id: D\n    replay: {from: A, to: B}\n    actions: [{then: again}]\n", encoding="utf-8")
    w = [i for i in check_file(p) if i.code == "W011"]
    assert len(w) == 1 and "B" in w[0].message and "A" not in w[0].message.split("（")[1].split("）")[0]


# ---------------------------------------------------------------- platform choice


AV = {"android": True, "ios": True, "web": True}
APP = {"android": "a", "web": "w"}


ONLY_WEB = {"android": False, "ios": False, "web": True}


def test_a_platform_used_only_with_on_is_not_chosen_for_the_run():
    with pytest.raises(PlatformError, match="複数"):
        resolve(APP, None, AV)
    assert resolve(APP, None, AV, [None, "web"]) == ["android"]
    assert resolve({"android": "a", "ios": "i", "web": "w"}, "all", AV, [None, "web"]) == ["android", "ios"]
    assert resolve(APP, "web", AV, [None, "web"]) == ["web"]  # asked for: everything runs there


def test_the_run_does_not_fall_back_to_the_on_platform():
    with pytest.raises(PlatformError, match="実行できる対象がない（候補: Android"):
        resolve(APP, None, ONLY_WEB, [None, "web"])


def test_the_on_platform_must_be_available_too():
    with pytest.raises(PlatformError, match="`on: android` のセクションがあるが、Android の実行対象が見つからない"):
        resolve(APP, None, ONLY_WEB, [None, "android"])
    with pytest.raises(PlatformError, match="`on: android`"):
        resolve(APP, "web", ONLY_WEB, [None, "android"])


def test_when_every_section_names_its_device_the_run_is_for_the_first():
    assert resolve(APP, None, AV, ["web", "android"]) == ["web"]
    assert resolve(APP, "all", AV, ["android", "web"]) == ["android"]
    assert resolve(APP, None, ONLY_WEB, ["web"]) == ["web"]  # Android is not needed at all
    with pytest.raises(PlatformError, match="`on: android`"):
        resolve(APP, None, ONLY_WEB, ["web", "android"])


# ---------------------------------------------------------------- runner


def test_sections_run_on_their_device_and_thens_are_judged_before_leaving_it(make_run):
    main, web, trace = devices()
    systems = []

    def factory(system):
        systems.append(system)
        return FakeAI(passing)

    res, *_ = make_run(SWITCH, None, driver=main, platform="android", others={"web": (web, "http://w")},
                       factory=factory)
    assert [s.status for s in res.steps] == ["pass"] * 6 and res.status == "pass"
    assert [s.platform for s in res.steps] == ["android", "android", "web", "web", "android", "android"]
    assert trace[:2] == ["android:reset", "web:reset"]  # every device starts from its reset state
    acts = [t for t in trace if ":act:" in t]
    assert acts == ["android:act:tap", "web:act:tap", "android:act:tap"]
    # "sent" is judged on the phone (and its `wait` waited out) before anything happens on the Web
    first_web = next(i for i, t in enumerate(trace) if t.startswith("web:") and t != "web:reset")
    assert trace[first_web - 2:first_web] == ["android:observe", "android:wait_out"]
    assert [c["platform"] for c in res.calls] == ["android", "android", "web", "web", "android", "android"]
    # one conversation per device, each told about its own screen; the phone's is taken up again
    assert len(systems) == 2 and "an Android phone" in systems[0] and "a web browser" in systems[1]
    assert [c["session"] for c in res.calls] == [1, 1, 2, 2, 1, 1]  # the phone's conversation is taken up again
    assert res.others == {"web": "http://w"}


def test_coming_back_to_a_device_tells_its_conversation_what_happened_elsewhere(make_run):
    main, web, _ = devices()
    ais = []

    def factory(system):
        ais.append(FakeAI(passing))
        return ais[-1]

    make_run(SWITCH, None, driver=main, platform="android", others={"web": (web, "http://w")}, factory=factory)
    phone, browser = ais
    back = phone.msgs[2]  # the first message after the Web section
    assert "you are now on android" in back and "[B @ web] do: open the admin page -> done" in back
    assert "Earlier steps" in browser.msgs[0] and "Earlier steps" not in phone.msgs[1]
    # a device not used yet: its app is not open (a blank page did not tell the AI to launch it)
    assert "just switched to a web browser (`on: web`)" in browser.msgs[0] and "launch" in browser.msgs[0]
    assert not any("just switched" in m for m in phone.msgs + browser.msgs[1:])
    assert phone.closed and browser.closed


def test_a_section_on_the_scenarios_own_platform_does_not_switch(make_run):
    res, drv, ai, _ = make_run(SWITCH.replace("on: web", "on: android"), passing, platform="android")
    assert [s.platform for s in res.steps] == ["android"] * 6 and res.status == "pass"
    assert drv.resets == 1 and len({c["session"] for c in res.calls}) == 1


def test_a_failure_there_is_reported_with_the_device(make_run):
    main, web, _ = devices()

    def script(msg, n):
        if "open the admin page" in msg:
            return reply({"type": "fail", "reason": "no such page"}, verify=[v("sent")] if "sent" in msg else [])
        return passing(msg, n)

    res, _, _, events = make_run(SWITCH, script, driver=main, platform="android", others={"web": (web, "http://w")})
    assert [s.status for s in res.steps] == ["pass", "pass", "fail", "not_run", "not_run", "not_run"]
    fail = next(e for e in events if e["type"] == "fail")
    assert fail["device"] == "web" and describe(fail).startswith("[uiai] do 失敗: t @ android（on: web） / B /")


def test_stop_all_stops_at_the_switch_when_a_then_fails(make_run):
    main, web, _ = devices()
    y = SWITCH.replace("steps:", "config: {on_failure: stop_all}\nsteps:")

    def script(msg, n):
        if "only judge" in msg:
            return reply({"type": "none"}, verify=[v("sent", ok=False)])
        return passing(msg, n)

    res, *_ = make_run(y, script, driver=main, platform="android", others={"web": (web, "http://w")})
    assert [s.status for s in res.steps] == ["pass", "fail", "not_run", "not_run", "not_run", "not_run"]
    assert res.stop_all and web.acts == []


def test_next_section_resets_the_device_of_each_section(make_run):
    main, web, trace = devices()
    y = SWITCH.replace("steps:", "config: {on_failure: next_section}\nsteps:")
    res, *_ = make_run(y, passing, driver=main, platform="android", others={"web": (web, "http://w")})
    assert res.status == "pass"
    assert [t for t in trace if t.endswith(":reset")] == ["android:reset", "web:reset", "web:reset", "android:reset"]


def test_stop_app_after_stops_the_app_on_every_device(make_run):
    main, web, trace = devices()
    y = SWITCH.replace("steps:", "config: {stop_app_after: true}\nsteps:")
    make_run(y, passing, driver=main, platform="android", others={"web": (web, "http://w")})
    assert [t for t in trace if t.endswith(":stop_app")] == ["android:stop_app", "web:stop_app"]


def test_the_report_shows_where_each_step_ran(make_run, tmp_path):
    main, web, _ = devices()
    res, *_ = make_run(SWITCH, passing, driver=main, platform="android", others={"web": (web, "http://w")})
    out = tmp_path / "rep"
    out.mkdir()
    write_scenario(res, out, Redactor([]))
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "- 対象: android（http://x）、`on: web` は web（http://w）" in md
    assert "| 3 | B @ web | do |" in md and "| 1 | A | do |" in md
    assert "B @ web · do" in (out / "report.html").read_text(encoding="utf-8")
    assert json.loads((out / "result.json").read_text(encoding="utf-8"))["steps"][2]["platform"] == "web"


# ---------------------------------------------------------------- CLI


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    import uiai.ai.claude_code as cc
    import uiai.drivers as drivers
    from test_cli import FakeSession

    made: list = []

    class Driver(FakeDriver):
        def __init__(self, p, label):
            super().__init__()
            self.p, self.label, self.threads = p, label, []

        def act(self, action, app, check_stale=False):
            self.threads.append(threading.current_thread().name)
            return super().act(action, app, check_stale)

        def close(self):
            self.closed = True

    def make_driver(p, serial=None, udid=None, browser_path=None, headed=False):
        if serial == "BAD":
            raise drivers.DriverError("つながらない")
        made.append(Driver(p, serial or p))
        return made[-1]

    monkeypatch.setattr(drivers, "make_driver", make_driver)
    monkeypatch.setattr(cc, "ClaudeCodeSession", FakeSession)
    monkeypatch.setattr(platform, "android_serials", lambda: ["A", "B"])
    monkeypatch.setattr(platform, "booted_udids", lambda: [])

    def scenario(name: str, on: bool) -> str:
        p = tmp_path / f"{name}.yaml"
        extra = '  - id: w\n    on: web\n    actions:\n      - do: "見る"\n      - then: "出る"\n' if on else ""
        p.write_text(f'name: {name}\napp: {{android: "com.example.app", web: "http://w"}}\nsteps:\n'
                     f'  - id: a\n    actions:\n      - do: "開く"\n      - then: "表示される"\n{extra}',
                     encoding="utf-8")
        return str(p)

    def run(*args):
        return cli.main(["run", *args, "--results-dir", str(tmp_path / "r"), "--run-id", "x",
                         "--rejudge-model", "none"])

    return scenario, run, made


def test_a_run_opens_the_device_of_each_on_platform(cli_env, tmp_path, capsys):
    scenario, run, made = cli_env
    code = run(scenario("s", on=True), "--serial", "A")
    out = capsys.readouterr().out
    assert code == 0, out
    assert [(d.p, len(d.acts)) for d in made] == [("android", 1), ("web", 1)]
    assert all(getattr(d, "closed", False) for d in made)
    assert "▶ s @ android（com.example.app） + web（http://w）" in out and "⇄ web に切り替え" in out
    result = json.loads((tmp_path / "r" / "x" / "s-android" / "result.json").read_text(encoding="utf-8"))
    assert [s["platform"] for s in result["steps"]] == ["android", "android", "web", "web"]


def test_parallel_runs_switching_scenarios_in_order_afterwards(cli_env, capsys):
    scenario, run, made = cli_env
    files = [scenario("s1", on=False), scenario("s2", on=True), scenario("s3", on=False)]
    code = run(*files, "--parallel", "--platform", "android")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "並列実行: android 2 台（A, B）" in out and "web" not in out.split("並列実行: ")[1].split("\n")[0]
    assert "端末を切り替えるシナリオ（on）1 件は、ここから順番に実行する" in out
    web = [d for d in made if d.p == "web"]
    assert len(web) == 1 and web[0].threads == ["MainThread"] and web[0].closed
    assert out.index("▶ s2") > max(out.index("▶ s1"), out.index("▶ s3"))


def test_a_device_for_on_that_cannot_start_skips_the_scenario(cli_env, capsys, monkeypatch, tmp_path):
    scenario, run, made = cli_env
    monkeypatch.setattr(platform, "android_serials", lambda: ["BAD"])  # listed by adb, but cannot be opened
    f = tmp_path / "t.yaml"
    f.write_text('name: t\napp: {android: "com.example.app", web: "http://w"}\nsteps:\n'
                 '  - id: a\n    on: web\n    actions:\n      - do: "開く"\n'
                 '  - id: b\n    on: android\n    actions:\n      - do: "見る"\n', encoding="utf-8")
    code = run(str(f), "--serial", "BAD")
    out = capsys.readouterr().out
    assert code == 2 and "✗ t @ web: `on: android` の Android: つながらない" in out, out
    assert [d.p for d in made] == ["web"] and made[0].acts == []


def test_dry_run_names_the_devices_switched_to(cli_env, capsys):
    scenario, run, _ = cli_env
    assert cli.main(["run", scenario("s", on=True), "--dry-run"]) == 0
    assert "android で実行できる（`on` で web にも切り替える）" in capsys.readouterr().out


def test_only_a_plain_on_key_is_read_as_on(tmp_path):
    # YAML 1.1 reads a plain `on` as true; values keep that meaning
    p = tmp_path / "s.yaml"
    p.write_text('name: n\napp: {android: com.example.app, web: "http://w"}\nconfig: {strict: on}\n'
                 'steps:\n  - id: a\n    "on": web\n    actions: [{do: x, strict: off}]\n'
                 '  - id: b\n    On: web\n    actions: [{do: y}]\n', encoding="utf-8")
    sc = load(p)
    assert sc.config.strict is True and [s.on for s in sc.sections] == ["web", "web"]
    assert [it.strict for it in sc.items] == [False, True]


# ---------------------------------------------------------------- review fixes


def test_the_note_about_a_new_device_waits_for_that_device(make_run):
    # with no call on the Web, the phone's next message said it had just been switched to and was not open
    main, web, _ = devices()
    ais = []

    def factory(system):
        ais.append(FakeAI(passing))
        return ais[-1]

    y = SWITCH.replace('''      - do: "open the admin page"
      - then: "the request is listed"''', "      []").replace("    actions:\n      []", "    actions: []") + (
        '  - id: D\n    on: web\n    actions:\n      - do: "open the admin page"\n      - then: "listed"\n')
    res, *_ = make_run(y, None, driver=main, platform="android", others={"web": (web, "http://w")}, factory=factory)
    phone, browser = ais
    assert not any("just switched" in m for m in phone.msgs)
    assert "just switched to a web browser" in browser.msgs[0] and "open the admin page" in browser.msgs[0]


def test_each_device_keeps_whether_its_next_do_may_launch(make_run):
    # the Web section had no `do`: back on the phone, an unrequested relaunch must still be warned
    main, web, _ = devices()
    y = SWITCH.replace('''      - do: "open the admin page"
      - then: "the request is listed"''', '      - then: "the admin page is shown"').replace(
        "open the result", "check the result")  # ("open" asks for a launch)

    def script(msg, n):
        r = passing(msg, n)
        if "check the result" in msg:
            r["action"] = {"type": "launch"}
        return r

    res, *_ = make_run(y, script, driver=main, platform="android", others={"web": (web, "http://w")})
    assert [w for s in res.steps for w in s.warnings] == ["アプリを起動し直した（`do` は起動を指示していない）"]


def test_the_end_of_a_scenario_is_not_tagged_with_the_last_device(make_run, tmp_path):
    from uiai.report import write_summary

    main, web, _ = devices()
    y = SWITCH.replace("  - id: C\n", "  - id: C\n    on: web\n")

    def script(msg, n):
        if "open the result" in msg:
            return reply({"type": "fail", "reason": "gone"}, verify=[v("the request is listed")])
        return passing(msg, n)

    res, _, _, events = make_run(y, script, driver=main, platform="android", others={"web": (web, "http://w")})
    end = next(e for e in events if e["type"] == "scenario_end")
    assert "device" not in end and next(e for e in events if e["type"] == "fail")["device"] == "web"
    out = tmp_path / "rep"
    out.mkdir()
    summary = write_summary([(res, out)], tmp_path, 1, [], Redactor([])).read_text(encoding="utf-8")
    assert "- t @ android / C @ web / do「open the result」: gone" in summary


@pytest.mark.parametrize("app,warned", [
    ("{android: com.example.app}", False),            # the run can only be on Android: the same device
    ('{android: com.example.app, web: "http://w"}', True),  # it runs on the Web by default
])
def test_replay_warns_only_when_the_device_differs(tmp_path, app, warned):
    p = tmp_path / "s.yaml"
    p.write_text(f"name: n\napp: {app}\nsteps:\n  - id: A\n    on: android\n    actions: [{{do: a}}, {{then: b}}]\n"
                 "  - id: C\n    replay: {from: A, to: A}\n    actions: [{then: c}]\n", encoding="utf-8")
    assert any(i.code == "W011" for i in check_file(p)) == warned


def test_parallel_takes_the_next_device_when_one_cannot_start(cli_env, capsys, monkeypatch, tmp_path):
    scenario, run, made = cli_env
    monkeypatch.setattr(platform, "android_serials", lambda: ["BAD", "A"])
    f = tmp_path / "t.yaml"
    f.write_text('name: t\napp: {android: "com.example.app", web: "http://w"}\nsteps:\n'
                 '  - id: a\n    actions:\n      - do: "開く"\n'
                 '  - id: b\n    on: android\n    actions:\n      - do: "見る"\n', encoding="utf-8")
    code = run(str(f), "--parallel")
    out = capsys.readouterr().out
    assert code == 0, out
    assert [(d.p, d.label, len(d.acts)) for d in made] == [("web", "web", 1), ("android", "A", 1)]
