from __future__ import annotations

from conftest import reply, v
from uiai.ai.protocol import system_prompt

BASIC = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "open the app"
      - then: "X is shown"
      - do: "tap B"
      - then: "Y is shown"
"""


def statuses(res):
    return [(s.kind, s.text, s.status) for s in res.steps]


def test_happy_path_judges_then_in_next_call_and_final_then_in_judge_only_call(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            assert '"X is shown"' in msg
            return reply(verify=[v("X is shown")])
        assert "only judge" in msg and '"Y is shown"' in msg
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, drv, ai, ev = make_run(BASIC, script)
    assert res.status == "pass"
    assert [s.status for s in res.steps] == ["pass"] * 4
    assert len(ai.msgs) == 3 and [a["type"] for a in drv.acts] == ["launch", "tap"]
    assert ai.closed


def test_failed_then_is_rechecked_and_the_step_action_is_not_executed_meanwhile(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply(verify=[v("X is shown", False)])
        if n == 3:
            assert "re-check" in msg
            return reply(verify=[v("X is shown")])
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, drv, ai, _ = make_run(BASIC, script)
    assert res.status == "pass"
    assert [a["type"] for a in drv.acts] == ["launch", "tap"]  # the tap from call 2 was not executed
    assert [c["kind"] for c in res.calls] == ["do", "do", "recheck", "judge"]


def test_then_fails_after_timeout_and_the_scenario_continues(make_run, clock):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if '"X is shown"' in msg:
            return reply(verify=[v("X is shown", False)])
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, drv, ai, ev = make_run(BASIC, script)
    x = res.steps[1]
    assert x.status == "fail" and res.status == "fail"
    assert res.steps[2].status == "pass" and res.steps[3].status == "pass"  # continued
    fails = [e for e in ev if e["type"] == "fail"]
    assert len(fails) == 1 and fails[0]["kind"] == "then"
    # judged at t=0,1,..,5 (1 s waits): 6 judgments, the 6th (>= 5 s) fails
    assert sum(1 for c in res.calls if "X is shown" in c["thens"]) == 6


AGAIN = "this `do` was reported done"  # in the message that asks a `do` again (finish)


def test_what_finishes_the_previous_do_runs_only_when_that_do_asked_again_on_its_own_gives_it(make_run):
    """"open the app" left the confirmation of what it asked for open: the OK given to judge the `then` is not run;
    the `do` is asked again in a conversation of its own that has not seen the `then`, and runs what it gives."""
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:  # in the call of "tap B"
            return reply({"type": "tap", "x": 5, "y": 5}, verify=[v("X is shown", False)], purpose="verify", done=False)
        if n == 3:
            assert AGAIN in msg and "do: open the app" in msg and "then to judge now: []" in msg
            assert "X is shown" not in msg and "tap B" not in msg and "previous do" not in msg
            return reply({"type": "tap", "x": 5, "y": 5})
        if n == 4:
            assert "only judge" in msg and "tap was NOT executed" in msg and '"tap B"' in msg
            assert "went on: tap" in msg and "previous do (the `then`s check its result): open the app" in msg
            return reply({"type": "none"}, verify=[v("X is shown")])
        if n == 5:
            assert "then to judge now: []" in msg and "previous do" not in msg
            return reply()
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, drv, ai, _ = make_run(BASIC, script)
    assert [(a["type"], a.get("x")) for a in drv.acts] == [("launch", None), ("tap", 5), ("tap", 1)]
    assert [c["kind"] for c in res.calls] == ["do", "do", "finish", "judge", "do", "judge"]
    assert res.calls[2]["step"] == 1 and res.calls[2]["session"] != res.calls[1]["session"]
    assert res.calls[3]["session"] == res.calls[1]["session"]  # the judging goes on in the conversation it was in
    assert res.calls[1]["note"].startswith("判定のための操作は実行せず、前の do を then なしで聞き直す")
    assert "then の判定の前に、then を見せずに聞き直して続けた操作: tap" in res.steps[0].notes
    assert res.status == "pass"


def test_a_then_is_not_made_to_pass_by_what_the_previous_do_did_not_ask_for(make_run):
    """The `do` said to tap one button and leave its confirmation open; the AI gave the OK of the confirmation to
    judge the `then` (the error it expected came only after that OK: a bug), also after it was not run. Asked again
    on its own, the `do` needs nothing more: the OK is never pressed and the `then` fails."""
    ok = {"type": "tap", "x": 9, "y": 9}

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if AGAIN in msg:
            return reply({"type": "none"})
        if "X is shown" in msg:
            if n > 3:
                assert "needs nothing more" in msg or "re-check" in msg
            return reply(ok, verify=[v("X is shown", False)], purpose="verify", done=False)
        if "only judge" in msg:
            return reply({"type": "none"}, verify=[v("Y is shown")])
        return reply()

    res, drv, ai, _ = make_run(BASIC, script)
    assert [a.get("x") for a in drv.acts] == [None, 1]  # never the OK
    assert [c["kind"] for c in res.calls].count("finish") == 1
    assert res.steps[1].status == "fail" and res.steps[3].status == "pass"
    assert any(c["note"].startswith("判定のための操作は実行せず、前の do は聞き直し済み") for c in res.calls)
    assert not res.steps[0].notes


def test_asked_again_a_do_may_not_go_back_or_restart_the_app(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply({"type": "tap", "x": 5, "y": 5}, verify=[v("X is shown", False)], purpose="verify", done=False)
        if n == 3:
            assert AGAIN in msg
            return reply({"type": "back"})
        if n == 4:
            assert "needs nothing more" in msg
            return reply({"type": "none"}, verify=[v("X is shown")])
        if n == 5:
            return reply()
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, drv, _, _ = make_run(BASIC, script)
    assert [a["type"] for a in drv.acts] == ["launch", "tap"]
    assert res.calls[2]["note"] == "前の do の続きとしては実行しない"
    assert res.status == "pass"


def test_a_do_is_asked_again_a_few_times_at_most(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if AGAIN in msg:
            return reply({"type": "tap", "x": 6, "y": 6}, done=False)  # never done
        if "X is shown" in msg:
            return reply({"type": "tap", "x": 5, "y": 5}, verify=[v("X is shown", False)], purpose="verify", done=False)
        if "only judge" in msg:
            return reply({"type": "none"}, verify=[v("Y is shown")])
        return reply()

    res, drv, ai, _ = make_run(BASIC, script)
    kinds = [c["kind"] for c in res.calls]
    assert kinds.count("finish") == 3 and kinds[2:5] == ["finish"] * 3  # in one go, then never again
    assert "(continuing this `do`, action 2)" in ai.msgs[3] and "previous action: tap -> ok" in ai.msgs[3]
    assert [a.get("x") for a in drv.acts] == [None, 6, 6, 6, 1]
    assert res.steps[1].status == "fail"


TABS = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "tap tab A"
      - then: "field X is not shown"
      - do: "tap tab B"
      - then: "field X is shown"
"""


