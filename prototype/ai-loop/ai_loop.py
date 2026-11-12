#!/usr/bin/env python3
"""Minimal "program drives, AI decides" loop for measuring AI-in-the-loop speed.

Each `do` step = observe -> ONE Claude Code call -> act.
Pending `then` assertions are verified inside the same call, using the
screen observed before the next action (no separate evaluator pass).
If a `then` fails, the runner waits briefly and re-asks on a fresh screen
(it may still be loading) before accepting the failure.

Drivers (--driver):
  adb    : Android, `adb shell uiautomator dump` (waits for idle; slow)
  u2     : Android, resident uiautomator2 server (fast; `pip install uiautomator2`)
  vision : Android, screenshot only - the AI answers pixel coordinates (needs Pillow)
  web    : Web (Playwright/Chromium), screenshot only (needs Pillow + playwright)

The AI is reached through a single persistent `claude -p` process
(stream-json in/out), so there is no per-step process start-up.

Usage:
  python3 ai_loop.py scenario.yaml --model sonnet --driver vision [--out run.json] [--save-dir shots/]
  python3 ai_loop.py web-scenario.yaml --driver web [--browser-path /path/to/chromium]
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

# --------------------------------------------------------------------------- #
# Drivers
# --------------------------------------------------------------------------- #


class Driver:
    kind = "tree"           # "tree": numbered UI elements / "image": screenshot + pixel coordinates
    platform = "a device"
    ignore_top = 0.0        # top fraction ignored by the stability check (status bar)

    def __init__(self):
        self.last_polls = 1
        self.wait_s = 1.0
        # After an action, first wait (up to change_timeout) for the screen to CHANGE,
        # then (up to stable_timeout) for it to settle. Otherwise a still-unchanged
        # screen right after a tap looks "settled".
        self.acted = False
        self.change_timeout = 2.0
        self.stable_timeout = 3.0

    def reset(self, app: str, scenario: dict) -> None:
        pass

    def close(self) -> None:
        pass

    poll_interval = 0.1     # min interval between frames (fast grabbers would otherwise see slow animations as still)
    stable_frames = 2       # consecutive "same" comparisons required = still for >= ~0.2s

    def _settle(self, grab, same, changed=None):
        """Poll `grab()` until the screen changed (if we just acted) and then settled.

        `changed` (sensitive) ends the change-wait; `same` (tolerant) decides stillness.
        """
        changed = changed or (lambda a, b: not same(a, b))
        want_change = self.acted and getattr(self, "_last_frame", None) is not None
        self.acted = False
        start, prev, polls, still = time.time(), None, 0, 0
        while True:
            t0 = time.time()
            frame = grab()
            polls += 1
            elapsed = time.time() - start
            if want_change:
                if changed(self._last_frame, frame) or elapsed > self.change_timeout:
                    want_change = False
                prev = frame
            else:
                still = still + 1 if prev is not None and same(prev, frame) else 0
                if still >= self.stable_frames or elapsed > self.change_timeout + self.stable_timeout:
                    break
                prev = frame
            time.sleep(max(0.0, self.poll_interval - (time.time() - t0)))
        self.last_polls = polls
        self._last_frame = frame
        return frame

    def _observe_image(self, grab_image) -> bytes:
        """Settle on screenshots and return the settled frame as JPEG."""
        from PIL import ImageChops

        def grab():
            im = grab_image()
            top = int(im.height * self.ignore_top)
            return im, im.crop((0, top, im.width, im.height)).convert("L")

        def diff_px(a, b) -> int:
            return ImageChops.difference(a[1], b[1]).point(lambda p: 255 if p > 24 else 0).histogram()[255]

        def same(a, b) -> bool:  # tolerate a blinking text cursor, not a spinner
            return diff_px(a, b) <= max(50, int(b[1].width * b[1].height * 0.0003))

        def changed(a, b) -> bool:  # typed characters / toggles must count as a change
            return diff_px(a, b) > 20

        im, _ = self._settle(grab, same, changed)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=80)
        return out.getvalue()

    def _mark_acted(self, t: str) -> None:
        if t in ("tap", "input", "key", "back", "scroll", "launch"):
            self.acted = True


ANDROID_KEYS = {"enter": 66, "back": 4, "tab": 61, "delete": 67, "backspace": 67, "home": 3, "search": 84}


class AdbDriver(Driver):
    """Android. Observes via `uiautomator dump`; targets are numbered refs."""

    platform = "an Android device"

    def __init__(self, serial: str | None = None):
        super().__init__()
        self.base = ["adb"] + (["-s", serial] if serial else [])
        size = self._out(["shell", "wm", "size"])
        m = re.search(r"(\d+)x(\d+)", size)
        self.w, self.h = (int(m.group(1)), int(m.group(2))) if m else (1080, 2400)
        self.refs: dict[int, tuple[int, int]] = {}

    def _out(self, args: list[str]) -> str:
        return subprocess.run(self.base + args, capture_output=True, text=True).stdout

    def reset(self, app: str, scenario: dict) -> None:
        self._out(["shell", "input", "keyevent", "3"])  # home
        for pkg in [app, *scenario.get("reset_packages", [])]:  # clean start state
            self._out(["shell", "am", "force-stop", pkg])

    def _dump(self) -> str:
        xml = ""
        for _ in range(3):
            xml = self._out(["exec-out", "uiautomator", "dump", "--compressed", "/dev/tty"])
            if "<hierarchy" in xml:
                break
            time.sleep(0.3)
        return xml

    def observe(self):
        """Dump the UI tree and return a compact, numbered text snapshot."""
        xml = self._dump()
        start = xml.find("<?xml")
        xml = xml[start if start >= 0 else max(xml.find("<hierarchy"), 0):]
        xml = xml[: xml.rfind("</hierarchy>") + len("</hierarchy>")]
        self.refs = {}
        lines: list[str] = []
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return "(failed to read screen)"
        for node in root.iter("node"):
            text = node.get("text", "")
            desc = node.get("content-desc", "")
            rid = node.get("resource-id", "").split(":id/")[-1]
            cls = node.get("class", "").split(".")[-1]
            flags = [f for f in ("clickable", "checkable", "scrollable") if node.get(f) == "true"]
            if node.get("checkable") == "true":
                flags.append(f"checked={node.get('checked')}")
            if node.get("enabled") == "false":
                flags.append("disabled")
            if not (text or desc or (flags and rid)):
                continue
            m = re.findall(r"\d+", node.get("bounds", ""))
            if len(m) != 4:
                continue
            x1, y1, x2, y2 = map(int, m)
            if x2 <= x1 or y2 <= y1:
                continue
            ref = len(self.refs) + 1
            self.refs[ref] = ((x1 + x2) // 2, (y1 + y2) // 2)
            label = " ".join(p for p in (f'"{text}"' if text else "", f'desc="{desc}"' if desc else "") if p)
            idpart = f" id={rid}" if rid else ""
            lines.append(f"[{ref}] {cls} {label}{idpart} {' '.join(flags)}".rstrip())
        return "\n".join(lines) if lines else "(empty screen)"

    def _point(self, action: dict) -> tuple[int, int] | None:
        try:
            return self.refs.get(int(action.get("ref", -1)))
        except (TypeError, ValueError):
            return None

    def act(self, action: dict, app: str) -> str:
        t = action.get("type")
        if t in ("tap", "input"):
            pt = self._point(action)
            if pt is None and t == "tap":
                return f"bad target {action}"
            if pt is not None:  # input without a target types into the focused field
                self._out(["shell", "input", "tap", str(pt[0]), str(pt[1])])
            if t == "input":
                txt = str(action.get("text", "")).replace(" ", "%s")
                self._out(["shell", "input", "text", txt])
        elif t == "key":
            code = ANDROID_KEYS.get(str(action.get("key", "")).lower())
            if code is None:
                return f"unknown key {action.get('key')}"
            self._out(["shell", "input", "keyevent", str(code)])
        elif t == "back":
            self._out(["shell", "input", "keyevent", "4"])
        elif t == "scroll":
            y_from, y_to = (0.7, 0.3) if action.get("direction", "down") == "down" else (0.3, 0.7)
            self._out(["shell", "input", "swipe", str(self.w // 2), str(int(self.h * y_from)),
                       str(self.w // 2), str(int(self.h * y_to)), "300"])
        elif t == "launch":
            self._out(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
        elif t == "wait":
            time.sleep(self.wait_s)
        elif t in ("none", "fail"):
            pass
        else:
            return f"unknown action {t}"
        self._mark_acted(t)
        return "ok"


class U2Driver(AdbDriver):
    """Android. Same as AdbDriver, but observes via the resident uiautomator2 server.

    Note: while the u2 server runs, `adb shell uiautomator dump` gets killed.
    """

    def __init__(self, serial: str | None = None):
        super().__init__(serial)
        import uiautomator2 as u2  # optional dependency
        self.d = u2.connect(serial)

    def _dump(self) -> str:
        return self._settle(lambda: self.d.dump_hierarchy(compressed=True), lambda a, b: a == b)


class ScreenshotDriver(AdbDriver):
    """Android, screenshot only. The AI answers pixel coordinates; no UI tree."""

    kind = "image"
    ignore_top = 0.03  # status bar (clock etc.)

    def __init__(self, serial: str | None = None, width: int = 540):
        super().__init__(serial)
        self.iw, self.ih = width, round(self.h * width / self.w)
        self.scale = self.w / width

    def _grab(self):
        from PIL import Image  # optional dependency

        b = subprocess.run(self.base + ["exec-out", "screencap"], capture_output=True).stdout
        w, h = int.from_bytes(b[0:4], "little"), int.from_bytes(b[4:8], "little")
        hdr = 16 if len(b) >= 16 + w * h * 4 else 12  # Android 9+ has a 16-byte header
        im = Image.frombuffer("RGBA", (w, h), b[hdr:hdr + w * h * 4], "raw", "RGBA", 0, 1)
        return im.convert("RGB").resize((self.iw, self.ih))

    def observe(self):
        return self._observe_image(self._grab)

    def _point(self, action: dict) -> tuple[int, int] | None:
        try:
            return int(float(action["x"]) * self.scale), int(float(action["y"]) * self.scale)
        except (KeyError, TypeError, ValueError):
            return None


class WebDriver(Driver):
    """Web (Playwright + Chromium), screenshot only. Same AI contract as ScreenshotDriver."""

    kind = "image"
    platform = "a web browser"

    def __init__(self, width: int = 1280, height: int = 800, executable: str | None = None):
        super().__init__()
        from playwright.sync_api import sync_playwright  # optional dependency

        self._pw = sync_playwright().start()
        opts: dict = {"headless": True}
        if executable:
            opts["executable_path"] = executable
        self.browser = self._pw.chromium.launch(**opts)
        self.page = self.browser.new_page(viewport={"width": width, "height": height}, locale="ja-JP")
        self.iw, self.ih = width, height

    def reset(self, app: str, scenario: dict) -> None:
        self.page.goto("about:blank")

    def close(self) -> None:
        self.browser.close()
        self._pw.stop()

    def _grab(self):
        from PIL import Image

        for i in range(50):  # capture fails while navigating to another site (renderer swap)
            try:
                return Image.open(io.BytesIO(self.page.screenshot(type="jpeg", quality=80))).convert("RGB")
            except Exception:  # noqa: BLE001
                if i == 49:
                    raise
                time.sleep(0.1)

    def observe(self):
        return self._observe_image(self._grab)

    def act(self, action: dict, app: str) -> str:
        t = action.get("type")
        p = self.page
        try:
            if t in ("tap", "input"):
                has_xy = "x" in action and "y" in action
                if not has_xy and t == "tap":
                    return f"bad target {action}"
                if has_xy:  # input without a target types into the focused field
                    p.mouse.click(float(action["x"]), float(action["y"]))
                if t == "input":
                    p.keyboard.type(str(action.get("text", "")))
            elif t == "key":
                p.keyboard.press(str(action.get("key", "Enter")))
            elif t == "back":
                p.go_back(wait_until="domcontentloaded", timeout=15000)
            elif t == "scroll":
                p.mouse.move(self.iw / 2, self.ih / 2)
                p.mouse.wheel(0, self.ih * 0.6 * (1 if action.get("direction", "down") == "down" else -1))
            elif t == "launch":
                p.goto(app, wait_until="domcontentloaded", timeout=30000)
            elif t == "wait":
                time.sleep(self.wait_s)
            elif t in ("none", "fail"):
                pass
            else:
                return f"unknown action {t}"
        except Exception as e:  # noqa: BLE001 - report to the log, let the AI see the result
            return f"error: {str(e)[:200]}"
        self._mark_acted(t)
        return "ok"


def make_driver(name: str, serial: str | None, browser_path: str | None) -> Driver:
    if name == "web":
        return WebDriver(executable=browser_path)
    return {"adb": AdbDriver, "u2": U2Driver, "vision": ScreenshotDriver}[name](serial)


# --------------------------------------------------------------------------- #
# AI via Claude Code (persistent headless session)
# --------------------------------------------------------------------------- #

RULES = """Rules:
- One action per reply. Set "done": true when this action completes the `do` step; false if more actions are needed
  (e.g. scroll first, then tap in the next message).
