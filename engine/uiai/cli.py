"""uiai CLI: run / check / setup / watch.

Exit codes (design doc 12):
  0  all scenarios passed (pass with warnings included, unless --fail-on-warning)
  1  a step failed or was not run
  2  could not run to the end (format errors, missing device/browser/claude, missing variables...)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .events import EventLog, describe
from .redact import Redactor

DEFAULT_MODEL = "haiku"
DEFAULT_RESULTS = Path(".uiai") / "results"


def _out(s: str) -> None:
    print(s, flush=True)


def _slug(s: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", s).strip("._") or "scenario"


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #


def cmd_run(a: argparse.Namespace) -> int:
    from .ai import AIError
    from .ai.claude_code import ClaudeCodeSession
    from .drivers import DriverError, make_driver
    from .loop import STATUS_LABEL, ScenarioRunner
    from .notify import Webhook
    from .platform import PlatformError, probe, resolve, target
    from .report import write_scenario, write_summary
    from .scenario import ScenarioError, discover, load, resolve_variables

    files = discover(a.paths)
    if not files:
        _out("シナリオが見つからない")
        return 2
    overrides = {}
    for kv in a.var or []:
        if "=" not in kv:
            _out(f"--var は NAME=VALUE の形式: {kv}")
            return 2
        k, v = kv.split("=", 1)
        overrides[k] = v

    results_dir = Path(a.results_dir)
    run_id = a.run_id or time.strftime("%Y%m%d-%H%M%S")
    run_dir = results_dir / run_id
    if not a.run_id:
        n = 2
        while run_dir.exists():
            run_dir, n = results_dir / f"{run_id}-{n}", n + 1
    run_dir.mkdir(parents=True, exist_ok=True)
    redactor = Redactor()
    events = EventLog(run_dir / "events.jsonl", redactor)
    url = a.webhook or os.environ.get("UIAI_WEBHOOK_URL")
    if url:
        events.listeners.append(Webhook(url))
    _out(f"run id: {run_dir.name}")
    _out(f"結果: {run_dir}")
    events.emit("run_start", run_id=run_dir.name, results=str(run_dir), scenarios=[str(f) for f in files])

    available = None
    drivers: dict = {}
    results: list = []
    skipped: list[tuple[str, str]] = []
    errored = False
    stop_all = False
    interrupted = False
    try:
        for f in files:
            if stop_all:
                skipped.append((str(f), "on_failure: stop_all により未実行"))
                continue
            try:
                sc = load(f)
            except ScenarioError as e:
                reason = "シナリオの形式エラー: " + "; ".join(str(i) for i in e.issues if i.level == "error")
                skipped.append((str(f), reason))
                events.emit("error", scenario=str(f), file=str(f), reason=reason)
                _out(f"✗ {f}: {reason}")
                errored = True
                continue
            values, missing = resolve_variables(sc, overrides)
            if missing:
                reason = f"変数 {missing} の値がない（--var、環境変数、または対話入力が必要）"
                skipped.append((sc.name, reason))
                events.emit("error", scenario=sc.name, file=str(f), reason=reason)
                _out(f"✗ {sc.name}: {reason}")
                errored = True
                continue
            redactor.add([values[n] for n in sc.secret_names if n in values])
            if available is None:
                available = probe(a.serial)
            try:
                platforms = resolve(sc.app, a.platform, available)
            except PlatformError as e:
                skipped.append((sc.name, str(e)))
                events.emit("error", scenario=sc.name, file=str(f), reason=str(e))
                _out(f"✗ {sc.name}: {e}")
                errored = True
                continue
            for p in platforms:
                if stop_all:
                    break
                try:
                    if p not in drivers:
                        drivers[p] = make_driver(p, serial=a.serial, browser_path=a.browser_path, headed=a.headed)
                except DriverError as e:
                    skipped.append((f"{sc.name} @ {p}", str(e)))
                    events.emit("error", scenario=sc.name, platform=p, file=str(f), reason=str(e))
                    _out(f"✗ {sc.name} @ {p}: {e}")
                    errored = True
                    continue
                model = a.model or sc.config.model or DEFAULT_MODEL
                out = run_dir / _slug(f"{f.stem}-{p}")
                n = 2
                while out.exists():
                    out, n = run_dir / _slug(f"{f.stem}-{p}-{n}"), n + 1
                out.mkdir(parents=True)
                runner = ScenarioRunner(sc, p, target(sc.app, p, f.parent), drivers[p],
                                        lambda system, m=model: ClaudeCodeSession(m, system), values, out,
                                        events, redactor, model)
                res = runner.run()
                write_scenario(res, out, redactor)
                results.append((res, out))
                errored = errored or res.status == "error"
                stop_all = stop_all or res.stop_all
    except KeyboardInterrupt:
        interrupted = True
        _out("中断した")
    finally:
        for d in drivers.values():
            try:
                d.close()
            except Exception:  # noqa: BLE001
                pass

    statuses = [r.status for r, _ in results]
    if errored or interrupted or skipped:
        code = 2
    elif any(s == "fail" for s in statuses):
        code = 1
    elif a.fail_on_warning and any(s == "pass_warn" for s in statuses):
        code = 1
    else:
        code = 0
    summary = {k: statuses.count(k) for k in ("pass", "pass_warn", "fail", "error")}
    summary["skipped"] = len(skipped)
    summary_path = write_summary(results, run_dir, code, skipped, redactor)
    events.emit("run_end", exit_code=code, summary=summary, report=f" {summary_path}")
    events.close()
    _out("")
    for res, out in results:
        _out(f"{STATUS_LABEL[res.status]:<8} {res.name} @ {res.platform}  {out / 'report.html'}")
    for name, reason in skipped:
        _out(f"{'未実行':<8} {name}: {reason}")
    _out(f"まとめ: {summary_path}（終了コード {code}）")
    return code


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #


def cmd_check(a: argparse.Namespace) -> int:
    from .scenario import check_file, discover

    files = discover(a.paths)
    if not files:
        _out("シナリオが見つからない")
        return 2
    bad = False
    report = {}
    for f in files:
        issues = check_file(f)
        report[str(f)] = [vars(i) for i in issues]
        errs = [i for i in issues if i.level == "error"]
        if errs or (a.strict and issues):
            bad = True
        if not a.json:
            _out(f"{'NG' if errs else 'OK'} {f}")
            for i in issues:
                _out(f"   {i}")
    if a.json:
        _out(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if bad else 0


# --------------------------------------------------------------------------- #
# setup
# --------------------------------------------------------------------------- #


def cmd_setup(a: argparse.Namespace) -> int:
    ok = True
    claude = shutil.which("claude")
    if claude:
        v = subprocess.run([claude, "--version"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace").stdout.strip()
        _out(f"OK   claude: {v}")
    else:
        _out("NG   claude（Claude Code CLI）が見つからない: https://docs.claude.com/claude-code")
        ok = False
    adb = shutil.which("adb")
    _out(f"OK   adb: {adb}" if adb else "--   adb なし（Android を使う場合は Android SDK Platform-Tools を入れる）")
    if sys.platform == "darwin":
        _out("OK   xcrun（iOS は段階 3 で対応予定）" if shutil.which("xcrun") else "--   xcrun なし（iOS は Xcode が必要）")
    if not a.skip_browser:
        _out("...  Playwright のブラウザ（Chromium）を取得する")
        r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
        if r.returncode == 0:
            _out("OK   Chromium")
        else:
            _out("NG   Chromium を取得できない")
            ok = False
    return 0 if ok else 2


# --------------------------------------------------------------------------- #
# watch
# --------------------------------------------------------------------------- #


def _find_run(results_dir: Path, run: str) -> Path | None:
    if run != "latest":
        return results_dir / run
    if not results_dir.is_dir():
        return None
    runs = sorted((p for p in results_dir.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    return runs[-1] if runs else None


def cmd_watch(a: argparse.Namespace) -> int:
    """Print failures of a run as they happen (one line each); exit when the run ends.

    Meant for Claude Code's Monitor tool: every printed line becomes a notification.
    """
    results_dir = Path(a.results_dir)
    deadline = time.time() + a.wait
    path = None
    while time.time() < deadline:
        run_dir = _find_run(results_dir, a.run)
        if run_dir is not None and (run_dir / "events.jsonl").exists():
            path = run_dir / "events.jsonl"
            break
        time.sleep(0.5)
    if path is None:
        _out(f"[uiai] 実行が見つからない: {results_dir / a.run}")
        return 2
    end = time.time() + a.timeout
    with open(path, encoding="utf-8") as fh:
        buf = ""
        while time.time() < end:
            chunk = fh.readline()
            if not chunk:
                time.sleep(0.3)
                continue
            buf += chunk
            if not buf.endswith("\n"):
                continue
            line, buf = buf, ""
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = ev.get("type")
            if t in ("fail", "error") or (a.all and t in ("warning", "scenario_end")):
                _out(describe(ev))
            elif t == "run_end":
                _out(describe(ev))
                return 0
    _out("[uiai] watch がタイムアウトした（実行はまだ続いている可能性がある）")
    return 2


# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="uiai", description="AI がスクリーンショットを見て操作・判定する UI テスト")
    ap.add_argument("--version", action="version", version=f"uiai {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="シナリオを実行する")
    r.add_argument("paths", nargs="+", help="シナリオのファイルかフォルダ")
    r.add_argument("--platform", choices=["android", "ios", "web", "all"])
    r.add_argument("--model", help=f"使うモデル（既定: config.model、なければ {DEFAULT_MODEL}）")
    r.add_argument("--serial", help="Android 端末のシリアル（adb -s）")
    r.add_argument("--browser-path", help="Chromium の実行ファイル（既定: Playwright のもの）")
    r.add_argument("--headed", action="store_true", help="ブラウザを表示して実行する")
    r.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    r.add_argument("--run-id", help="結果フォルダ名（uiai watch で先に見張るとき用）")
    r.add_argument("--var", action="append", metavar="NAME=VALUE", help="変数の値（繰り返し可）")
    r.add_argument("--webhook", help="失敗を送る Webhook の URL（既定: 環境変数 UIAI_WEBHOOK_URL）")
    r.add_argument("--fail-on-warning", action="store_true", help="警告付き合格も終了コード 1 にする")
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("check", help="シナリオの形式を検査する")
    c.add_argument("paths", nargs="+")
    c.add_argument("--strict", action="store_true", help="警告も失敗として扱う")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    s = sub.add_parser("setup", help="実行環境を確認し、ブラウザを取得する")
    s.add_argument("--skip-browser", action="store_true")
    s.set_defaults(fn=cmd_setup)

    w = sub.add_parser("watch", help="実行中の失敗を 1 行ずつ表示する（Monitor 用）")
    w.add_argument("--run", default="latest", help="run id（既定: latest）")
    w.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    w.add_argument("--all", action="store_true", help="警告とシナリオごとの結果も表示する")
    w.add_argument("--wait", type=float, default=60, help="実行が始まるのを待つ秒数")
    w.add_argument("--timeout", type=float, default=3 * 3600)
    w.set_defaults(fn=cmd_watch)
    return ap


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Japanese Windows defaults to cp932
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    a = build_parser().parse_args(argv)
    return a.fn(a)