def test_the_do_given_as_a_verify_action_runs_only_after_the_thens_are_judged(make_run):
    """The AI gave the tap on tab B (the `do`) as one that finishes the previous `do`: the negative `then` was
    observed after it and failed. "tap tab A", asked again on its own, needs nothing more; the `then` is judged on
    the screen tab A left, and tab B is tapped as a step."""
    def script(msg, n):
        if n == 1:
            return reply({"type": "tap", "x": 1, "y": 1})
        if n == 2:
            return reply({"type": "tap", "x": 2, "y": 2}, verify=[v("field X is not shown", absence=True)],
                         purpose="verify")
        if n == 3:
            assert AGAIN in msg and "do: tap tab A" in msg
            return reply({"type": "none"})
        if n == 4:
            assert "only judge" in msg and "needs nothing more" in msg
            return reply({"type": "none"}, verify=[v("field X is not shown", absence=True)])
        if n == 5:
            assert "do: tap tab B" in msg and "then to judge now: []" in msg
            return reply({"type": "tap", "x": 2, "y": 2})
        return reply({"type": "none"}, verify=[v("field X is shown")])

    res, drv, ai, _ = make_run(TABS, script)
    assert [a["x"] for a in drv.acts] == [1, 2]
    assert drv.watched == [2.0]  # observed on the screen tab A left (in call 4, before tab B is tapped)
    assert [c["kind"] for c in res.calls] == ["do", "do", "finish", "judge", "do", "judge"]
    assert res.status == "pass" and not any(s.warnings for s in res.steps)


