from __future__ import annotations

from conftest import reply, v

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


def test_verify_action_during_recheck_is_executed(make_run):
    def script(msg, n):
        if n == 1:
            return reply({"type": "launch"})
        if n == 2:
            return reply({"type": "tap", "x": 5, "y": 5}, verify=[v("X is shown", False)], purpose="verify", done=False)
        if n == 3:
            return reply(verify=[v("X is shown")])
        return reply({"type": "none"}, verify=[v("Y is shown")])

    res, drv, _, _ = make_run(BASIC, script)
    assert [(a["type"], a.get("x")) for a in drv.acts] == [("launch", None), ("tap", 5), ("tap", 1)]
    assert "判定のための操作: tap" in res.steps[2].notes
    assert res.status == "pass"


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
        if n == 2:  # dialog still open: finish it
            return reply({"type": "tap", "x": 7, "y": 7},
                         verify=[v("saved message is shown", False), v("no error is shown", True, absence=True)],
                         purpose="verify", done=False)
        if n == 3:
            return reply({"type": "none"}, verify=[v("saved message is shown"), v("no error is shown", True, absence=True)])
        return reply({"type": "none"}, verify=[v("no error is shown", False, absence=True)])

    res, drv, ai, _ = make_run(y, script, driver=drv)
    assert [a.get("x") for a in drv.acts] == [1, 7]
    assert drv.watched == [2.0]          # observed only after the dialog was finished
    assert res.steps[1].status == "pass" and res.steps[2].status == "fail"


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
    assert drv.acts[0]["text"] == "hunter2xyz"
    assert all("hunter2xyz" not in m for m in ai.msgs)
    assert "(pw)" in ai.msgs[0]
    import json
    blob = json.dumps(ev, ensure_ascii=False)
    assert "hunter2xyz" not in blob and "****" in blob


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
