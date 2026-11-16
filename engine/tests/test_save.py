"""`save` on a `then`: a value read from the screen, used by later steps as a variable (issue #5)."""

from __future__ import annotations

import json

import pytest

from conftest import FakeAI, FakeDriver, reply, v
from uiai import cli, platform
from uiai.ai.protocol import build_judge_message, build_message, Ask, judge_system_prompt, parse_judge, \
    strip_tags, system_prompt, then_line
from uiai.events import EventLog, describe
from uiai.loop import ScenarioRunner
from uiai.redact import Redactor
from uiai.report import write_scenario
from uiai.scenario import check_file, load, resolve_variables

SAVE = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "open the list"
      - then: "the detail is shown"
        save:
          title: "the title"
      - do: "search for (title)"
      - then: "results for (title) are shown"
"""

DETAIL = "the detail is shown"
SENT = then_line(DETAIL, False, {"title": "the title"})  # as the AI is given it


def write(tmp_path, text, name="s.yaml"):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def errors(p):
    return [(i.code, i.message) for i in check_file(p) if i.level == "error"]


def scenario(steps: str, extra: str = "") -> str:
    return f'name: t\napp: "http://x"\n{extra}steps:\n{steps}'


# ---------------------------------------------------------------- loading and `uiai check`


def test_a_saved_variable_needs_no_declaration_and_no_value_before_the_run(tmp_path):
    p = write(tmp_path, SAVE)
    assert [i for i in check_file(p) if i.level == "error"] == []
    sc = load(p)
    assert sc.items[1].save == {"title": "the title"} and sc.items[2].uses == ["title"]
    assert sc.saved_names == {"title"}
    assert resolve_variables(sc, {}, interactive=False) == ({}, [])  # nothing to ask for: CI can run it


@pytest.mark.parametrize("action,message", [
    ('- do: "x"\n        save: {a: "b"}', "`save` は `then` にだけ書ける"),
    ('- then: "x"\n        save: "the title"', "マッピング"),
    ('- then: "x"\n        save: {}', "マッピング"),
    ('- then: "x"\n        save: {"1a": "b"}', "変数名 `1a` が不正"),
    ('- then: "x"\n        save: {a: ""}', "`a` に、画面で読み取る内容を書く"),
    ('- then: "x"\n        save: {a: 3}', "`a` に、画面で読み取る内容を書く"),
])
def test_e035_the_form_of_save(tmp_path, action, message):
    p = write(tmp_path, scenario(f"  - id: A\n    actions:\n      {action}\n"))
    assert [m for c, m in errors(p) if c == "E035" and message in m], errors(p)


def test_e036_a_variable_comes_from_one_place(tmp_path):
    both = scenario('  - id: A\n    actions:\n      - then: "x"\n        save: {a: "b"}\n      - do: "(a)"\n',
                    extra="variables:\n  a: fixed\n")
    assert [m for c, m in errors(write(tmp_path, both)) if c == "E036"] == [
        "変数 `a` が `variables` と `save` の両方にある（画面から読み取るなら `variables` から消す）"]
    twice = scenario('  - id: A\n    actions:\n      - then: "x"\n        save: {a: "b"}\n'
                     '      - then: "y"\n        save: {a: "c"}\n      - do: "(a)"\n')
    assert [c for c, _ in errors(write(tmp_path, twice))] == ["E036"]


def test_e037_used_before_the_then_that_reads_it(tmp_path):
    before = scenario('  - id: A\n    actions:\n      - do: "type (a)"\n      - then: "x"\n        save: {a: "b"}\n')
    assert errors(write(tmp_path, before)) == [
        ("E037", "変数 `(a)` を、画面から値を読み取る `save` より前で使っている（値がまだない）")]
    own = scenario('  - id: A\n    actions:\n      - then: "(a) is shown"\n        save: {a: "b"}\n'
                   '      - do: "(a)"\n')
    assert [c for c, _ in errors(write(tmp_path, own))] == ["E037"]  # its own text is judged before it saves
    later = scenario('  - id: A\n    actions:\n      - then: "x"\n        save: {a: "b"}\n'
                     '      - do: "type (a)"\n      - then: "(a) is shown"\n')
    assert errors(write(tmp_path, later)) == []


def test_e037_follows_the_run_order_of_replayed_dos(tmp_path):
    # A replays C before B has read the value: C's own `do` comes after B, its replay in A does not
    steps = ('  - id: A\n    replay: {from: C, to: C}\n    actions:\n      - then: "a"\n'
             '  - id: B\n    actions:\n      - then: "b"\n        save: {x: "it"}\n'
             '  - id: C\n    actions:\n      - do: "type (x)"\n      - then: "c"\n')
    assert [(i.code, i.where) for i in check_file(write(tmp_path, scenario(steps))) if i.level == "error"] == [
        ("E037", "steps[0]（A） replay → C actions[0]")]


def test_undefined_variables_and_secrets_in_what_save_reads(tmp_path):
    p = write(tmp_path, scenario('  - id: A\n    actions:\n      - then: "x"\n        save: {a: "the (nope)"}\n'
                                 '      - do: "(a)"\n'))
    assert ("E030", "未定義の変数 `(nope)`") in errors(p)
    p = write(tmp_path, scenario('  - id: A\n    actions:\n      - do: "log in"\n      - then: "x"\n'
                                 '        save: {a: "the row of (pw)"}\n      - do: "(a)"\n',
                                 extra="variables:\n  pw: {value: s, secret: true}\n"))
    assert [c for c, _ in errors(p)] == ["E033"]


def test_w005_a_saved_variable_never_used(tmp_path):
    p = write(tmp_path, scenario('  - id: A\n    actions:\n      - do: "x"\n'
                                 '      - then: "y"\n        save: {a: "b"}\n'))
    assert [(i.code, i.message) for i in check_file(p) if i.level == "warning"] == [
        ("W005", "`save` した変数 `a` が使われていない")]


PART = """
name: 検索
app: "http://x"
variables:
  title:
