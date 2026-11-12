"""What the AI is told, and how its replies are read.

One call per step: the reply carries the verdicts for the pending `then`s AND the next
action. See docs/design/ai-loop-redesign.md (8.2, 8.3).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

SYSTEM = """You operate {desc} to run a UI test scenario, one step at a time.
Each message gives the current step (`do`), the assertions (`then`) to judge on the CURRENT screen,
and a screenshot of the current screen ({iw}x{ih} px).

Reply with ONLY one JSON object, no prose, no code fences:
{{"verify":[{{"then":"<text>","pass":true|false,"reason":"<short>","absence":true|false,"read":"<strict only>"}}],
 "action":{{"type":"tap|input|key|scroll|back|launch|wait|none|fail","x":<px>,"y":<px>,"text":"<for input>","key":"<for key>","direction":"down|up|left|right","reason":"<short>"}},
 "purpose":"step|interrupt|verify",
 "dialog":"<purpose interrupt: what you dismiss>",
 "allowed":"<purpose interrupt: the matching entry of the allowed-dialog list, or empty>",
 "error_shown":true|false,
 "done":true|false}}

Rules:
- One action per reply. "done": true when this action completes the `do`; false if more actions are needed
  (e.g. scroll first, then tap in the next message).
- x,y = the center of the target in the screenshot's pixel coordinates. For input, x,y = the field to type into
  (omit them to type into the already-focused field). One input action does both the tap and the typing.
- "launch" (re)starts the app under test. Use it only for the first step of a section or when the `do` says to
  start/open/restart the app.
- "back" goes back. "key" presses a key such as Enter. "wait": the screen is still loading/animating, you get a
  fresh screen. "none": nothing to do because the `do` is already satisfied on this screen.
- "fail": the step cannot be done on this screen (target not found even after scrolling, unexpected state).
  Do not take detours through other screens or features; follow the path the `do` describes.
- "purpose": "step" for actions that perform the `do`; "interrupt" when you dismiss an unexpected dialog/popup
  the scenario does not mention (cookie notice, permission prompt, update prompt) - then "done": false;
  "verify" for actions taken only to judge a `then` (see below).
- Error messages: if the screen shows an error (error dialog, "failed", "エラー", "失敗", network error...)
  that neither the `do` nor the `then`s mention, do NOT dismiss it: set "error_shown": true and action "fail"
  with the message in "reason".
- Allowed dialogs (may be dismissed silently): {allow}
{secrets}
Judging `then`:
- "verify" has one entry per given `then`, in the same order (empty list if none). Judge only from the current
  screenshot; pass=false if it is not satisfied (the runner may re-check on a fresh screen).
- "absence": true if the `then` asserts that something is NOT shown (e.g. "エラーが表示されないこと").
- If the previous step has not finished (e.g. a confirmation dialog it opened is still shown), return the action
  that finishes it, with "purpose": "verify" - also when the `then`s pass.
- If what a `then` refers to may be outside the visible area (e.g. further down a list), return a scroll with
  "purpose": "verify".
- [strict] `then`: exact character-by-character match. Distinguish full-width/half-width characters, ー/-/−,
  O/0, l/1/I, the number of spaces and punctuation. Put the exact text you read in "read". If the text is
  truncated (…), masked, cut off or otherwise not fully readable, pass=false and say so. Never guess.
- [strict] `do`: the target's label must match the quoted text exactly.
"""


def system_prompt(desc: str, iw: int, ih: int, allow: list[str], secrets: list[str] | None = None) -> str:
    allow_s = json.dumps(allow, ensure_ascii=False) if allow else "(none)"
    secrets_s = ""
    if secrets:  # only when the scenario has secret variables (an example here gets copied literally)
        names = ", ".join(f"({n})" for n in sorted(secrets))
        secrets_s = (f"- Secret placeholders: {names}. When a `do` asks to type one, put the placeholder itself in\n"
                     f"  \"text\" exactly as written; the runner substitutes the real value.\n")
    return SYSTEM.format(desc=desc, iw=iw, ih=ih, allow=allow_s, secrets=secrets_s)


@dataclass
class Ask:
    section: str
    do: str | None              # None: only judge `then`s
    do_strict: bool = False
    step_no: int = 0
    step_total: int = 0
    thens: list[tuple[str, bool]] | None = None   # (text, strict)
    attempt: int = 0
    recheck: bool = False
    feedback: str = ""          # result of the previous action


def build_message(a: Ask) -> str:
    parts = [f"section: {a.section}" + (f" (step {a.step_no}/{a.step_total})" if a.step_total else "")]
    if a.do is None:
        parts.append("do: (none - only judge the `then`s; action: none)")
    else:
        parts.append(f"do: {a.do}" + (" [strict]" if a.do_strict else ""))
    if a.attempt:
        parts.append(f"(continuing this `do`, action {a.attempt + 1})")
    if a.feedback:
        parts.append(f"previous action: {a.feedback}")
    if a.recheck:
        parts.append("(re-check: a `then` failed on the previous screen; this is a fresh screen)")
    thens = [t + (" [strict]" if s else "") for t, s in (a.thens or [])]
    parts.append("then to judge now: " + json.dumps(thens, ensure_ascii=False))
    parts.append("screen: (see the screenshot)")
    return "\n".join(parts)


def parse_reply(text: str) -> dict | None:
    """The JSON object in the reply, or None if there is none."""
    start = text.find("{")
    if start < 0:
        return None
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text[start:]):
        try:
            obj, _ = dec.raw_decode(text[start + m.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return normalize(obj)
    return None


def normalize(obj: dict) -> dict:
    act = obj.get("action")
    if not isinstance(act, dict):
        act = {"type": str(act)} if isinstance(act, str) else {"type": "none"}
    verify = obj.get("verify")
    if not isinstance(verify, list):
        verify = []
    purpose = obj.get("purpose")
    if purpose not in ("step", "interrupt", "verify"):
        purpose = "interrupt" if obj.get("interrupt") else "step"
    return {
        "verify": [v for v in verify if isinstance(v, dict)],
        "action": act,
        "purpose": purpose,
        "dialog": str(obj.get("dialog") or ""),
        "allowed": str(obj.get("allowed") or ""),
        "error_shown": bool(obj.get("error_shown")),
        "done": bool(obj.get("done")),
    }
