"""`optional: true` on a `do`: if it fails, it is recorded as skipped and the scenario goes on."""

from __future__ import annotations

import json

from conftest import FakeAI, reply, v
from uiai.ai.protocol import Ask, build_message, system_prompt
from uiai.events import describe
from uiai.redact import Redactor
from uiai.report import write_scenario, write_summary
from uiai.scenario import check_file, load

REGISTER = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "register taro"
        optional: true
      - do: "open the list"
      - then: "taro is listed"
"""


def statuses(res):
    return [(s.kind, s.text, s.status) for s in res.steps]


# ---------------------------------------------------------------- scenario


def test_optional_is_read_on_do_lines_and_kept_by_replay(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text(REGISTER + """  - id: B
    replay: {from: A, to: A}
    actions:
      - do: "go on"
      - then: "done"
""", encoding="utf-8")
    sc = load(p)
    assert [(it.raw, it.optional) for it in sc.sections[1].items if it.kind == "do"] == [
        ("register taro", True), ("open the list", False), ("go on", False)]


def test_optional_must_be_a_boolean_and_only_counts_on_do(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text('name: n\napp: com.example.app\nsteps: [{id: s, actions: [{do: a, optional: "yes"}, '
                 '{then: b, optional: true}]}]', encoding="utf-8")
    codes = sorted(i.code for i in check_file(p))
    assert "E014" in codes and "W010" in codes


# ---------------------------------------------------------------- AI prompt


def test_the_ai_is_told_only_in_scenarios_with_an_optional_do():
    assert "[optional]" in system_prompt("x", 1, 1, [], optional=True)
    assert "[optional]" not in system_prompt("x", 1, 1, [])
    assert "do: register [optional]" in build_message(Ask(section="A", do="register", do_optional=True))
    assert "[optional]" not in build_message(Ask(section="A", do="register"))


def test_the_runner_asks_for_the_rule_when_the_scenario_has_an_optional_do(make_run):
    systems = []

    def script(msg, n):
        return reply({"type": "none"}, verify=[v("taro is listed")] if "taro is listed" in msg else [])

    def factory(system):
        systems.append(system)
        return FakeAI(script)

    make_run(REGISTER, None, factory=factory)
    make_run(REGISTER.replace("        optional: true\n", ""), None, factory=factory)
    assert ["[optional] `do`" in s for s in systems] == [True, False]


# ---------------------------------------------------------------- runner


def test_a_failed_optional_do_is_skipped_and_the_scenario_goes_on(make_run):
    def script(msg, n):
        if n == 1:
            assert "do: register taro [optional]" in msg
            return reply({"type": "fail", "reason": "already registered"})
        if n == 2:
            assert "[optional]" not in msg
            return reply({"type": "tap", "x": 1, "y": 1})
        return reply({"type": "none"}, verify=[v("taro is listed")])

    res, drv, ai, events = make_run(REGISTER, script)
    assert statuses(res) == [("do", "register taro", "skip"), ("do", "open the list", "pass"),
                             ("then", "taro is listed", "pass")]
    assert res.steps[0].reason == "already registered"
    assert res.status == "pass" and res.counts()["skip"] == 1  # skipping is not a warning
    skip = [e for e in events if e["type"] == "skip"]
    assert len(skip) == 1 and skip[0]["text"] == "register taro" and not [e for e in events if e["type"] == "fail"]


def test_an_error_shown_during_an_optional_do_is_skipped_too(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "fail", "reason": "登録済みです"}, error_shown=True)
        if n == 2:
            return reply({"type": "tap", "x": 1, "y": 1})
        return reply({"type": "none"}, verify=[v("taro is listed")])

    res, *_ = make_run(REGISTER, script)
    assert res.steps[0].status == "skip" and "登録済みです" in res.steps[0].reason and res.status == "pass"


def test_an_optional_do_looks_at_the_result_of_its_last_action_before_it_passes(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "tap", "x": 1, "y": 1})  # "done"
        if n == 2:
            assert "[optional] check the result on this screen" in msg
            return reply({"type": "none"})
        return reply({"type": "tap", "x": 1, "y": 1}, verify=[v("taro is listed")] if "taro is listed" in msg else [])

    res, drv, ai, _ = make_run(REGISTER, script)
    assert [s.status for s in res.steps] == ["pass", "pass", "pass"] and res.status == "pass"  # no no-op warning
    assert len(drv.acts) == 2 and "check the result" not in ai.msgs[2]  # only for the optional `do`


def test_a_message_after_the_last_action_is_closed_by_the_optional_do_itself(make_run):
    # "already registered" comes after the tap that should have finished the `do`; left to the next `do`, it
    # was closed there and that `do` then failed (1 run in 3)
    y = REGISTER.replace('app: "http://x"', 'app: "http://x"\nconfig: {max_actions: 1}')

    def script(msg, n):
        if n == 1:
            return reply({"type": "tap", "x": 1, "y": 1})
        if n == 2:  # the check: close the message (beyond max_actions: the check has room for it)
            return reply({"type": "tap", "x": 5, "y": 5, "reason": "close"}, done=False)
        if n == 3:
            return reply({"type": "fail", "reason": "already registered"})
        return reply({"type": "tap", "x": 1, "y": 1}, verify=[v("taro is listed")] if "taro is listed" in msg else [])

    res, drv, *_ = make_run(y, script)
    assert [s.status for s in res.steps] == ["skip", "pass", "pass"] and res.steps[0].reason == "already registered"
    assert [a.get("reason") for a in drv.acts][:2] == [None, "close"]


def test_the_scenario_time_limit_still_stops_an_optional_do(make_run, clock):
    y = REGISTER.replace('app: "http://x"', 'app: "http://x"\nconfig: {timeout: 3}')

    def script(msg, n):
        clock.now += 2
        return reply({"type": "wait"}, done=False)

    res, *_ = make_run(y, script)
    assert res.steps[0].status == "fail" and "config.timeout" in res.steps[0].reason
    assert [s.status for s in res.steps[1:]] == ["not_run", "not_run"]


# ---------------------------------------------------------------- reports


def test_reports_and_notices_show_the_skip(make_run, tmp_path):
    def script(msg, n):
        if n == 1:
            return reply({"type": "fail", "reason": "already registered"})
        return reply({"type": "tap", "x": 1, "y": 1}, verify=[v("taro is listed")] if "taro is listed" in msg else [])

    res, _, _, events = make_run(REGISTER, script)
    run_dir = tmp_path / "run"
    out = run_dir / "s-web"
    out.mkdir(parents=True)
    write_scenario(res, out, Redactor([]))
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "⏭️ スキップ（optional） | already registered" in md and "スキップ（optional） 1" in md
    assert json.loads((out / "result.json").read_text(encoding="utf-8"))["counts"]["skip"] == 1
    summary = write_summary([(res, out)], run_dir, 0, [], Redactor([])).read_text(encoding="utf-8")
    assert "## スキップ（optional の do が失敗した）" in summary and "do「register taro」: already registered" in summary
    skip = next(e for e in events if e["type"] == "skip")
    assert describe(skip) == "[uiai] スキップ（optional）: t @ web / A / 「register taro」: already registered"