steps:
  - id: 検索する
    actions:
      - do: "「(title)」で検索する"
      - then: "「(title)」が見つかること"
"""


def test_an_included_scenario_can_use_a_value_the_including_one_reads(tmp_path):
    write(tmp_path, PART, "parts/search.yaml")  # on its own it asks for `title`
    p = write(tmp_path, scenario('  - id: 読む\n    actions:\n      - do: "開く"\n'
                                 '      - then: "詳細"\n        save: {title: "題"}\n'
                                 '  - include: parts/search.yaml\n'))
    assert errors(p) == []
    sc = load(p)
    assert "title" not in sc.variables and sc.saved_names == {"title"}
    assert resolve_variables(sc, {}, interactive=False) == ({}, [])


def test_an_included_save_clashes_with_a_value_of_the_including_scenario(tmp_path):
    write(tmp_path, scenario('  - id: 読む\n    actions:\n      - do: "開く"\n'
                             '      - then: "詳細"\n        save: {title: "題"}\n      - do: "(title)"\n'),
          "parts/read.yaml")
    p = write(tmp_path, scenario('  - include: parts/read.yaml\n  - id: B\n    actions:\n      - do: "(title)"\n',
                                 extra="variables:\n  title: fixed\n"))
    assert [c for c, _ in errors(p)] == ["E036"]


# ---------------------------------------------------------------- what the AI is told


def test_the_save_rule_is_only_in_scenarios_that_save():
    plain = system_prompt("a screen", 10, 10, [])
    assert "[save" not in plain and "{save}" not in plain
    assert '[save {"NAME": "WHAT", ...}]' in system_prompt("a screen", 10, 10, [], save=True)
    assert "[save" not in judge_system_prompt("a screen", 10, 10)
    assert '[save {"NAME": "WHAT", ...}]' in judge_system_prompt("a screen", 10, 10, save=True)


def test_a_then_carries_what_to_read_and_the_ai_may_echo_it():
    line = then_line("X", True, {"a": "the title", "b": "the price"})
    assert line == 'X [strict] [save {"a": "the title", "b": "the price"}]'
    assert strip_tags(line) == "X" and strip_tags("X [strict]") == "X" and strip_tags("X") == "X"
    # what to read may hold any character: JSON keeps the entries apart, and the tag still comes off
    odd = then_line("X", False, {"a": "the [ID] field; b: c", "b": "d"})
    assert odd == 'X [save {"a": "the [ID] field; b: c", "b": "d"}]' and strip_tags(odd) == "X"
    msg = build_message(Ask(section="s", do=None, thens=[("X", False, {"a": "the title"}), ("Y", False)]))
    assert json.dumps(['X [save {"a": "the title"}]', "Y"], ensure_ascii=False) in msg
    assert 'assertion: X [save {"a": "the title"}]' in build_judge_message("X", False, "do", {"a": "the title"})
    assert parse_judge('{"pass": true, "reason": "r", "save": {"a": "v"}}')["save"] == {"a": "v"}
    assert parse_judge('{"pass": true, "reason": "r"}')["save"] is None


# ---------------------------------------------------------------- running


def test_the_value_read_is_used_by_the_next_do_which_waits_for_it(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:  # judged before the `do` that needs the value, on the screen the last `do` left
            assert "only judge" in msg and json.dumps(SENT, ensure_ascii=False) in msg
            return reply({"type": "none"}, verify=[v(SENT, save={"title": " Foo Bar "})])  # echoed with its tags
        if n == 3:
            assert "do: search for Foo Bar" in msg
            return reply()
        assert '"results for Foo Bar are shown"' in msg
        return reply({"type": "none"}, verify=[v("results for Foo Bar are shown")])

    res, drv, ai, events = make_run(SAVE, script)
    assert [s.status for s in res.steps] == ["pass"] * 4 and res.status == "pass"
    assert [s.text for s in res.steps] == ["open the list", DETAIL, "search for Foo Bar",
                                           "results for Foo Bar are shown"]
    assert res.steps[1].saved == {"title": "Foo Bar"}  # trimmed
    assert len(ai.msgs) == 4


def test_the_system_prompt_has_the_rule_and_other_scenarios_do_not(make_run):
    systems = []

    def factory(system):
        systems.append(system)
        return FakeAI(lambda m, n: reply({"type": "none"}, verify=[v(DETAIL, save={"title": "T"})] if n == 2 else
                                         [v("results for T are shown")] if n == 4 else []))

    make_run(SAVE, None, factory=factory)
    assert '[save {"NAME": "WHAT", ...}]' in systems[0]


def test_without_a_step_that_needs_it_soon_the_then_is_judged_with_the_next_do_as_usual(make_run):
    text = SAVE.replace('      - do: "search for (title)"\n',
                        '      - do: "go back"\n      - then: "the list is shown"\n      - do: "search for (title)"\n')

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            assert "do: go back" in msg
            return reply(verify=[v(DETAIL, save={"title": "Foo"})])
        if n == 3:
            assert "do: search for Foo" in msg  # the value is known: no extra call
            return reply(verify=[v("the list is shown")])
        return reply({"type": "none"}, verify=[v("results for Foo are shown")])

    res, _, ai, _ = make_run(text, script)
    assert res.status == "pass" and len(ai.msgs) == 4


@pytest.mark.parametrize("verdict,reason", [
    (v(DETAIL), "`save` の title の値を AI が返さなかった"),
    (v(DETAIL, save={"title": ""}), "`save` の title の値を AI が返さなかった"),
    (v(DETAIL, save={"title": "Foo Ba…"}), "`save` の title の値が省略されている可能性（Foo Ba…）"),
    (v(DETAIL, save={"title": "Foo..."}), "`save` の title の値が省略されている可能性（Foo...）"),
    (v(DETAIL, ok=False, save={"title": "Foo"}), "r"),
])
def test_without_a_usable_value_the_then_fails_and_the_do_that_needs_it_is_not_run(make_run, verdict, reason):
    text = SAVE.replace("save:", "timeout: 0\n        save:")

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        assert n == 2, "the `do` that needs the value is not run"
        return reply({"type": "none"}, verify=[verdict])

    res, _, ai, events = make_run(text, script)
    assert [s.status for s in res.steps] == ["pass", "fail", "not_run", "not_run"] and res.status == "fail"
    assert res.steps[1].reason == reason and res.steps[1].saved == {}
    assert res.steps[2].reason == "変数 (title) の値がない（値を読み取る then「the detail is shown」が不合格）"
    assert res.steps[2].text == "search for (title)"  # never had a value
    fails = [e for e in events if e["type"] == "fail"]
    assert fails[0]["unsaved"] == ["title"] and "（値が決まらない変数: title）" in describe(fails[0])
    # the `do` left unrun is notified too: the failed `then` alone does not tell that the scenario stops
    assert len(fails) == 2 and fails[1]["kind"] == "do" and fails[1]["unrun"] is True and fails[1]["not_run"] == 1
    assert describe(fails[1]).startswith("[uiai] do 未実行: ") and "（残り 1 ステップは未実行）" in describe(fails[1])
    assert any("値は決まらない" in n for n in res.steps[1].notes)


def test_a_retry_on_a_fresh_screen_can_still_read_it(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply({"type": "none"}, verify=[v(DETAIL, save={"title": "Fo…"})])  # still loading
        if n == 3:
            assert "re-check" in msg
            return reply({"type": "none"}, verify=[v(DETAIL, save={"title": "Foo"})])
        if n == 4:
            assert "do: search for Foo" in msg
            return reply()
        return reply({"type": "none"}, verify=[v("results for Foo are shown")])

    res, *_ = make_run(SAVE, script)
    assert res.status == "pass" and res.steps[1].saved == {"title": "Foo"}


NEXT = """
name: t
app: "http://x"
config: {on_failure: next_section}
steps:
  - id: A
    actions:
      - do: "open"
      - then: "the detail is shown"
        timeout: 0
        save: {title: "the title"}
  - id: B
    actions:
      - do: "open"
      - then: "the header says (title)"
      - do: "search for (title)"
        optional: true
      - do: "tap"
      - then: "done"
  - id: C
    actions:
      - do: "search for (title)"
      - then: "results"
  - id: D
    actions:
      - do: "open"
      - then: "the end"