- If an unexpected dialog/popup blocks the step, handle it with "interrupt": true and "done": false.
- "launch" opens/starts the app under test. "back" goes back. "key" presses a key such as Enter.
- "none" means nothing to do (step already satisfied).
- "wait" means the screen is still loading/animating; you will get a fresh screen.
- Use "fail" only if the step is impossible on this screen after reasonable attempts.
- "verify" must contain one entry per given `then` (empty list if none). If a `then` is not satisfied,
  set pass=false; the runner may re-check it on a fresh screen before accepting the failure.
- If a `then` fails because the previous step is not finished yet (e.g. a confirmation dialog appeared),
  return the action that finishes it with "interrupt": true; it is executed before the re-check.
"""


def system_prompt(drv: Driver) -> str:
    if drv.kind == "image":
        screen = f"and a screenshot of the current screen ({drv.iw}x{drv.ih} px)"
        target = '"x":<px>,"y":<px>'
        extra = ("- For tap/input, x,y = the center of the target, in the screenshot's pixel coordinates.\n"
                 "- For input, omit x,y to type into the already-focused field.\n")
    else:
        screen = "and the current screen as numbered elements"
        target = '"ref":<n>'
        extra = ("- Judge only from the screen elements.\n"
                 "- For input, omit ref to type into the already-focused field.\n")
    return f"""You operate {drv.platform} to execute a UI test scenario, one step at a time.