def test_a_scroll_to_judge_a_then_still_runs_in_the_call_of_the_do(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply({"type": "scroll", "direction": "down"}, verify=[v("X is shown", False)], purpose="verify",
                         done=False)
        if n == 3:
            return reply(verify=[v("X is shown")])
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, drv, _, _ = make_run(BASIC, script)
    assert [a["type"] for a in drv.acts] == ["launch", "scroll", "tap"]
    assert [c["kind"] for c in res.calls] == ["do", "do", "recheck", "judge"]
    assert res.status == "pass"


def test_what_the_previous_do_still_needed_runs_before_a_negative_then_is_observed(make_run):
    """"save" left its confirmation open: asked again, it taps the OK, and a negative `then` is observed only after
    that (an error shown after saving is caught)."""
    y = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "save"
      - then: "saved message is shown"
      - then: "no error is shown"
      - do: "open home"
      - then: "home is shown"
"""
    drv = __import__("conftest").FakeDriver()
    drv.watch_results = [True]
    finish = {"type": "tap", "x": 7, "y": 7}

    def script(msg, n):
        if n == 1:
            return reply()
        if n == 2:  # the call of "open home"
            return reply(finish, verify=[v("saved message is shown", False), v("no error is shown", absence=True)],
                         purpose="verify", done=False)
        if n == 3:
            assert AGAIN in msg and "do: save" in msg
            return reply(finish)
        if n == 4:
            return reply({"type": "none"}, verify=[v("saved message is shown"), v("no error is shown", absence=True)])
        if "only judge" in msg and "no error" in msg:
            return reply({"type": "none"}, verify=[v("no error is shown", False, absence=True)])
        if "only judge" in msg:
            return reply({"type": "none"}, verify=[v("home is shown")])
        return reply({"type": "tap", "x": 3, "y": 3})

    res, drv, ai, _ = make_run(y, script, driver=drv)
    assert [a.get("x") for a in drv.acts] == [1, 7, 3]
    assert drv.watched == [2.0]          # observed only after the confirmation was finished
    assert [s.status for s in res.steps] == ["pass", "pass", "fail", "pass", "pass"]


def test_the_rules_keep_a_do_to_what_it_says_and_its_actions_off_verify():
    s = system_prompt("a screen", 10, 10, [])
    assert 'A `do` that only says to tap or press one control (e.g. "「保存」をタップ") is done with that tap' in s
    assert "check: leave it open. Unexpected dialogs" in s
    assert 'always "step", also while `then`s are being judged' in s
    assert "Never press anything in a dialog or screen that a `then`\n  refers to" in s
    assert "a confirmation dialog it opened" not in s  # the example that read as "press the confirmation"


def test_the_previous_do_is_not_given_across_a_reset(make_run):
    y = """
name: t
app: "http://x"
config:
  on_failure: next_section
steps:
  - id: A
    actions:
      - do: "open"
      - then: "X is shown"
  - id: B
    actions:
      - then: "Y is shown"
      - do: "tap"
"""

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:  # X, before the reset
            assert "only judge" in msg and "previous do (the `then`s check its result): open" in msg
            return reply({"type": "none"}, verify=[v("X is shown")])
        if n == 3:  # Y: on the screen the reset left, not a result of "open"
            assert '"Y is shown"' in msg and "previous do" not in msg
            return reply(verify=[v("Y is shown")])
        return reply({"type": "none"})

    res, _, ai, _ = make_run(y, script)
    assert res.status == "pass" and len(ai.msgs) == 3
    # without the reset, Y is judged as a result of "open"
    res, _, ai, _ = make_run(y.replace("on_failure: next_section", "on_failure: stop_scenario"), lambda m, n: (
        reply({"type": "launch"}) if n == 1 else reply(verify=[v("X is shown"), v("Y is shown")])))
    assert "previous do (the `then`s check its result): open" in ai.msgs[1] and '"Y is shown"' in ai.msgs[1]
    assert res.status == "pass" and len(ai.msgs) == 2


def test_without_a_previous_do_an_action_to_finish_it_is_not_run(make_run):
    y = """
name: t
app: "http://x"
config:
  on_failure: next_section
steps:
  - id: A
    actions:
      - do: "open"
  - id: B
    actions:
      - then: "Y is shown"
      - do: "tap"
"""

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if '"Y is shown"' in msg:  # on the screen the reset left: no `do` to finish, nothing to ask again
            assert AGAIN not in msg
            return reply({"type": "tap", "x": 9, "y": 9}, verify=[v("Y is shown", False)], purpose="verify",
                         done=False)
        return reply({"type": "none"})

    res, drv, ai, _ = make_run(y, script)
    assert [a.get("x") for a in drv.acts] == [None]
    assert "finish" not in [c["kind"] for c in res.calls]
    assert res.calls[1]["note"] == "判定のための操作は実行せず、前の do は聞き直さない。then は判定だけの呼び出しで判定する"
    assert '"verify" is only for scrolling here' in ai.msgs[2]
    assert res.steps[1].status == "fail"


LOGIN = """
name: t
app: "http://x"
config: {interrupts: {allow: ["Cookie の同意"]}}
steps:
  - id: A
    actions:
      - do: "open the app"
      - do: "type the email"
      - do: "type the password"
      - then: "logged in"
"""
COOKIE = dict(purpose="interrupt", dialog="Cookie", allowed="Cookie の同意", done=False)
COVERED = "the action may have hit the dialog"  # in the message that asks a `do` again after an interrupt


def test_a_do_whose_last_action_a_dialog_may_have_taken_is_asked_again_once_it_is_closed(make_run):
    """The cookie dialog came up as the email was typed: the typing went to the dialog (the field stayed empty, and
    the next `do`s went on). Closed on the next screen, the `do` that typed is asked again on its own and types."""
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply({"type": "input", "x": 3, "y": 3, "text": "a@b"})
        if n == 3:
            assert "do: type the password" in msg
            return reply({"type": "tap", "x": 9, "y": 9}, **COOKIE)
        if n == 4:
            assert AGAIN in msg and COVERED in msg and "do: type the email" in msg
            return reply({"type": "input", "x": 3, "y": 3, "text": "a@b"})
        if n == 5:
            assert "do: type the password" in msg
            assert "tap -> ok; the previous `do` was asked again on its own, since its last action may have hit " \
                   "that dialog: it went on: input (this is the screen after it)" in msg
            return reply({"type": "input", "x": 4, "y": 4, "text": "pw"})
        return reply({"type": "none"}, verify=[v("logged in")])

    res, drv, _, _ = make_run(LOGIN, script)
    assert [(a["type"], a.get("x")) for a in drv.acts] == [
        ("launch", None), ("input", 3), ("tap", 9), ("input", 3), ("input", 4)]
    assert [c["kind"] for c in res.calls] == ["do", "do", "do", "finish", "do", "judge"]
    assert res.calls[2]["after_do"] == 2 and res.calls[3]["session"] != res.calls[2]["session"]
    assert res.steps[1].notes == ["直後の割り込みを閉じた後に聞き直して続けた操作: input"]
    assert res.status == "pass"


def test_thens_are_not_judged_on_a_dialog_over_what_the_last_do_led_to(make_run):
    """No do is asked again after a launch (a dialog cannot take it). After the password, the dialog is closed in the
    judging call: its verdict is not used, the `do` is asked again (it needed nothing), and the `then` is judged on
    the next screen."""
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply({"type": "tap", "x": 9, "y": 9}, **COOKIE)  # right after the launch
        if n == 3:
            assert AGAIN not in msg
            return reply({"type": "input", "x": 3, "y": 3, "text": "a@b"})
        if n == 4:
            return reply({"type": "input", "x": 4, "y": 4, "text": "pw"})
        if n == 5:
            assert "only judge" in msg
            return reply({"type": "tap", "x": 9, "y": 9}, verify=[v("logged in", False)], **COOKIE)
        if n == 6:
            assert AGAIN in msg and COVERED in msg and "do: type the password" in msg
            return reply({"type": "none"})
        assert "only judge" in msg and "it needed nothing more" in msg
        return reply({"type": "none"}, verify=[v("logged in")])

    res, drv, _, _ = make_run(LOGIN, script)
    assert [(a["type"], a.get("x")) for a in drv.acts] == [
        ("launch", None), ("tap", 9), ("input", 3), ("input", 4), ("tap", 9)]
    assert [c["kind"] for c in res.calls] == ["do", "do", "do", "do", "judge", "finish", "judge"]
    assert "after_do" not in res.calls[1]
    assert res.calls[4]["note"].startswith("前の do の最後の操作の直後に割り込み")
    assert res.steps[3].status == "pass" and res.steps[3].calls == [7]
    assert res.status == "pass"


def test_a_do_left_in_front_of_a_dialog_is_asked_again_also_with_the_next_dos_thens(make_run):
    y = """
name: t
app: "http://x"
config: {interrupts: {allow: ["Cookie の同意"]}}
steps:
  - id: A
    actions:
      - do: "open the app"
      - do: "tap B"
      - then: "Y is shown"
      - do: "tap C"
"""

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply({"type": "tap", "x": 5, "y": 5})
        if n == 3:  # tap C, with the `then` of tap B: the dialog took the tap
            return reply({"type": "tap", "x": 9, "y": 9}, verify=[v("Y is shown", False)], **COOKIE)
        if n == 4:
            assert AGAIN in msg and COVERED in msg and "do: tap B" in msg and "Y is shown" not in msg
            return reply({"type": "tap", "x": 5, "y": 5})
        if n == 5:
            assert "do: tap C" in msg and "it went on: tap" in msg
            return reply({"type": "tap", "x": 6, "y": 6}, verify=[v("Y is shown")])
        return reply({"type": "none"})

    res, drv, _, _ = make_run(y, script)
    assert [a.get("x") for a in drv.acts] == [None, 5, 9, 5, 6]
    assert [c["kind"] for c in res.calls] == ["do", "do", "do", "finish", "do"]
    assert res.steps[2].status == "pass" and res.status == "pass"


def test_a_dialog_closed_after_a_stale_try_still_has_the_do_asked_again(make_run):
    drv = __import__("conftest").FakeDriver()
    drv.stale = [False, False, True]  # the first tap on the dialog finds the screen changed

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply({"type": "input", "x": 3, "y": 3, "text": "a@b"})
        if n in (3, 4):
            return reply({"type": "tap", "x": 9, "y": 9}, **COOKIE)
        if n == 5:
            assert AGAIN in msg and COVERED in msg
            return reply({"type": "none"})
        if n == 6:
            return reply({"type": "input", "x": 4, "y": 4, "text": "pw"})
        return reply({"type": "none"}, verify=[v("logged in")])

    res, drv, _, _ = make_run(LOGIN, script, driver=drv)
    assert [c["kind"] for c in res.calls] == ["do", "do", "do", "do", "finish", "do", "judge"]
    assert res.calls[2]["act_result"].startswith("未実行") and res.calls[3]["after_do"] == 2
    assert res.status == "pass"


def test_a_dialog_that_is_not_to_be_closed_asks_nothing_again(make_run):
    y = LOGIN.replace('config: {interrupts: {allow: ["Cookie の同意"]}}', "config: {interrupts: fail}")

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply({"type": "input", "x": 3, "y": 3, "text": "a@b"})
        return reply({"type": "tap", "x": 9, "y": 9}, purpose="interrupt", dialog="Cookie", done=False)

    res, drv, _, _ = make_run(y, script)
    assert [c["kind"] for c in res.calls] == ["do", "do", "do"]
    assert [a["type"] for a in drv.acts] == ["launch", "input"]
    assert res.steps[2].status == "fail" and "Cookie" in res.steps[2].reason


def test_the_message_that_asks_a_do_again_after_a_dialog_says_why():
    from uiai.ai.protocol import Ask, build_message

    m = build_message(Ask(section="s", do="type the email", again=True, covered=True))
    assert AGAIN in m and COVERED in m and "only if this screen shows that it did not take effect" in m
    assert COVERED not in build_message(Ask(section="s", do="type the email", again=True))


def test_do_failure_stops_the_scenario_and_marks_the_rest_not_run(make_run):
    y = BASIC + """
  - id: B
    actions:
      - do: "tap C"
      - then: "Z is shown"
"""

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        return reply({"type": "fail", "reason": "no B"}, verify=[v("X is shown")])

    res, drv, ai, ev = make_run(y, script)
    assert statuses(res) == [("do", "open the app", "pass"), ("then", "X is shown", "pass"),
                             ("do", "tap B", "fail"), ("then", "Y is shown", "not_run"),
                             ("do", "tap C", "not_run"), ("then", "Z is shown", "not_run")]
    fail = [e for e in ev if e["type"] == "fail"][0]
    assert fail["kind"] == "do" and fail["not_run"] == 3 and fail["reason"] == "no B"
    assert res.status == "fail"


def test_next_section_resets_the_app_and_continues(make_run):
    y = """
name: t
app: "http://x"
config: {on_failure: next_section}
steps:
  - id: A
    actions:
      - do: "open the app"
      - do: "tap B"
      - then: "Y is shown"
  - id: B
    actions:
      - do: "open the app again"
      - then: "Z is shown"
"""

    def script(msg, n):
        if "\ndo: tap B" in msg:  # not the "- [A] do: tap B -> FAILED" history line of section B
            return reply({"type": "fail", "reason": "no B"})
        if "only judge" in msg:
            return reply({"type": "none"}, verify=[v("Z is shown")])
        return reply({"type": "launch"})

    res, drv, _, _ = make_run(y, script)
    assert [s.status for s in res.steps] == ["pass", "fail", "not_run", "pass", "pass"]
    assert drv.resets == 2  # scenario start + before section B


def test_interrupt_report_mode_warns(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "tap", "x": 9, "y": 9}, purpose="interrupt", dialog="cookie", done=False)
        if n == 2:
            return reply({"type": "launch"})
        if n == 3:
            return reply(verify=[v("X is shown")])
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, drv, _, ev = make_run(BASIC, script)
    assert res.status == "pass_warn"
    assert res.steps[0].warnings == ["想定外のダイアログを閉じた: cookie"]
    assert any(e["type"] == "warning" for e in ev)
    assert not any(e["type"] == "fail" for e in ev)


def test_interrupt_on_allow_list_is_only_noted(make_run):
    y = BASIC.replace('app: "http://x"', 'app: "http://x"\nconfig: {interrupts: {allow: ["Cookie の同意"]}}')

    def script(msg, n):
        if n == 1:
            return reply({"type": "tap", "x": 9, "y": 9}, purpose="interrupt", dialog="cookie",
                         allowed="Cookie の同意", done=False)
        if n == 2:
            return reply({"type": "launch"})
        if n == 3:
            return reply(verify=[v("X is shown")])
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, _, _, _ = make_run(y, script)
    assert res.status == "pass" and res.steps[0].warnings == []
    assert res.steps[0].notes == ["割り込みを閉じた: cookie（許可: Cookie の同意）"]


def test_interrupt_fail_mode_fails_the_do_without_dismissing(make_run):
    y = BASIC.replace('app: "http://x"', 'app: "http://x"\nconfig: {interrupts: fail}')

    def script(msg, n):
        return reply({"type": "tap", "x": 9, "y": 9}, purpose="interrupt", dialog="cookie", done=False)

    res, drv, _, _ = make_run(y, script)
    assert drv.acts == []
    assert res.steps[0].status == "fail" and "cookie" in res.steps[0].reason


def test_error_dialog_fails_the_do(make_run):
    def script(msg, n):
        return reply({"type": "fail", "reason": "保存に失敗しました"}, error_shown=True)

    res, drv, _, _ = make_run(BASIC, script)
    assert res.steps[0].status == "fail" and res.steps[0].reason.startswith("エラー表示")
    assert drv.acts == []


def test_absence_then_is_observed_and_rechecked_when_the_screen_changes(make_run):
    y = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "save"
      - then: "no error is shown"
"""
    drv = __import__("conftest").FakeDriver()
    drv.watch_results = [True]  # the screen changes during the observation

    def script(msg, n):
        if n == 1:
            return reply()
        if n == 2:
            return reply({"type": "none"}, verify=[v("no error is shown", True, absence=True)])
        return reply({"type": "none"}, verify=[v("no error is shown", False, absence=True)])

    res, drv, ai, _ = make_run(y, script, driver=drv)
    assert drv.watched == [2.0]
    assert res.steps[1].status == "fail"  # error appeared after the first (passing) look


def test_absence_then_passes_when_nothing_changes(make_run):
    y = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "save"
      - then: "no error is shown"
        observe: 3
"""

    def script(msg, n):
        if n == 1:
            return reply()
        return reply({"type": "none"}, verify=[v("no error is shown", True, absence=True)])

    res, drv, ai, _ = make_run(y, script)
    assert drv.watched == [3.0] and res.steps[1].status == "pass" and len(ai.msgs) == 2


def test_absence_then_is_not_observed_while_the_previous_step_needs_finishing(make_run):
    # Real run: "save" opened a confirmation dialog; the negative then passed and was observed
    # before "保存する" was tapped, so the error shown after saving was missed.
    y = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "save"
      - then: "saved message is shown"
      - then: "no error is shown"
"""
    drv = __import__("conftest").FakeDriver()
    drv.watch_results = [True]

    def script(msg, n):
        if n == 1:
            return reply()
        if n == 2:  # dialog still open: finish it (the `do` is asked again for that)
            return reply({"type": "tap", "x": 7, "y": 7},
                         verify=[v("saved message is shown", False), v("no error is shown", True, absence=True)],
                         purpose="verify", done=False)
        if n == 3:
            assert AGAIN in msg and "do: save" in msg
            return reply({"type": "tap", "x": 7, "y": 7})
        if n == 4:
            return reply({"type": "none"}, verify=[v("saved message is shown"), v("no error is shown", True, absence=True)])
        return reply({"type": "none"}, verify=[v("no error is shown", False, absence=True)])

    res, drv, ai, _ = make_run(y, script, driver=drv)
    assert [a.get("x") for a in drv.acts] == [1, 7]
    assert drv.watched == [2.0]          # observed only after the dialog was finished
    assert res.steps[1].status == "pass" and res.steps[2].status == "fail"
    assert "否定形の then の観察は" in res.calls[1]["note"] and "聞き直す" in res.calls[1]["note"]


def test_action_on_a_stale_screen_is_skipped_and_reasked(make_run):
    drv = __import__("conftest").FakeDriver()
    drv.stale = [False, True]  # the 2nd action finds that the screen changed (a popup appeared)

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 3:
            assert "NOT executed" in msg
        if "only judge" in msg:
            return reply({"type": "none"}, verify=[v("Y is shown")])
        return reply(verify=[v("X is shown")] if n == 2 else [])

    res, drv, ai, _ = make_run(BASIC, script, driver=drv)
    assert [a["type"] for a in drv.acts] == ["launch", "tap"]
    assert res.calls[1]["act_result"].startswith("未実行")
    assert res.status == "pass"


def test_secret_is_never_sent_to_the_ai_and_is_redacted(make_run, monkeypatch):
    monkeypatch.setenv("T_PW", "hunter2xyz")
    y = """
name: t
app: "http://x"
variables:
  pw: {env: T_PW, secret: true}
steps:
  - id: A
    actions:
      - do: "type (pw) into the password field"
      - then: "logged in"
"""

    def script(msg, n):
        if n == 1:
            return reply({"type": "input", "x": 1, "y": 1, "text": "(pw)"})
        return reply({"type": "none"}, verify=[v("logged in", False, reason="saw hunter2xyz on screen")])

    res, drv, ai, ev = make_run(y, script)
    assert drv.acts[0]["text"] == "hunter2xyz" and drv.acts[0]["secret"] is True  # Android types it, not pastes
    assert all("hunter2xyz" not in m for m in ai.msgs)
    assert "(pw)" in ai.msgs[0]
    import json
    blob = json.dumps(ev, ensure_ascii=False)
    assert "hunter2xyz" not in blob and "****" in blob


def test_only_input_holding_a_secret_is_marked_for_the_driver(make_run, monkeypatch):
    monkeypatch.setenv("T_PW", "hunter2xyz")
    y = """
name: t
app: "http://x"
variables:
  user: taro
  pw: {env: T_PW, secret: true}
steps:
  - id: A
    actions:
      - do: "type (user) and (pw)"
      - then: "logged in"
"""

    def script(msg, n):
        if n <= 2:
            return reply({"type": "input", "x": 1, "y": 1, "text": ["taro", "x(pw)"][n - 1]}, done=n == 2)
        return reply({"type": "none"}, verify=[v("logged in")])

    res, drv, ai, ev = make_run(y, script)
    assert [(a["text"], a.get("secret")) for a in drv.acts] == [("taro", None), ("xhunter2xyz", True)]


def test_launch_without_instruction_and_noop_are_warned(make_run):
    y = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "open the app"
      - do: "tap B"
      - do: "turn dark mode on"
"""

    def script(msg, n):
        if "tap B" in msg:
            return reply({"type": "launch"})
        if "dark mode" in msg:
            return reply({"type": "none"})
        return reply({"type": "launch"})

    res, _, _, _ = make_run(y, script)
    assert res.steps[0].warnings == []
    assert res.steps[1].warnings == ["アプリを起動し直した（`do` は起動を指示していない）"]
    assert res.steps[2].warnings == ["操作せずに完了扱い（前提がシナリオの想定と違う可能性）"]
    assert res.status == "pass_warn"


def test_detour_warning_and_max_actions(make_run):
    y = """
name: t
app: "http://x"
config: {max_actions: 6}
steps:
  - id: A
    actions:
      - do: "open settings"
      - do: "search for Tokyo"
      - do: "open the profile"
      - do: "never done"
"""

    def script(msg, n):
        if "open settings" in msg:
            return reply(done=n >= 4)            # 4 actions: warned
        if "search for Tokyo" in msg:
            return reply(done=n >= 7)            # 3 actions (navigate, type, submit): not warned
        if "open the profile" in msg:
            return reply({"type": "back"} if n == 8 else None, done=n >= 9)  # unexpected back: warned
        return reply(done=False)

    res, _, _, _ = make_run(y, script)
    assert res.steps[0].warnings == [] and "操作 4 回" in res.steps[0].notes  # count: note only
    assert res.steps[1].warnings == []
    assert res.steps[2].warnings == ["戻る操作を挟んだ（`do` は戻ることを指示していない。遠回りの可能性）"]
    assert res.steps[3].status == "fail" and "上限（6 回）" in res.steps[3].reason


def test_black_screen_is_not_sent_to_the_ai(make_run):
    drv = __import__("conftest").FakeDriver()
    drv.detect_black, drv.black = True, True
    res, drv, ai, _ = make_run(BASIC, lambda m, n: reply(), driver=drv)
    assert ai.msgs == []
    assert res.steps[0].status == "fail" and "真っ黒" in res.steps[0].reason


def test_unparsable_reply_is_retried_once(make_run):
    def script(msg, n):
        if n == 1:
            return "sorry, here you go"
        if n == 2:
            assert "not a valid JSON" in msg
            return reply({"type": "launch"})
        if n == 3:
            return reply(verify=[v("X is shown")])
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, _, _, _ = make_run(BASIC, script)
    assert res.status == "pass"


def test_stop_all_flag(make_run):
    y = BASIC.replace('app: "http://x"', 'app: "http://x"\nconfig: {on_failure: stop_all}')

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        return reply({"type": "none"}, verify=[v("X is shown", False)])

    res, _, _, _ = make_run(y, script)
    assert res.stop_all
    assert res.steps[1].status == "fail" and res.steps[2].status == "not_run"


def test_scenario_timeout_fails_the_current_do(make_run, clock):
    y = BASIC.replace('app: "http://x"', 'app: "http://x"\nconfig: {timeout: 3}')

    def script(msg, n):
        clock.now += 2
        return reply({"type": "wait"}, done=False)

    res, _, _, _ = make_run(y, script)
    assert res.steps[0].status == "fail" and "config.timeout" in res.steps[0].reason
    assert res.steps[3].status == "not_run"



TWO_SECTIONS = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "open the app"
      - do: "tap B"
      - then: "Y is shown"
  - id: C
    actions:
      - do: "tap D"
      - do: "tap E"
      - then: "Z is shown"
"""


def rotate_at(monkeypatch, section, anywhere):
    import uiai.loop as loop_mod

    monkeypatch.setattr(loop_mod, "ROTATE_AT_SECTION", section)
    monkeypatch.setattr(loop_mod, "ROTATE_ANYWHERE", anywhere)


def test_small_conversations_are_not_rotated(make_run):
    res, _, ais, _ = make_run(TWO_SECTIONS, lambda msg, n: reply(verify=[v("Y is shown")] if '"Y is' in msg else
                                                                 [v("Z is shown")] if '"Z is' in msg else []),
                              fresh_ai=True)
    assert res.status == "pass" and len(ais) == 1


def test_a_large_conversation_is_rotated_at_the_next_section_after_judging_pending_thens(make_run, monkeypatch):
    rotate_at(monkeypatch, section=2000, anywhere=10**9)  # FakeAI: call n reports n*1000 input tokens

    def script(msg, n):
        if '"Y is shown"' in msg:
            assert "only judge" in msg  # judged on its own in the old conversation, not with "tap D"
            return reply({"type": "none"}, verify=[v("Y is shown")])
        if '"Z is shown"' in msg:
            return reply({"type": "none"}, verify=[v("Z is shown")])
        return reply()

    res, drv, ais, _ = make_run(TWO_SECTIONS, script, fresh_ai=True)
    assert res.status == "pass"
    assert len(ais) == 2 and all(a.closed for a in ais)
    first_c = ais[1].msgs[0]
    assert first_c.startswith("Earlier steps") and "- [A] then: Y is shown -> pass" in first_c
    assert "\ndo: tap D" in first_c and '"Y is shown"' not in first_c
    assert all("Earlier steps" not in m for m in ais[0].msgs + ais[1].msgs[1:])
    assert [c["kind"] for c in res.calls] == ["do", "do", "judge", "do", "do", "judge"]
    assert [c["session"] for c in res.calls] == [1, 1, 1, 2, 2, 2]


def test_a_very_large_conversation_is_rotated_between_dos_but_never_inside_a_do(make_run, monkeypatch):
    rotate_at(monkeypatch, section=10**9, anywhere=2000)
    yaml = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "one"
      - do: "two"
      - do: "three"
"""

    def script(msg, n):
        if "\ndo: two" in msg and "action 3" not in msg:  # "two" takes three actions
            return reply(done=False)
        return reply()

    res, drv, ais, _ = make_run(yaml, script, fresh_ai=True)
    assert res.status == "pass"
    # one(1 call) -> two: rotation needs 2000 tokens, so two runs in conversation 1 (3 calls, never
    # rotated inside) -> new conversation before "three"
    assert [c["session"] for c in res.calls] == [1, 1, 1, 1, 2]
    assert "- [A] do: two -> done" in ais[1].msgs[0]


def test_an_action_held_back_during_a_recheck_is_reported_as_not_executed(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply({"type": "tap", "x": 5, "y": 5}, verify=[v("X is shown", False)])
        if n == 3:
            assert "previous action: tap was NOT executed" in msg
            return reply(verify=[v("X is shown")])
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, drv, ai, _ = make_run(BASIC, script)
    assert res.status == "pass"


def _x_never_passes(msg, n):
    if n == 1:
        return reply({"type": "launch"})
    if '"X is shown"' in msg:
        return reply(verify=[v("X is shown", False)])
    return reply({"type": "none"}, verify=[v("Y is shown")])


def test_a_then_about_to_fail_passes_on_rejudge_with_a_warning(make_run, clock):
    seen = []

    def rejudge(msg):
        seen.append(msg)
        return {"pass": True, "reason": "X is there"}

    res, drv, ai, ev = make_run(BASIC, _x_never_passes, rejudge=rejudge)
    x = res.steps[1]
    assert x.status == "pass" and x.reason == "X is there"
    assert res.status == "pass_warn" and any("判定が分かれた" in w for w in x.warnings)
    assert len(seen) == 1 and "step just carried out: open the app" in seen[0] and "assertion: X is shown" in seen[0]
    assert not [e for e in ev if e["type"] == "fail"]
    rj = [c for c in res.calls if c.get("rejudge")]
    assert len(rj) == 1 and rj[0]["rejudge"][0]["model"] == "sonnet" and rj[0]["rejudge"][0]["pass"] is True
    assert rj[0]["rejudge"][0]["model_id"] == ""  # the fake does not know one; ApiSession's is recorded


def test_a_then_failing_on_rejudge_too_fails_with_both_reasons(make_run, clock):
    res, drv, ai, ev = make_run(BASIC, _x_never_passes, rejudge=lambda m: '{"pass": false, "reason": "no X"}')
    x = res.steps[1]
    assert x.status == "fail" and "再判定（sonnet）でも不合格: no X" in x.reason and not x.warnings
    assert [e["kind"] for e in ev if e["type"] == "fail"] == ["then"]


def test_a_failed_rejudge_call_keeps_the_fail(make_run, clock):
    from uiai.ai import AIError

    res, drv, ai, ev = make_run(BASIC, _x_never_passes, rejudge=lambda m: AIError("boom"))
    x = res.steps[1]
    assert x.status == "fail" and any("できなかった: boom" in nt for nt in x.notes)
    assert res.status == "fail"


def test_a_passing_then_is_not_rejudged(make_run, clock):
    calls = []
    res, *_ = make_run(BASIC, lambda m, n: reply(verify=[v("X is shown")] if '"X is' in m else [v("Y is shown")]),
                       rejudge=lambda m: calls.append(m) or {"pass": True, "reason": ""})
    assert res.status == "pass" and calls == []


# ---------------------------------------------------------------------------- unexpected failures


def test_an_unexpected_exception_ends_the_scenario_as_a_recorded_error(make_run, capsys):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        raise ValueError("bad thing")

    res, drv, ai, ev = make_run(BASIC, script)
    assert res.status == "error" and res.error == "想定外のエラー（ValueError）: bad thing"
    assert [e["reason"] for e in ev if e["type"] == "error"] == [res.error]
    assert ai.closed
    err = capsys.readouterr().err
    assert "Traceback" in err and "ValueError: bad thing" in err  # where it happened, for diagnosis


def test_running_out_of_time_at_a_section_boundary_fails_the_pending_then(make_run, clock):
    y = """
name: t
app: "http://x"
config: {on_failure: next_section, timeout: 3}
steps:
  - id: A
    actions:
      - do: "open the app"
      - then: "X is shown"
  - id: B
    actions:
      - do: "tap B"
"""

    def script(msg, n):
        clock.now += 1
        if n == 1:
            return reply({"type": "launch"})
        return reply({"type": "none"}, verify=[v("X is shown", False)])

    res, drv, ai, ev = make_run(y, script)
    assert [s.status for s in res.steps] == ["pass", "fail", "not_run"]
    assert "config.timeout" in res.steps[1].reason and res.status == "fail"
    (fail,) = [e for e in ev if e["type"] == "fail"]
    assert fail["kind"] == "then" and fail["not_run"] == 1  # reported like a failed `do` stopping the rest


def test_a_session_that_fails_to_close_does_not_lose_the_result(make_run, capsys):
    from conftest import FakeAI

    class BadClose(FakeAI):
        def close(self):
            raise RuntimeError("close failed")

    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply(verify=[v("X is shown")])
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, *_ = make_run(BASIC, None, factory=lambda system: BadClose(script))
    assert res.status == "pass"
    assert "RuntimeError: close failed" in capsys.readouterr().err


WAITS = """
name: t
app: "http://x"
steps:
  - id: A
    actions:
      - do: "open the app"
        wait: 2
      - then: "X is shown"
        wait: 1
      - do: "tap B"
      - then: "Y is shown"
"""


def test_scenario_wait_goes_to_the_driver_before_the_next_screenshot_and_the_loop_does_not_sleep(make_run, clock):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply(verify=[v("X is shown")])
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, drv, _, _ = make_run(WAITS, script)
    assert res.status == "pass"
    # the `do`'s and the `then`'s wait both reach the driver before the screenshot that judges "X is shown"
    assert drv.trace[:6] == ["reset", "observe", "act:launch", "wait:2", "wait:1", "observe"]
    assert clock.now == 1000.0  # waiting is the driver's job (counted from the action, see test_wait.py)


def test_wait_of_the_last_do_is_waited_out_before_a_reset_and_at_the_end(make_run):
    y = """
name: t
app: "http://x"
config: {on_failure: next_section, stop_app_after: true}
steps:
  - id: A
    actions:
      - do: "save"
        wait: 3
  - id: B
    actions:
      - do: "save again"
        wait: 3
"""
    res, drv, _, _ = make_run(y, lambda msg, n: reply())
    assert res.status == "pass"
    assert drv.trace == ["reset", "observe", "act:tap", "wait:3", "wait_out", "reset",
                       "observe", "act:tap", "wait:3", "wait_out", "stop_app"]
