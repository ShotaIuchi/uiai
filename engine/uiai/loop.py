"""The execution loop: program drives, AI decides (design doc 8).

One AI call per step returns the verdicts for the pending `then`s and the next action.
`then`s are judged on the first settled screen after the previous `do`; a failed `then`
is re-checked on fresh screens until `then.timeout`; a passed negative `then` is watched
for `then.observe` seconds. A `do` that cannot be done stops the scenario (default).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .ai import AIError
from .ai.protocol import Ask, build_message, parse_reply, system_prompt
from .drivers.base import STALE, Driver, DriverError
from .events import EventLog
from .redact import Redactor
from .scenario import Item, Scenario, fill_secrets, render

EXECUTABLE = ("tap", "input", "key", "scroll", "back", "launch")
LAUNCH_WORDS = re.compile(r"起動|開く|開いて|ひらく|立ち上げ|アクセス|launch|open|start|restart|visit", re.I)
# Detour warning: going `back` inside a `do` that does not ask for it (the AI entered a wrong screen and
# came back). The number of actions is NOT used: in real runs compound `do`s legitimately took 3-4 actions
# ("…でログインする" = type email, tap field, type password, tap login), so a count threshold only produced
# false warnings. The count stays visible in the report's call list.
BACK_WORDS = re.compile(r"戻|back", re.I)
# An action is skipped if the screen changed after the AI's screenshot (popup appeared meanwhile).
# With continuously animated screens this would never end, so after this many skips per `do` it acts anyway.
MAX_STALE_SKIPS = 2
STALE_LABEL = "未実行（AI の判断後に画面が変わったため撮り直す）"

STATUS_LABEL = {"pass": "合格", "pass_warn": "警告付き合格", "fail": "不合格", "error": "実行エラー",
                "skipped": "未実行（スキップ）", "not_run": "未実行"}


class StopScenario(Exception):
    """Abort the scenario (timeout); the current `do` is failed with `reason`."""


class StopAll(Exception):
    """on_failure: stop_all and a `then` failed: stop before running the current `do`."""


@dataclass
class StepResult:
    index: int
    kind: str
    section: str
    origin: str
    text: str
    strict: bool = False
    status: str = "not_run"     # pass | fail | not_run
    reason: str = ""
    read: str | None = None
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    calls: list[int] = field(default_factory=list)


@dataclass
class ThenState:
    item: Item
    text: str
    started: float | None = None
    observed: bool = False
    absence: bool = False
    final: str | None = None


@dataclass
class ScenarioResult:
    name: str
    file: str
    platform: str
    target: str
    model: str
    status: str = "pass"   # pass | pass_warn | fail | error | skipped
    error: str = ""
    steps: list[StepResult] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    check_warnings: list[str] = field(default_factory=list)
    started_at: str = ""
    seconds: float = 0.0
    stop_all: bool = False

    def counts(self) -> dict:
        c = {"pass": 0, "fail": 0, "not_run": 0, "warnings": 0}
        for s in self.steps:
            c[s.status] = c.get(s.status, 0) + 1
            c["warnings"] += len(s.warnings)
        return c


class ScenarioRunner:
    def __init__(self, sc: Scenario, platform: str, target: str, driver: Driver,
                 ai_factory: Callable[[str], object], values: dict[str, str], out_dir: Path,
                 events: EventLog, redactor: Redactor, model: str,
                 printer: Callable[[str], None] = lambda s: print(s, flush=True)):
        self.sc, self.platform, self.app, self.drv = sc, platform, target, driver
        self.ai_factory, self.values, self.out = ai_factory, values, out_dir
        self.events, self.redact, self.print = events, redactor, printer
        self.cfg = sc.config
        self.secrets = sc.secret_names
        self.ai = None
        self.res = ScenarioResult(sc.name, str(sc.path), platform, target, model,
                                  check_warnings=[str(w) for w in sc.warnings])
        self.steps = {it.index: StepResult(it.index, it.kind, it.section, it.origin, self.text(it), it.strict)
                      for it in sc.items}
        self.res.steps = list(self.steps.values())
        self.items = sc.items
        self.t0 = 0.0
        self.section_first_do = True

    # ------------------------------------------------------------------ helpers
    def text(self, it: Item) -> str:
        return render(it.raw, self.values, self.secrets)

    def ev(self, type_: str, **kw) -> None:
        self.events.emit(type_, scenario=self.sc.name, platform=self.platform, file=str(self.sc.path), **kw)

    def elapsed(self) -> float:
        return time.time() - self.t0

    def check_time(self) -> None:
        if self.elapsed() > self.cfg.timeout:
            raise StopScenario(f"シナリオの上限時間（config.timeout = {self.cfg.timeout:g} 秒）を超えた")

    def warn(self, step: StepResult, msg: str) -> None:
        step.warnings.append(msg)
        self.ev("warning", section=step.section, step=step.index + 1, kind=step.kind, text=step.text, message=msg)
        self.print(f"    ! 警告: {msg}")

    # ------------------------------------------------------------------ AI call
    def observe(self):
        """Settled screen. An all-black screen (FLAG_SECURE?) is waited out up to then_timeout,
        then returned as is for the caller to fail (it is never sent to the AI)."""
        black_since = None
        while True:
            self.check_time()
            obs = self.drv.observe()
            if not (obs.black and self.drv.detect_black):
                return obs
            black_since = black_since or time.time()
            if time.time() - black_since > self.cfg.then_timeout:
                return obs
            time.sleep(1.0)

    def ask(self, a: Ask, obs, kind: str, step_index: int | None) -> tuple[dict, dict]:
        self.check_time()
        msg = build_message(a)
        reply, meta = self.ai.ask(msg, obs.jpeg)
        res = parse_reply(reply)
        if res is None:
            reply2, meta2 = self.ai.ask("Your previous reply was not a valid JSON object. "
                                        "Reply again with ONLY the JSON object for the same screen.")
            res = parse_reply(reply2)
            meta = {k: meta[k] + meta2[k] for k in ("wall_s", "api_s", "out_tokens")} | {"in_tokens": meta2["in_tokens"]}
            if res is None:
                res = {"verify": [], "action": {"type": "fail", "reason": "AI の応答を解釈できない: " + reply2[:120]},
                       "purpose": "step", "dialog": "", "allowed": "", "error_shown": False, "done": False}
        n = len(self.res.calls) + 1
        img = f"call_{n:02d}.jpg"
        (self.out / img).write_bytes(obs.jpeg)
        rec = {
            "n": n, "t": round(self.elapsed(), 2), "kind": kind, "section": a.section,
            "step": None if step_index is None else step_index + 1, "do": a.do,
            "thens": [t for t, _ in a.thens or []], "verify": res["verify"], "action": res["action"],
            "purpose": res["purpose"], "dialog": res["dialog"], "allowed": res["allowed"],
            "error_shown": res["error_shown"], "done": res["done"], "act_result": "",
            "image": img, "iw": obs.width, "ih": obs.height, "screen_changed": obs.changed,
            "obs_s": obs.seconds, "obs_polls": obs.polls, "llm_s": meta["wall_s"], "api_s": meta["api_s"],
            "in_tokens": meta["in_tokens"], "out_tokens": meta["out_tokens"], "note": "",
        }
        self.res.calls.append(rec)
        if step_index is not None:
            self.steps[step_index].calls.append(n)
        return res, rec

    def log_call(self, rec: dict) -> None:
        act = rec["action"] or {}
        t = act.get("type")
        tgt = (f" ({act.get('x')},{act.get('y')})" if "x" in act else "") + \
              (f" {act.get('text')!r}" if t == "input" else "") + (f" {act.get('key')}" if t == "key" else "")
        tag = {"interrupt": " [割り込み]", "verify": " [判定のため]"}.get(rec["purpose"], "")
        what = "判定のみ" if rec["do"] is None else f"「{rec['do']}」"
        res = "" if rec["act_result"] in ("", "ok") else f" -> {rec['act_result']}"
        self.print(self.redact.text(
            f"  #{rec['n']:02d} [{rec['section']}] {what} {rec['kind']}: {t}{tgt}{tag}{res}"
            f" | 撮影 {rec['obs_s']}s AI {rec['llm_s']}s" + (f" | {rec['note']}" if rec["note"] else "")))

    # ------------------------------------------------------------------ then judging
    def judge(self, undecided: list[ThenState], res: dict, rec: dict) -> bool:
        """Apply verdicts. Returns True if some `then` must be re-checked on a fresh screen.

        A passed negative `then` is only observed (and so confirmed) once the screen is final:
        not while another `then` is being re-checked or the previous `do` still needs a finishing
        action (e.g. a confirmation dialog) - otherwise an error shown after that action is missed.
        """
        now = time.time()
        verdicts = res["verify"]
        act = res["action"] or {}
        finishing = res["purpose"] == "verify" and act.get("type") in EXECUTABLE
        retrying = False
        passed_absence: list[ThenState] = []
        for i, t in enumerate(undecided):
            v = verdicts[i] if len(verdicts) == len(undecided) else next(
                (x for x in verdicts if str(x.get("then", "")).replace(" [strict]", "") == t.text), None)
            if v is None:
                v = {"pass": False, "reason": "AI が判定を返さなかった"}
            t.started = t.started or now
            step = self.steps[t.item.index]
            step.reason = str(v.get("reason", ""))
            step.read = v.get("read") if t.item.strict else None
            t.absence = t.absence or v.get("absence") in (True, "true", "True")
            if step.calls[-1:] != [rec["n"]]:
                step.calls.append(rec["n"])
            if v.get("pass") in (True, "true", "True"):
                if t.absence and t.item.observe > 0 and not t.observed:
                    passed_absence.append(t)
                else:
                    self.finalize(t, "pass")
            elif now - t.started >= t.item.timeout:
                self.finalize(t, "fail")
            else:
                retrying = True
        if passed_absence and (finishing or retrying):
            rec["note"] = "否定形の then の観察は、前の操作が終わり画面が確定してから行う"
        elif passed_absence:
            secs = max(t.item.observe for t in passed_absence)
            changed = self.drv.watch(secs)
            rec["note"] = f"否定形の then を {secs:g} 秒観察: " + ("画面が変わった" if changed else "変化なし")
            for t in passed_absence:
                t.observed = True
                if not changed:
                    self.finalize(t, "pass")
        return any(t.final is None for t in undecided)

    def finalize(self, t: ThenState, status: str, reason: str | None = None) -> None:
        t.final = status
        step = self.steps[t.item.index]
        step.status = status
        if reason is not None:
            step.reason = reason
        if status == "fail":
            self.res.stop_all = self.cfg.on_failure == "stop_all"
            img = self.res.calls[step.calls[-1] - 1]["image"] if step.calls else None
            self.ev("fail", section=step.section, step=step.index + 1, kind="then", text=step.text,
                    reason=step.reason, read=step.read, image=str(self.out / img) if img else None)
            self.print(self.redact.text(f"  ✗ then 不合格 [{step.section}] 「{step.text}」: {step.reason}"))

    def recheck_action(self, res: dict, rec: dict, step: StepResult | None) -> None:
        """While a `then` is being re-checked: run only verify/interrupt actions, otherwise wait."""
        act = res["action"] or {}
        if res["purpose"] in ("verify", "interrupt") and act.get("type") in EXECUTABLE:
            if res["purpose"] == "interrupt" and not self.interrupt_allowed(res, step):
                time.sleep(1.0)
                return
            result = self.drv.act(self.fill(act), self.app, check_stale=True)
            if result == STALE:
                rec["act_result"] = STALE_LABEL
                return
            rec["act_result"] = self.redact.text(result)
            if step is not None and res["purpose"] == "verify":
                step.notes.append(f"判定のための操作: {act.get('type')}")
        else:
            time.sleep(1.0)

    def interrupt_allowed(self, res: dict, step: StepResult | None) -> bool:
        """Record an interrupt per config.interrupts. False if it must not be executed (mode=fail)."""
        mode, allowed = self.cfg.interrupts.mode, bool(res["allowed"])
        dialog = res["dialog"] or "（内容不明）"
        if allowed or mode == "allow":
            if step is not None:
                step.notes.append(f"割り込みを閉じた: {dialog}" + (f"（許可: {res['allowed']}）" if allowed else ""))
            return True
        if mode == "fail":
            return False
        if step is not None:
            self.warn(step, f"想定外のダイアログを閉じた: {dialog}")
        return True

    def fill(self, act: dict) -> dict:
        if act.get("type") == "input" and act.get("text"):
            return dict(act, text=fill_secrets(str(act["text"]), self.values, self.secrets))
        return act

    def judge_only(self, pending: list[ThenState]) -> None:
        while True:
            undecided = [t for t in pending if t.final is None]
            if not undecided:
                return
            obs = self.observe()
            if obs.black and self.drv.detect_black:
                for t in undecided:
                    self.finalize(t, "fail", "撮影できない画面の可能性（画面が真っ黒。FLAG_SECURE など）")
                return
            a = Ask(section=self.steps[undecided[0].item.index].section, do=None,
                    thens=[(t.text, t.item.strict) for t in undecided],
                    recheck=any(t.started for t in undecided))
            res, rec = self.ask(a, obs, "judge", None)
            if self.judge(undecided, res, rec):
                self.recheck_action(res, rec, self.steps[undecided[0].item.index])
            self.log_call(rec)

    # ------------------------------------------------------------------ do
    def run_do(self, it: Item, pending: list[ThenState]) -> tuple[bool, str]:
        step = self.steps[it.index]
        text = step.text
        n_do = sum(1 for x in self.items if x.kind == "do")
        do_no = sum(1 for x in self.items if x.kind == "do" and x.index <= it.index)
        actions, step_actions, feedback, last, went_back, stale_skips = 0, 0, "", None, False, 0
        while True:
            if actions >= self.cfg.max_actions:
                return False, f"操作回数の上限（{self.cfg.max_actions} 回）に達した"
            obs = self.observe()
            undecided = [t for t in pending if t.final is None]
            if obs.black and self.drv.detect_black:
                return False, "撮影できない画面の可能性（画面が真っ黒。FLAG_SECURE など）"
            if last is not None:
                fb = feedback
                if obs.changed is False:
                    fb += "; the screen did not change"
            else:
                fb = ""
            a = Ask(section=it.section, do=text, do_strict=it.strict, step_no=do_no, step_total=n_do,
                    thens=[(t.text, t.item.strict) for t in undecided], attempt=actions,
                    recheck=any(t.started for t in undecided), feedback=fb)
            res, rec = self.ask(a, obs, "do" if not undecided or not any(t.started for t in undecided) else "recheck",
                                it.index)
            if undecided and self.judge(undecided, res, rec):
                self.recheck_action(res, rec, step)
                self.log_call(rec)
                continue
            if self.res.stop_all:
                self.log_call(rec)
                raise StopAll()
            act = res["action"] or {}
            t = act.get("type")
            if res["error_shown"]:
                self.log_call(rec)
                return False, "エラー表示: " + str(act.get("reason") or res.get("dialog") or "")
            if t == "fail":
                self.log_call(rec)
                return False, str(act.get("reason") or "AI が実行できないと判断した")
            if res["purpose"] == "interrupt" and not self.interrupt_allowed(res, step):
                self.log_call(rec)
                return False, f"想定外のダイアログ: {res['dialog'] or '（内容不明）'}（config.interrupts.mode = fail）"
            if t == "launch" and not (self.section_first_do or LAUNCH_WORDS.search(text)):
                self.warn(step, "アプリを起動し直した（`do` は起動を指示していない）")
            if t == "none" and res["purpose"] == "step" and actions == 0:
                self.warn(step, "操作せずに完了扱い（前提がシナリオの想定と違う可能性）")
            result = (self.drv.act(self.fill(act), self.app, check_stale=stale_skips < MAX_STALE_SKIPS)
                      if t not in (None, "none") else "ok")
            if result == STALE:
                stale_skips += 1
                rec["act_result"] = STALE_LABEL
                self.log_call(rec)
                last = act
                feedback = f"{t} was NOT executed: the screen changed after the screenshot (look again)"
                continue
            rec["act_result"] = self.redact.text(result)
            self.log_call(rec)
            actions += 1
            if res["purpose"] == "step" and t not in ("scroll", "wait", "none"):
                step_actions += 1
            went_back = went_back or (t == "back" and res["purpose"] == "step")
            last = act
            feedback = f"{t} -> {rec['act_result']}"
            if result != "ok":
                feedback += " (the action failed)"
                continue
            if res["done"] and res["purpose"] == "step":
                break
        if went_back and not BACK_WORDS.search(text):
            self.warn(step, "戻る操作を挟んだ（`do` は戻ることを指示していない。遠回りの可能性）")
        if step_actions > 1:
            step.notes.append(f"操作 {step_actions} 回")
        return True, ""

    # ------------------------------------------------------------------ scenario
    def fail_do(self, it: Item, reason: str, rest: list[Item], pending: list[ThenState]) -> None:
        step = self.steps[it.index]
        step.status, step.reason = "fail", reason
        for t in pending:
            if t.final is None:
                self.finalize(t, "fail", f"判定できなかった（{reason}）")
        img = self.res.calls[step.calls[-1] - 1]["image"] if step.calls else None
        self.ev("fail", section=it.section, step=it.index + 1, kind="do", text=step.text, reason=reason,
                image=str(self.out / img) if img else None, not_run=len(rest))
        self.print(self.redact.text(f"  ✗ do 失敗 [{it.section}] 「{step.text}」: {reason}"
                                    + (f"（残り {len(rest)} ステップは未実行）" if rest else "")))
        self.res.stop_all = self.cfg.on_failure == "stop_all"

    def run(self) -> ScenarioResult:
        self.t0 = time.time()
        self.res.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.ev("scenario_start", target=self.app)
        self.print(f"▶ {self.sc.name} @ {self.platform}（{self.app}）")
        pending: list[ThenState] = []
        try:
            self.drv.reset(self.app, self.cfg)
            self.ai = self.ai_factory(system_prompt(self.drv.description, self.drv.iw, self.drv.ih,
                                                    self.cfg.interrupts.allow, sorted(self.secrets)))
            sections = self.sc.sections
            stop = False
            for si, sec in enumerate(sections):
                if stop:
                    break
                if si > 0 and self.cfg.on_failure == "next_section":
                    if pending:
                        self.judge_only(pending)
                        pending = []
                    self.drv.reset(self.app, self.cfg)
                    self.section_first_do = True
                for k, it in enumerate(sec.items):
                    if it.kind == "then":
                        if it.wait:
                            time.sleep(it.wait)
                        pending.append(ThenState(it, self.steps[it.index].text))
                        continue
                    try:
                        ok, reason = self.run_do(it, pending)
                    except StopScenario as e:
                        ok, reason, stop_now = False, str(e), True
                    except StopAll:
                        self.print("  ■ on_failure: stop_all — 以降は実行しない")
                        stop = True
                        break
                    else:
                        stop_now = False
                    pending = [t for t in pending if t.final is None]
                    if not ok:
                        if stop_now or self.cfg.on_failure != "next_section":
                            rest = [x for x in self.items if x.index > it.index]
                            stop = True
                        else:
                            rest = sec.items[k + 1:]
                        self.fail_do(it, reason, rest, pending)
                        pending = []
                        break
                    self.steps[it.index].status = "pass"
                    self.section_first_do = False
                    if it.wait:
                        time.sleep(it.wait)
                    if self.res.stop_all:
                        stop = True
                        break
            if pending and not stop:
                try:
                    self.judge_only(pending)
                except StopScenario as e:
                    for t in pending:
                        if t.final is None:
                            self.finalize(t, "fail", str(e))
            if self.cfg.stop_app_after:
                self.drv.stop_app(self.app)
        except (AIError, DriverError) as e:
            self.res.status, self.res.error = "error", self.redact.text(str(e))
            self.ev("error", reason=self.res.error)
            self.print(f"  ✗ 実行エラー: {self.res.error}")
        finally:
            if self.ai is not None:
                self.ai.close()
            self.res.seconds = round(self.elapsed(), 1)
        if self.res.status != "error":
            c = self.res.counts()
            self.res.status = "fail" if c["fail"] or c["not_run"] else ("pass_warn" if c["warnings"] else "pass")
        self.ev("scenario_end", status=self.res.status, counts=self.res.counts(), seconds=self.res.seconds)
        self.print(f"■ {self.sc.name} @ {self.platform}: {STATUS_LABEL[self.res.status]}（{self.res.seconds} 秒）")
        return self.res