"""


def test_without_the_value_thens_and_optional_dos_are_passed_over_and_next_section_goes_on(make_run):
    def script(msg, n):
        if "only judge" in msg and DETAIL in msg or "the detail is shown [save" in msg:
            return reply({"type": "none"}, verify=[v(DETAIL, ok=False)])
        if "only judge" in msg:
            return reply({"type": "none"}, verify=[v(t, ok=True) for t in ("done", "the end") if f'"{t}"' in msg])
        return reply({"type": "launch"})

    res, _, ai, events = make_run(NEXT, script)
    st = {s.text: s.status for s in res.steps}
    assert st["the detail is shown"] == "fail"
    assert st["the header says (title)"] == "not_run"   # a `then`: not judged, the section goes on
    skipped = [s for s in res.steps if s.status == "skip"]
    assert len(skipped) == 1 and skipped[0].section == "B"  # the optional `do` is skipped
    assert [s.status for s in res.steps if s.section == "B"] == ["pass", "not_run", "skip", "pass", "pass"]
    assert [s.status for s in res.steps if s.section == "C"] == ["not_run", "not_run"]  # next_section
    assert [s.status for s in res.steps if s.section == "D"] == ["pass", "pass"]
    assert [(e["type"], e.get("unrun")) for e in events if e["type"] in ("fail", "skip")] == [
        ("fail", None), ("skip", None), ("fail", True)]  # C's `do`: the rest of its section is not run


def test_a_second_opinion_that_passes_must_read_the_value_too(make_run):
    text = SAVE.replace("save:", "timeout: 0\n        save:")

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply({"type": "none"}, verify=[v(DETAIL, ok=False)])
        if n == 3:
            assert "do: search for Bar" in msg
            return reply()
        return reply({"type": "none"}, verify=[v("results for Bar are shown")])

    seen = []

    def rejudge(msg):
        seen.append(msg)
        return {"pass": True, "reason": "ok", "save": {"title": "Bar"}}

    res, *_ = make_run(text, script, rejudge=rejudge)
    assert res.status == "pass_warn" and res.steps[1].saved == {"title": "Bar"}
    assert "assertion: " + SENT in seen[0]
    assert res.calls[1]["rejudge"][0]["save"] == {"title": "Bar"}

    res, *_ = make_run(text, lambda m, n: reply({"type": "launch"}) if n == 1 else
                       reply({"type": "none"}, verify=[v(DETAIL, ok=False)]),
                       rejudge=lambda m: {"pass": True, "reason": "ok"})
    assert res.steps[1].status == "fail" and "AI が返さなかった" in res.steps[1].reason


def test_a_value_read_on_one_device_is_used_on_another(make_run):
    text = """