Each message gives: the current step (`do`), assertions (`then`) to verify on the CURRENT screen,
{screen}.

Reply with ONLY one JSON object, no prose, no code fences:
{{"verify":[{{"then":"<text>","pass":true|false,"reason":"<short>"}}],
 "action":{{"type":"tap|input|key|scroll|back|launch|wait|none|fail",{target},"text":"<for input>","key":"<for key, e.g. Enter>","direction":"down|up","reason":"<for fail>"}},
 "done":true|false,
 "interrupt":true|false}}

{RULES}{extra}"""


class ClaudeCodeSession:
    def __init__(self, model: str, cwd: str, system: str):
        cmd = [
            "claude", "-p",
            "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--model", model,
            "--tools", "",
            "--system-prompt", system,
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--setting-sources", "project",
        ]
        self.p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._api_ms_total = 0  # duration_api_ms in result events is cumulative per session

    def ask(self, text: str, image: bytes | None = None) -> tuple[str, dict]:
        content: list[dict] = []
        if image is not None:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                         "data": base64.b64encode(image).decode()}})
        content.append({"type": "text", "text": text})
        msg = {"type": "user", "message": {"role": "user", "content": content}}
        start = time.time()
        assert self.p.stdin and self.p.stdout
        self.p.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        reply = ""
        for line in self.p.stdout:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "assistant":
                for c in ev.get("message", {}).get("content", []):
                    if c.get("type") == "text":
                        reply += c["text"]
            elif ev.get("type") == "result":
                usage = ev.get("usage", {})
                api_total = ev.get("duration_api_ms", 0)
                api_delta, self._api_ms_total = api_total - self._api_ms_total, api_total
                return (reply or ev.get("result", "")), {
                    "wall_s": round(time.time() - start, 2),
                    "api_s": round(api_delta / 1000, 2),
                    "in_tokens": usage.get("input_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0),
                    "out_tokens": usage.get("output_tokens", 0),
                }
        raise RuntimeError("claude session ended unexpectedly")

    def close(self) -> None:
        if self.p.stdin:
            self.p.stdin.close()
        self.p.wait(timeout=10)


def parse_reply(reply: str) -> dict:
    m = re.search(r"\{.*\}", reply, re.S)
    if not m:
        return {"verify": [], "action": {"type": "fail", "reason": f"unparsable: {reply[:120]}"}, "done": True}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"verify": [], "action": {"type": "fail", "reason": f"bad json: {reply[:120]}"}, "done": True}


# --------------------------------------------------------------------------- #
# Loop
# --------------------------------------------------------------------------- #


def flatten(scenario: dict) -> list[tuple[str, str, str]]:
    items = []
    for sec in scenario.get("steps", []):
        for a in sec.get("actions", []):
            for kind in ("do", "then"):
                if kind in a:
                    items.append((sec.get("id", ""), kind, a[kind]))
    return items


def build_prompt(do: str | None, thens: list[str], screen: str | None, attempt: int, recheck: bool) -> str:
    parts = [f"do: {do}" if do else "do: (none - only verify)"]
    if attempt:
        parts.append(f"(continuing this step, attempt {attempt + 1})")
    if recheck:
        parts.append("(re-check: a `then` failed before; this is a fresh screen after waiting)")
    parts.append("then to verify now: " + (json.dumps(thens, ensure_ascii=False) if thens else "[]"))
    parts.append("screen:\n" + screen if screen is not None else "screen: (see the screenshot)")
    return "\n".join(parts)


def run(scenario_path: str, model: str, serial: str | None, max_attempts: int, settle: float,
        driver: str = "adb", verify_retries: int = 2, recheck_wait: float = 1.0,
        save_dir: str | None = None, browser_path: str | None = None) -> dict:
    scenario = yaml.safe_load(Path(scenario_path).read_text())
    app = scenario["app"]
    drv = make_driver(driver, serial, browser_path)
    if isinstance(drv, WebDriver) and not re.match(r"^[a-z]+:", app):
        app = (Path(scenario_path).parent / app).resolve().as_uri()  # local file relative to the scenario
    drv.wait_s = recheck_wait
    drv.reset(app, scenario)
    if save_dir:
        Path(save_dir).mkdir(parents=True, exist_ok=True)

    workdir = tempfile.mkdtemp(prefix="uiai-ai-loop-")
    llm = ClaudeCodeSession(model, workdir, system_prompt(drv))
    calls: list[dict] = []
    verdicts: list[dict] = []
    pending: list[tuple[str, str]] = []  # (section, then)

    def one_call(do: str | None, attempt: int, section: str, allow_recheck: bool, is_recheck: bool) -> dict:
        nonlocal pending
        s = time.time()
        screen = drv.observe()
        t_obs = time.time() - s
        image = screen if drv.kind == "image" else None
        text_screen = None if image is not None else screen
        reply, meta = llm.ask(build_prompt(do, [t for _, t in pending], text_screen, attempt, is_recheck), image)
        res = parse_reply(reply)
        verifies = res.get("verify") or []
        recheck = bool(allow_recheck and pending and any(not v.get("pass") for v in verifies))
        if save_dir and image is not None:
            (Path(save_dir) / f"call_{len(calls) + 1:02d}.jpg").write_bytes(image)
        act = res.get("action", {}) or {}
        recheck_fix = recheck and res.get("interrupt") and act.get("type") not in (None, "wait", "none", "fail")
        if recheck_fix:  # e.g. confirm a dialog that keeps the previous step from finishing
            s = time.time()
            act_result = "re-check fix: " + drv.act(act, app)
            t_act = time.time() - s
        elif recheck:
            act_result, t_act = "not executed (re-check)", 0.0
        else:
            for i, v in enumerate(verifies):
                verdicts.append({"section": pending[i][0] if i < len(pending) else section, **v})
            pending = []
            s = time.time()
            act_result = drv.act(act, app) if do else "skip"
            time.sleep(settle)
            t_act = time.time() - s
        rec = {
            "n": len(calls) + 1, "section": section, "do": do, "attempt": attempt + 1,
            "recheck": recheck, "is_recheck_call": is_recheck,
            "verify": verifies, "action": act, "act_result": act_result, "done": res.get("done"),
            "interrupt": res.get("interrupt", False),
            "obs_s": round(t_obs, 2), "obs_polls": drv.last_polls,
            "llm_wall_s": meta["wall_s"], "llm_api_s": meta["api_s"],
            "act_settle_s": round(t_act, 2),
            "in_tokens": meta["in_tokens"], "out_tokens": meta["out_tokens"],
        }
        calls.append(rec)
        tgt = (f" ref={act.get('ref')}" if "ref" in act else "") + \
              (f" xy=({act.get('x')},{act.get('y')})" if "x" in act else "") + \
              (f" text={act.get('text')!r}" if act.get("type") == "input" else "") + \
              (f" key={act.get('key')}" if act.get("type") == "key" else "")
        print(f"  #{rec['n']:02d} [{section}] {do or '(verify)'} a{attempt + 1}"
              f"{' RECHECK' if recheck else ''}{' INTERRUPT' if rec['interrupt'] else ''}: {act.get('type')}{tgt}"
              f"{'' if act_result in ('ok', 'skip', 'not executed (re-check)') else ' -> ' + act_result}"
              f"{'' if do is None or res.get('done') or recheck else ' (not done)'}"
              f" | obs {rec['obs_s']}s(x{drv.last_polls}) llm {rec['llm_wall_s']}s act {rec['act_settle_s']}s",
              flush=True)
        res["_recheck"] = recheck
        res["_recheck_fix"] = bool(recheck_fix)
        return res

    def drive(do: str | None, section: str) -> None:
        attempt = rechecks = 0
        while attempt < max_attempts:
            res = one_call(do, attempt, section, allow_recheck=rechecks < verify_retries,
                           is_recheck=rechecks > 0)
            if res["_recheck"]:
                rechecks += 1
                if not res["_recheck_fix"]:  # after a fix action, observe() already waits for the change
                    time.sleep(recheck_wait)
                continue
            attempt += 1
            if do is None or res.get("done") or (res.get("action") or {}).get("type") == "fail":
                return

    t_start = time.time()
    try:
        for section, kind, text in flatten(scenario):
            if kind == "then":
                pending.append((section, text))
            else:
                drive(text, section)
        if pending:
            drive(None, "final")
    finally:
        llm.close()
        drv.close()
    total = time.time() - t_start

    do_steps = sum(1 for _, k, _ in flatten(scenario) if k == "do")

    def avg(key):
        return round(sum(c[key] for c in calls) / len(calls), 2) if calls else 0

    summary = {
        "model": model, "driver": driver, "settle_s": settle, "do_steps": do_steps, "ai_calls": len(calls),
        "recheck_calls": sum(1 for c in calls if c["recheck"]),
        "wait_actions": sum(1 for c in calls if (c["action"] or {}).get("type") == "wait"),
        "interrupts": sum(1 for c in calls if c["interrupt"]),
        "total_s": round(total, 1), "per_do_step_s": round(total / max(do_steps, 1), 2),
        "avg_obs_s": avg("obs_s"), "avg_llm_wall_s": avg("llm_wall_s"), "avg_llm_api_s": avg("llm_api_s"),
        "avg_act_settle_s": avg("act_settle_s"),
        "sum_obs_s": round(sum(c["obs_s"] for c in calls), 1),
        "sum_llm_wall_s": round(sum(c["llm_wall_s"] for c in calls), 1),
        "sum_act_settle_s": round(sum(c["act_settle_s"] for c in calls), 1),
        "sum_recheck_wait_s": round(sum(1 for c in calls if c["recheck"]) * recheck_wait, 1),
        "last_in_tokens": calls[-1]["in_tokens"] if calls else 0,
        "verdicts_pass": sum(1 for v in verdicts if v.get("pass")),
        "verdicts_total": len(verdicts),
    }
    return {"summary": summary, "calls": calls, "verdicts": verdicts}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--serial")
    ap.add_argument("--driver", choices=["adb", "u2", "vision", "web"], default="adb")
    ap.add_argument("--browser-path", help="Chromium executable for --driver web (default: Playwright's)")
    ap.add_argument("--max-attempts", type=int, default=5)
    ap.add_argument("--settle", type=float, default=0.0, help="fixed wait after each action (s)")
    ap.add_argument("--verify-retries", type=int, default=2, help="re-checks of a failed `then` before accepting it")
    ap.add_argument("--recheck-wait", type=float, default=1.0, help="wait before a re-check / for a 'wait' action (s)")
    ap.add_argument("--save-dir", help="save the screenshots sent to the AI (image drivers)")
    ap.add_argument("--out")
    a = ap.parse_args()
    result = run(a.scenario, a.model, a.serial, a.max_attempts, a.settle, a.driver,
                 a.verify_retries, a.recheck_wait, a.save_dir, a.browser_path)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    for v in result["verdicts"]:
        print(f"  then {'PASS' if v.get('pass') else 'FAIL'}: {v.get('then')} — {v.get('reason')}")
    if a.out:
        Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
