"""The execution loop: program drives, AI decides (design doc 8).

One AI call per step returns the verdicts for the pending `then`s and the next action.
`then`s are judged on the first settled screen after the previous `do`; a failed `then`
is re-checked on fresh screens until `then.timeout`; a passed negative `then` is watched
for `then.observe` seconds. A `do` that cannot be done stops the scenario (default).
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .ai import AIError
from .ai.protocol import (Ask, build_judge_message, build_message, judge_system_prompt, parse_judge, parse_reply,
                          system_prompt)
from .drivers.base import STALE, Driver, DriverError
from .events import EventLog
from .redact import Redactor, traceback_to_stderr
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
# Conversations (design doc 10): every screenshot stays in the claude -p conversation (~1.6k tokens each on
# Web). Measured in phase 4, the input size barely changes the response time (0.44 ms per 1k tokens; the
# output length dominates), but it costs tokens and would hit the context window (200k) after ~120 calls.
# Starting a new conversation has a cost too: its first replies came with 2-3x more (thinking) output, and
# the AI misread a carried-over `then` as the result of the new `do`. So a new conversation is started only
# when the current one is large: at the next section boundary, or before any `do` when it is very large.
# Pending `then`s are judged in the old conversation first; earlier steps are carried over as text.
# Never mid-`do`: the message already has what a `do` in progress needs (attempt, feedback).
ROTATE_AT_SECTION = 50_000   # input tokens of the last call
ROTATE_ANYWHERE = 100_000
HISTORY_STEPS = 12           # earlier steps carried over to a new conversation
# What each device keeps while the scenario is on another one (`on`): its conversation, the app in use, whether
# its next `do` is the first since it was (re)set or its app changed (a launch is then not a detour), and what
# its next message must tell the AI first.
DEVICE_STATE = ("ai", "system", "session_id", "session_calls", "session_tokens", "session_section", "app",
                "section_first_do", "notice")

STATUS_LABEL = {"pass": "合格", "pass_warn": "警告付き合格", "fail": "不合格", "error": "実行エラー",
                "skipped": "未実行（スキップ）", "not_run": "未実行", "skip": "スキップ（optional）"}


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
    platform: str = ""          # the device it runs on (a section's `on`, else the scenario's)
    status: str = "not_run"     # pass | fail | not_run | skip (an optional `do` that failed)
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
    others: dict[str, str] = field(default_factory=dict)  # platform -> target of the sections with `on`
    backend: str = ""  # claude-code | api: the one asked for, then the one each opened session reports
    model_id: str = ""  # the model ID sent, when the backend knows it (api); claude-code resolves it itself
    status: str = "pass"   # pass | pass_warn | fail | error | skipped
    error: str = ""
    steps: list[StepResult] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    check_warnings: list[str] = field(default_factory=list)
    started_at: str = ""
    seconds: float = 0.0
    stop_all: bool = False

    def counts(self) -> dict:
        c = {"pass": 0, "fail": 0, "not_run": 0, "skip": 0, "warnings": 0}
        for s in self.steps:
            c[s.status] = c.get(s.status, 0) + 1
            c["warnings"] += len(s.warnings)
        return c


class ScenarioRunner:
    def __init__(self, sc: Scenario, platform: str, target: str, driver: Driver,
                 ai_factory: Callable[[str], object], values: dict[str, str], out_dir: Path,
                 events: EventLog, redactor: Redactor, model: str,
                 printer: Callable[[str], None] = lambda s: print(s, flush=True), *,
                 rejudge_factory: Callable[[str], object] | None = None, rejudge_model: str = "",
                 backend: str = "", type_delay: float | None = None,
                 others: dict[str, tuple[Driver, str]] | None = None):
        """others: (driver, target) for each other platform that sections switch to with `on`."""
        self.sc, self.platform, self.app, self.drv = sc, platform, target, driver
        # every device of the scenario; the one in use is self.cur (self.drv, self.app)
        self.targets = {platform: (driver, target), **{p: o for p, o in (others or {}).items() if p != platform}}
        self.multi = len(self.targets) > 1
        self.cur: str | None = None
        self.parked: dict[str, dict] = {}  # DEVICE_STATE of the devices not in use
        self.notice = ""  # to put before the next message (a device just switched to, another app)
        self.ai_factory, self.values, self.out = ai_factory, values, out_dir
        self.rejudge_factory, self.rejudge_model = rejudge_factory, rejudge_model
        self.events, self.redact, self.print = events, redactor, printer
        self.cfg = sc.config
        # ms between typed characters: --type-delay wins over config.type_delay
        self.type_delay = sc.config.type_delay if type_delay is None else type_delay
        self.secrets = sc.secret_names
        self.ai = None
        self.res = ScenarioResult(sc.name, str(sc.path), platform, target, model, backend=backend,
                                  others={p: t for p, (_, t) in self.targets.items() if p != platform},
                                  check_warnings=[str(w) for w in sc.warnings])
        on = {s.id: s.on or platform for s in sc.sections}
        self.steps = {it.index: StepResult(it.index, it.kind, it.section, it.origin, self.text(it), it.strict,
                                           on[it.section]) for it in sc.items}
        self.res.steps = list(self.steps.values())
        self.items = sc.items
        self.t0 = 0.0
        self.section_first_do = True
        self.system = ""
        self.session_no = 0          # conversations started so far
        self.session_id = 0          # the number of the one in use (with `on`, an earlier one may be taken up again)
        self.session_calls = 0       # calls in the current conversation
        self.session_tokens = 0      # input tokens of its last call
        self.session_section = -1    # section of the last `do` run in it
        self.carry_history = False   # prepend earlier steps to the next message
        self.closing: list[threading.Thread] = []

    # ------------------------------------------------------------------ helpers
    def text(self, it: Item) -> str:
        return render(it.raw, self.values, self.secrets)

    def ev(self, type_: str, **kw) -> None:
        if self.multi and self.cur and self.cur != self.platform and type_ in ("fail", "skip", "warning", "error"):
            kw.setdefault("device", self.cur)  # a step in a section with `on`: where it happened
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

    # ------------------------------------------------------------------ AI sessions
    def open_session(self) -> None:
        """Start a fresh conversation. The old one is closed in the background (~0.6 s); the new one starts
        up (~0.4 s) while the next screen settles, since this runs before the next observe."""
        old = self.ai
        self.ai = self.ai_factory(self.system)
        self.res.backend = getattr(self.ai, "backend", self.res.backend)  # what actually runs wins
        self.res.model_id = getattr(self.ai, "model_id", self.res.model_id)
        self.session_no += 1
        self.session_id = self.session_no
        self.session_calls = self.session_tokens = 0
        self.carry_history = self.session_no > 1
        if old is not None:
            th = threading.Thread(target=old.close, daemon=True)
            th.start()
            self.closing.append(th)

    def before_do(self, section_index: int, pending: list[ThenState]) -> None:
        """Start a new conversation if the current one is large (see ROTATE_*)."""
        new_section = section_index != self.session_section
        if self.session_calls and (self.session_tokens >= ROTATE_ANYWHERE
                                   or (new_section and self.session_tokens >= ROTATE_AT_SECTION)):
            if any(t.final is None for t in pending):
                self.judge_only(pending)  # in the old conversation, on the screen the previous `do` left
                if self.res.stop_all:
                    raise StopAll()
            self.open_session()
        self.session_section = section_index

    def history_text(self) -> str:
        done = [s for s in self.res.steps if s.status in ("pass", "fail", "skip")][-HISTORY_STEPS:]
        if not done:
            return ""
        label = {"pass": "done", "fail": "FAILED", "skip": "FAILED (optional: skipped, the scenario went on)"}
        lines = [f"- [{s.section}{f' @ {s.platform}' if self.multi else ''}] {s.kind}: {s.text} -> "
                 f"{label[s.status] if s.kind == 'do' else s.status}" for s in done]
        head = ("Earlier steps of this scenario (on this or another device, each device in its own conversation; "
                f"you are now on {self.cur}; screenshots of other conversations are not repeated)" if self.multi else
                "Earlier steps of this scenario (from a previous conversation; their screenshots are not repeated)")
        return head + ":\n" + "\n".join(lines) + "\n\n"

    def apps(self) -> list[tuple[Driver, str]]:
        """(driver, app) of every app the scenario uses: the scenario's on each device, and those of the
        included sections that differ."""
        out = list(self.targets.values())
        for sec in self.sc.sections:
            plat = sec.on or self.platform
            pair = (self.targets[plat][0], sec.targets.get(plat) or self.targets[plat][1])
            if pair not in out:
                out.append(pair)
        return out

    def use(self, platform: str, app: str | None = None) -> None:
        """Switch to the device of `platform` and its app `app` (default: the scenario's; an included section
        has its own). Each device has its own conversation, since the system prompt describes its screen; the
        one left is parked for when the scenario comes back to that device."""
        app = app or self.targets[platform][1]
        if platform == self.cur:
            self.use_app(app)
            return
        switching = self.cur is not None
        if switching:
            self.drv.wait_out()  # a `wait` of the last `do` there is over before going on elsewhere
            self.parked[self.cur] = {k: getattr(self, k) for k in DEVICE_STATE}
            self.print(f"  ⇄ {platform} に切り替え（{app}）")
        self.cur = platform
        self.drv = self.targets[platform][0]
        if platform in self.parked:
            for k, v in self.parked.pop(platform).items():
                setattr(self, k, v)
            self.carry_history = True  # what was done on the other device meanwhile
            self.use_app(app)
            return
        self.ai = None  # the conversation of the device left is parked, not closed
        self.system = system_prompt(self.drv.description, self.drv.iw, self.drv.ih,
                                    self.cfg.interrupts.allow, sorted(self.secrets),
                                    optional=any(it.optional for it in self.items))
        self.open_session()
        self.app, self.section_first_do = app, True
        # A blank page did not tell the AI that the admin page of "open the admin page and ..." was not open yet:
        # it waited and failed (real run, Web after Android).
        self.notice = (f"You have just switched to {self.drv.description} (`on: {platform}`). It was reset before "
                       "the scenario started and has not been used since: the app under test is not open yet. Use "
                       "\"launch\" to open it if the step needs it.\n\n") if switching else ""

    def use_app(self, app: str) -> None:
        """Go on with another app on the same device (sections of an included scenario, or back from them)."""
        if app == self.app:
            return
        self.print(f"  → {app}")
        self.app = app
        self.section_first_do = True  # launching it is not a detour
        self.notice = (f"The app under test is now {app} (the next steps come from another scenario). It may not "
                       "be open: use \"launch\" to open it if the step needs it.\n\n")

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
        if self.notice:
            msg, self.notice = self.notice + msg, ""
        if self.carry_history:
            msg = self.history_text() + msg
            self.carry_history = False
        self.session_calls += 1
        reply, meta = self.ai.ask(msg, obs.jpeg)
        self.session_tokens = meta["in_tokens"]
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
            "in_tokens": meta["in_tokens"], "out_tokens": meta["out_tokens"], "session": self.session_id,
            "platform": self.cur, "note": "",
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
        where = rec["section"] + (f" @ {rec['platform']}" if self.multi else "")
        self.print(self.redact.text(
            f"  #{rec['n']:02d} [{where}] {what} {rec['kind']}: {t}{tgt}{tag}{res}"
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
                self.finalize(t, "pass" if self.rejudge(t, rec) else "fail")
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

    def rejudge(self, t: ThenState, rec: dict) -> bool:
        """Second opinion (another model, fresh conversation, same screenshot) on a `then` about to fail.
        True if it passes; the disagreement stays as a warning, since the screen may be ambiguous."""
        if self.rejudge_factory is None:
            return False
        step = self.steps[t.item.index]
        label = f"再判定（{self.rejudge_model}）"
        before = [x for x in self.items if x.kind == "do" and x.index < t.item.index]
        msg = build_judge_message(t.text, t.item.strict, self.steps[before[-1].index].text if before else None)
        try:
            s = self.rejudge_factory(judge_system_prompt(self.drv.description, self.drv.iw, self.drv.ih))
            try:
                reply, meta = s.ask(msg, (self.out / rec["image"]).read_bytes())
            finally:
                th = threading.Thread(target=s.close, daemon=True)
                th.start()
                self.closing.append(th)
        except AIError as e:
            step.notes.append(f"{label}できなかった: {self.redact.text(str(e))}")
            return False
        r = parse_judge(reply)
        rec.setdefault("rejudge", []).append({
            "then": t.text, "model": self.rejudge_model, "model_id": getattr(s, "model_id", ""),
            "pass": None if r is None else r["pass"],
            "reason": reply[:200] if r is None else r["reason"], "read": None if r is None else r["read"],
            "llm_s": meta["wall_s"], "in_tokens": meta["in_tokens"], "out_tokens": meta["out_tokens"]})
        if r is None:
            step.notes.append(f"{label}の応答を解釈できない")
            return False
        self.print(self.redact.text(f"    ↻ {label}: {'合格' if r['pass'] else '不合格'} — {r['reason']}"
                                    f"（{meta['wall_s']}s）"))
        if not r["pass"]:
            step.reason = f"{step.reason}（{label}でも不合格: {r['reason']}）"
            return False
        first = step.reason
        step.reason = r["reason"]
        if t.item.strict:
            step.read = r["read"]
        self.warn(step, f"判定が分かれた: {self.res.model} は不合格（{first}）、{label}で合格")
        return True

    def finalize(self, t: ThenState, status: str, reason: str | None = None, not_run: int = 0) -> None:
        """not_run: steps that will not be run because of this failure (reported with it)."""
        t.final = status
        step = self.steps[t.item.index]
        step.status = status
        if reason is not None:
            step.reason = reason
        if status == "fail":
            self.res.stop_all = self.cfg.on_failure == "stop_all"
            img = self.res.calls[step.calls[-1] - 1]["image"] if step.calls else None
            self.ev("fail", section=step.section, step=step.index + 1, kind="then", text=step.text,
                    reason=step.reason, read=step.read, image=str(self.out / img) if img else None,
                    **({"not_run": not_run} if not_run else {}))
            self.print(self.redact.text(f"  ✗ then 不合格 [{step.section}] 「{step.text}」: {step.reason}"
                                        + (f"（残り {not_run} ステップは未実行）" if not_run else "")))

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
        """The action for the driver: secret placeholders replaced by the values. An input that holds a secret
        is marked `secret`, so that the driver can keep it off the clipboard (Android)."""
        if act.get("type") == "input" and act.get("text"):
            text = str(act["text"])
            filled = fill_secrets(text, self.values, self.secrets)
            return dict(act, text=filled, **({"secret": True} if filled != text else {}))
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
        checked = not it.optional  # an optional `do` is done only after the AI saw what its last action led to
        limit = self.cfg.max_actions
        while True:
            if actions >= limit:
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
            a = Ask(section=it.section, do=text, do_strict=it.strict, do_optional=it.optional,
                    step_no=do_no, step_total=n_do,
                    thens=[(t.text, t.item.strict) for t in undecided], attempt=actions,
                    recheck=any(t.started for t in undecided), feedback=fb)
            res, rec = self.ask(a, obs, "do" if not undecided or not any(t.started for t in undecided) else "recheck",
                                it.index)
            if undecided and self.judge(undecided, res, rec):
                self.recheck_action(res, rec, step)
                self.log_call(rec)
                act = res["action"] or {}
                if act.get("type") in EXECUTABLE:
                    # Tell the AI whether its action ran: in phase 4 it took an unexecuted tap for one that
                    # "did not work", tapped again, and finally failed the `do`.
                    last = act
                    feedback = (f"{act.get('type')} -> {rec['act_result']}" if rec["act_result"] else
                                f"{act.get('type')} was NOT executed: actions for the `do` wait until the `then`s "
                                "are decided (only purpose verify/interrupt actions run meanwhile)")
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
                if not checked and t not in (None, "none"):
                    # A message such as "already registered" often comes after the last action: the optional
                    # `do` handles it (closes it and fails, so it is skipped), not the next `do` (in 1 of 3 runs
                    # that one failed, taking the closed message for a reason not to go on).
                    checked = True
                    limit = max(limit, actions + 2)  # room to close what it caused, and to look again
                    feedback += "; [optional] check the result on this screen before the `do` counts as done"
                    continue
                break
        if went_back and not BACK_WORDS.search(text):
            self.warn(step, "戻る操作を挟んだ（`do` は戻ることを指示していない。遠回りの可能性）")
        if step_actions > 1:
            step.notes.append(f"操作 {step_actions} 回")
        return True, ""

    # ------------------------------------------------------------------ scenario
    def fail_pending(self, pending: list[ThenState], reason: str, not_run: int = 0) -> None:
        """Fail the `then`s still undecided because of `reason`. The last one reports `not_run`."""
        undecided = [t for t in pending if t.final is None]
        for n, t in enumerate(undecided, 1):
            self.finalize(t, "fail", f"判定できなかった（{reason}）", not_run=not_run if n == len(undecided) else 0)

    def fail_do(self, it: Item, reason: str, rest: list[Item], pending: list[ThenState]) -> None:
        step = self.steps[it.index]
        step.status, step.reason = "fail", reason
        self.fail_pending(pending, reason)  # the `do` failure below reports the steps left unrun
        img = self.res.calls[step.calls[-1] - 1]["image"] if step.calls else None
        self.ev("fail", section=it.section, step=it.index + 1, kind="do", text=step.text, reason=reason,
                image=str(self.out / img) if img else None, not_run=len(rest))
        self.print(self.redact.text(f"  ✗ do 失敗 [{it.section}] 「{step.text}」: {reason}"
                                    + (f"（残り {len(rest)} ステップは未実行）" if rest else "")))
        self.res.stop_all = self.cfg.on_failure == "stop_all"

    def skip_do(self, it: Item, reason: str) -> None:
        """An optional `do` failed: record it as skipped and go on. Its `then`s are judged as usual."""
        step = self.steps[it.index]
        step.status, step.reason = "skip", reason
        img = self.res.calls[step.calls[-1] - 1]["image"] if step.calls else None
        self.ev("skip", section=it.section, step=it.index + 1, kind="do", text=step.text, reason=reason,
                image=str(self.out / img) if img else None)
        self.print(self.redact.text(f"  ⏭ do スキップ（optional）[{it.section}] 「{step.text}」: {reason}"))

    def run(self) -> ScenarioResult:
        self.t0 = time.time()
        self.res.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.ev("scenario_start", target=self.app, **({"others": self.res.others} if self.multi else {}))
        self.print(f"▶ {self.sc.name} @ {self.platform}（{self.app}）"
                   + "".join(f" + {p}（{t}）" for p, t in self.res.others.items()))
        pending: list[ThenState] = []
        try:
            for drv, app in self.apps():  # every device (and app of an included scenario) starts reset
                drv.type_delay = self.type_delay / 1000  # a device may run several scenarios: set it each time
                drv.reset(app, self.cfg)
            sections = self.sc.sections
            stop = False
            for si, sec in enumerate(sections):
                if stop:
                    break
                plat = sec.on or self.platform
                reset = si > 0 and self.cfg.on_failure == "next_section"
                if pending and (reset or plat != self.cur):
                    # the `then`s left are judged where their `do`s ran, before going on (elsewhere)
                    try:
                        self.judge_only(pending)
                    except StopScenario as e:  # the scenario's time ran out: the rest is not run
                        self.fail_pending(pending, str(e), not_run=sum(len(x.items) for x in sections[si:]))
                        pending = []
                        break
                    pending = []
                    if self.res.stop_all:
                        self.print("  ■ on_failure: stop_all — 以降は実行しない")
                        break
                self.use(plat, sec.targets.get(plat))
                if reset:
                    self.drv.wait_out()  # a `wait` of the last `do` is over before the reset
                    self.drv.reset(self.app, self.cfg)
                    self.section_first_do = True
                for k, it in enumerate(sec.items):
                    if it.kind == "then":
                        self.drv.wait_after_action(it.wait)
                        pending.append(ThenState(it, self.steps[it.index].text))
                        continue
                    try:
                        self.before_do(si, pending)
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
                    if not ok and it.optional and not stop_now:  # the scenario's time limit still stops it
                        self.skip_do(it, reason)
                        self.drv.wait_after_action(it.wait)
                        continue
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
                    self.drv.wait_after_action(it.wait)
                    if self.res.stop_all:
                        stop = True
                        break
            if pending and not stop:
                try:
                    self.judge_only(pending)
                except StopScenario as e:
                    self.fail_pending(pending, str(e))
            self.drv.wait_out()  # a `wait` of the last `do` (nothing judged after it) is still waited for
            if self.cfg.stop_app_after:
                for drv, app in self.apps():
                    drv.stop_app(app)
        except Exception as e:  # noqa: BLE001 — an unexpected failure still ends as a recorded error
            if isinstance(e, (AIError, DriverError)):
                msg = str(e)
            else:
                msg = f"想定外のエラー（{type(e).__name__}）: {e}"
                traceback_to_stderr(self.redact)  # the message alone cannot locate it
            self.res.status, self.res.error = "error", self.redact.text(msg)
            self.ev("error", reason=self.res.error)
            self.print(f"  ✗ 実行エラー: {self.res.error}")
        finally:
            for ai in [self.ai, *(p["ai"] for p in self.parked.values())]:
                if ai is not None:
                    try:
                        ai.close()
                    except Exception:  # noqa: BLE001 — the scenario is over; its result must not be lost to this
                        traceback_to_stderr(self.redact)
            for th in self.closing:
                th.join(timeout=15)
            self.res.seconds = round(self.elapsed(), 1)
        if self.res.status != "error":
            c = self.res.counts()
            self.res.status = "fail" if c["fail"] or c["not_run"] else ("pass_warn" if c["warnings"] else "pass")
        self.ev("scenario_end", status=self.res.status, counts=self.res.counts(), seconds=self.res.seconds)
        self.print(f"■ {self.sc.name} @ {self.platform}: {STATUS_LABEL[self.res.status]}（{self.res.seconds} 秒）")
        return self.res