name: t
app: {android: com.example.app, web: "http://w"}
steps:
  - id: 注文
    actions:
      - do: "注文する"
      - then: "注文番号が表示されていること"
        save: {order: "注文番号"}
  - id: 管理画面
    on: web
    actions:
      - do: "「(order)」を検索する"
      - then: "見つかること"
"""
    phone, web = FakeDriver(), FakeDriver()
    phone.description, web.description = "an Android phone", "a web browser"

    def script(msg, n):
        if "注文番号が表示されていること [save" in msg:
            return reply({"type": "none"}, verify=[v("注文番号が表示されていること", save={"order": "A-123"})])
        if "only judge" in msg:  # (it names the `do` before as well)
            return reply({"type": "none"}, verify=[v("見つかること")])
        if "「A-123」を検索する" in msg:
            return reply()
        return reply()

    res, *_ = make_run(text, script, driver=phone, platform="android", others={"web": (web, "http://w")})
    assert res.status == "pass" and res.steps[2].text == "「A-123」を検索する" and res.steps[2].platform == "web"


def test_the_values_read_belong_to_the_run_not_to_the_dict_it_was_given(tmp_path, clock):
    sc = load(write(tmp_path, SAVE))
    values: dict = {}
    red = Redactor([])
    out = tmp_path / "out"
    out.mkdir()
    ai = FakeAI(lambda m, n: reply({"type": {1: "launch", 3: "tap"}.get(n, "none")},
                                   verify=[v(DETAIL, save={"title": "T"})] if n == 2 else
                                   [v("results for T are shown")] if n == 4 else []))
    ev = EventLog(tmp_path / "e.jsonl", red)
    res = ScenarioRunner(sc, "web", "http://x", FakeDriver(), lambda s: ai, values, out, ev, red, "haiku",
                         printer=lambda s: None).run()
    ev.close()
    assert res.status == "pass" and values == {}  # another platform's run of the scenario starts without it


def test_the_report_and_result_json_keep_the_value(make_run, tmp_path):
    res, *_ = make_run(SAVE, lambda m, n: reply({"type": "none"}, verify=[v(DETAIL, save={"title": "T"})] if n == 2
                                                else [v("results for T are shown")] if n == 4 else []))
    out = tmp_path / "rep"
    out.mkdir()
    write_scenario(res, out, Redactor([]))
    data = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert data["steps"][1]["saved"] == {"title": "T"}
    assert "（保存: title = 「T」）" in (out / "report.md").read_text(encoding="utf-8")
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "保存: <code>title = 「T」</code>" in html


# ---------------------------------------------------------------- cli


def test_var_for_a_saved_variable_is_not_used_and_dry_run_says_so(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(platform, "probe", lambda serial=None, udid=None: {"android": False, "ios": False, "web": True})
    p = write(tmp_path, SAVE)
    code = cli.main(["run", str(p), "--dry-run", "--var", "title=x", "--results-dir", str(tmp_path / "r")])
    out = capsys.readouterr().out
    assert code == 0
    assert "--var の title は画面から読み取る変数（save）なので、渡した値は使わない" in out
    assert "web で実行できる（画面から読み取る変数: title）" in out


# ---------------------------------------------------------------- review fixes


def test_an_app_change_is_told_with_the_do_not_with_the_judging_before_it(make_run, tmp_path):
    write(tmp_path, 'name: other\napp: "http://other"\nvariables:\n  code:\nsteps:\n  - id: s\n    actions:\n'
                    '      - do: "type (code)"\n      - then: "typed"\n', "parts/other.yaml")
    text = scenario('  - id: pre\n    actions:\n      - do: "open"\n      - then: "opened"\n'
                    '        save: {code: "the code"}\n  - include: parts/other.yaml\n')

    def script(msg, n):
        if n == 2:  # judged early, on the screen of the app before: nothing about the other app yet
            assert "only judge" in msg and "The app under test is now" not in msg
            return reply({"type": "none"}, verify=[v("opened", save={"code": "C1"})])
        if n == 3:
            assert "The app under test is now http://other" in msg and "do: type C1" in msg
            return reply({"type": "launch"})
        if n == 4:
            return reply({"type": "none"}, verify=[v("typed")])
        return reply({"type": "launch"})

    res, _, ai, _ = make_run(text, script)
    assert res.status == "pass" and len(ai.msgs) == 4


def test_what_finishes_the_last_do_runs_when_the_then_is_judged_early(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:  # the value is visible behind the confirmation the last `do` opened: it is asked again for it
            return reply({"type": "tap", "x": 5, "y": 6}, purpose="verify", done=False,
                         verify=[v(DETAIL, save={"title": "T"})])
        if n == 3:
            assert "this `do` was reported done" in msg and "do: open the list" in msg and DETAIL not in msg
            return reply({"type": "tap", "x": 5, "y": 6})
        if n == 4:
            assert "do: search for T" in msg
            return reply()
        return reply({"type": "none"}, verify=[v("results for T are shown")])

    res, drv, ai, _ = make_run(SAVE, script)
    assert res.status == "pass"
    assert [a["type"] for a in drv.acts] == ["launch", "tap", "tap"] and drv.acts[1]["x"] == 5
    assert [c["kind"] for c in res.calls] == ["do", "judge", "finish", "do", "judge"]
    assert "then の判定の前に、then を見せずに聞き直して続けた操作: tap" in res.steps[0].notes


def test_an_included_declaration_with_a_value_is_not_replaced_by_a_save(tmp_path):
    write(tmp_path, 'name: login\napp: "http://x"\nvariables:\n  pw: {env: PW, secret: true}\nsteps:\n'
                    '  - id: s\n    actions:\n      - do: "type (pw)"\n      - then: "in"\n', "parts/login.yaml")
    p = write(tmp_path, scenario('  - id: A\n    actions:\n      - do: "open"\n      - then: "x"\n'
                                 '        save: {pw: "the hint"}\n  - include: parts/login.yaml\n'))
    assert [c for c, _ in errors(p)] == ["E036"]  # not a silent swap of the secret for the hint
    # a save that E035 rejects does not take the declaration away either
    p = write(tmp_path, scenario('  - id: A\n    actions:\n      - do: "open"\n      - then: "x"\n'
                                 '        save: {pw: ""}\n  - include: parts/login.yaml\n'))
    assert [c for c, _ in errors(p)] == ["E035"]


def test_the_then_is_found_when_the_ai_echoes_a_tag_holding_a_bracket(make_run):
    text = SAVE.replace('title: "the title"', 'title: "the [ID] field"')

    def script(msg, n):
        if n == 2:  # one verdict too many: the `then` is found by its text
            return reply({"type": "none"}, verify=[v("something else"),
                                                   v(then_line(DETAIL, False, {"title": "the [ID] field"}),
                                                     save={"title": "T"})])
        if n == 3:
            return reply()
        if n == 4:
            return reply({"type": "none"}, verify=[v("results for T are shown")])
        return reply({"type": "launch"})

    res, *_ = make_run(text, script)
    assert res.steps[1].status == "pass" and res.steps[1].saved == {"title": "T"}


@pytest.mark.parametrize("value,saved,reason", [
    (1.10, None, "`save` の title の値を AI が文字として返さなかった（1.1）"),  # its text is lost
    (4827, None, "`save` の title の値を AI が文字として返さなかった（4827）"),
    ("　Foo ", "　Foo", ""),  # a full-width space is on the screen: only ASCII blanks are trimmed
])
def test_the_value_must_come_as_text(make_run, value, saved, reason):
    text = SAVE.replace("save:", "timeout: 0\n        save:")

    def script(msg, n):
        if n == 2:
            return reply({"type": "none"}, verify=[v(DETAIL, save={"title": value})])
        if n == 3:
            return reply()
        return reply({"type": "none" if n > 1 else "launch"}, verify=[v(f"results for {saved} are shown")])

    res, *_ = make_run(text, script)
    if saved is None:
        assert res.steps[1].status == "fail" and res.steps[1].reason == reason
    else:
        assert res.steps[1].saved == {"title": saved}


def test_an_optional_do_without_its_value_costs_no_extra_call(make_run):
    text = scenario('  - id: A\n    actions:\n      - do: "open"\n      - then: "detail"\n        timeout: 0\n'
                    '        save: {title: "the title"}\n      - do: "tap"\n      - then: "other"\n'
                    '      - do: "search for (title)"\n        optional: true\n      - do: "next"\n')

    def script(msg, n):
        assert "only judge" not in msg  # "other" is judged with "next", as usual
        if n == 2:
            return reply(verify=[v("detail", ok=False)])
        if n == 3:
            assert "do: next" in msg and '"other"' in msg
            return reply(verify=[v("other")])
        return reply({"type": "launch"})

    res, _, ai, _ = make_run(text, script)
    assert len(ai.msgs) == 3
    assert [s.status for s in res.steps] == ["pass", "fail", "pass", "pass", "skip", "pass"]
