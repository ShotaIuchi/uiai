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
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .events import EventLog, describe
from .redact import Redactor

DEFAULT_MODEL = "haiku"
DEFAULT_REJUDGE_MODEL = "sonnet"
BACKENDS = ("claude-code", "api")
DEFAULT_RESULTS = Path(".uiai") / "results"


def _out(s: str) -> None:
    print(s, flush=True)


def _slug(s: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", s).strip("._") or "scenario"


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #


@dataclass
class Job:
    no: int
    file: Path
    sc: Any
    values: dict
    platform: str
    out: Path
    model: str


class Device:
    """One device (or browser) that runs jobs of its platform, one at a time."""

    def __init__(self, platform: str, label: str, kw: dict):
        self.platform, self.label, self.kw = platform, label, kw
        self.driver = None
        self.error = ""


def _devices(a: argparse.Namespace, jobs_per_platform: dict[str, int]) -> dict[str, list[Device]]:
    """Without --parallel: one per platform (as given, or auto-selected by the driver).
    With --parallel: every given (or connected/booted) device, and --browsers browsers, but no more
    devices than the platform has jobs (an idle browser or device would only be started for nothing)."""
    from .platform import android_serials, booted_udids

    out: dict[str, list[Device]] = {}
    for p in sorted(jobs_per_platform):
        if p == "android":
            ids = a.serial or (android_serials() if a.parallel else [None])
            out[p] = [Device(p, s or "android", {"serial": s}) for s in ids]
        elif p == "ios":
            ids = a.udid or (booted_udids() if a.parallel else [None])
            out[p] = [Device(p, (u or "ios")[:8], {"udid": u}) for u in ids]
        else:
            n = max(1, a.browsers) if a.parallel else 1
            out[p] = [Device(p, f"web{i + 1}" if n > 1 else "web",
                             {"browser_path": a.browser_path, "headed": a.headed}) for i in range(n)]
        out[p] = out[p][:max(1, jobs_per_platform[p])]
    return out


def cmd_run(a: argparse.Namespace) -> int:
    from .ai.api import ApiSession
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
    if not a.parallel and (len(a.serial or []) > 1 or len(a.udid or []) > 1):
        _out("複数の端末・シミュレータを使うには --parallel を付ける")
        return 2
    backend = a.backend or os.environ.get("UIAI_BACKEND") or "claude-code"
    if backend not in BACKENDS:
        _out(f"--backend（UIAI_BACKEND）は {' か '.join(BACKENDS)}: {backend}")
        return 2
    if backend == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        _out("--backend api には環境変数 ANTHROPIC_API_KEY が要る")
        return 2
    if a.dry_run:
        return _dry_run(files, overrides, a)

    results_dir = Path(a.results_dir)
    run_id = a.run_id or time.strftime("%Y%m%d-%H%M%S")
    run_dir = results_dir / run_id
    if a.run_id and run_dir.exists():
        _out(f"run id 「{a.run_id}」の結果フォルダは既にある: {run_dir}（別の --run-id を指定する）")
        return 2
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
    if a.notify or os.environ.get("UIAI_NOTIFY") == "1":
        from .desktop import DesktopNotifier

        events.listeners.append(DesktopNotifier())
    _out(f"run id: {run_dir.name}")
    _out(f"結果: {run_dir}")
    if backend == "api":
        _out("AI: Anthropic API を直接呼ぶ（--backend api）")
    events.emit("run_start", run_id=run_dir.name, results=str(run_dir), scenarios=[str(f) for f in files])

    # 1. Jobs: every scenario is loaded and its variables are resolved (and asked for) before anything runs.
    available = None
    jobs: list[Job] = []
    skipped: list[tuple[str, str]] = []
    errored = False
    for f in files:
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
            available = probe(a.serial, a.udid)
        try:
            platforms = resolve(sc.app, a.platform, available)
        except PlatformError as e:
            skipped.append((sc.name, str(e)))
            events.emit("error", scenario=sc.name, file=str(f), reason=str(e))
            _out(f"✗ {sc.name}: {e}")
            errored = True
            continue
        for p in platforms:
            out = run_dir / _slug(f"{f.stem}-{p}")
            n = 2
            while out.exists():
                out, n = run_dir / _slug(f"{f.stem}-{p}-{n}"), n + 1
            out.mkdir(parents=True)
            jobs.append(Job(len(jobs), f, sc, values, p, out, a.model or sc.config.model or DEFAULT_MODEL))

    # 2. Run them: in order (default) or, with --parallel, on every device at once.
    devices = _devices(a, {p: sum(1 for j in jobs if j.platform == p) for p in {j.platform for j in jobs}})
    results: list[tuple[int, Any, Path]] = []
    lock = threading.Lock()
    stop_all = threading.Event()
    printer_lock = threading.Lock()

    def session(model: str, system: str):
        if backend == "api":
            return ApiSession(model, system)
        return ClaudeCodeSession(model, system)

    def run_job(job: Job, dev: Device) -> None:
        rj = a.rejudge_model
        rejudge = None if rj in ("", "none") or rj == job.model else (
            lambda system, m=rj: session(m, system))

        def printer(s: str) -> None:
            with printer_lock:
                print(f"[{dev.label}] {s}" if a.parallel else s, flush=True)

        runner = ScenarioRunner(job.sc, job.platform, target(job.sc.app, job.platform, job.file.parent), dev.driver,
                                lambda system, m=job.model: session(m, system), job.values, job.out,
                                events, redactor, job.model, printer, rejudge_factory=rejudge, rejudge_model=rj,
                                backend=backend)
        res = runner.run()
        write_scenario(res, job.out, redactor)
        with lock:
            results.append((job.no, res, job.out))
        if res.stop_all:
            stop_all.set()

    def open_driver(dev: Device) -> bool:
        if dev.driver is None and not dev.error:
            try:
                dev.driver = make_driver(dev.platform, **dev.kw)
            except DriverError as e:
                dev.error = str(e)
        return dev.driver is not None

    def close_driver(dev: Device) -> None:
        if dev.driver is not None:
            try:
                dev.driver.close()
            except Exception:  # noqa: BLE001
                pass
            dev.driver = None

    def skip(job: Job, reason: str) -> None:
        with lock:
            skipped.append((f"{job.sc.name} @ {job.platform}", reason))
        events.emit("error", scenario=job.sc.name, platform=job.platform, file=str(job.file), reason=reason)
        _out(f"✗ {job.sc.name} @ {job.platform}: {reason}")

    interrupted = False
    started: set[int] = set()
    try:
        if not a.parallel:
            for job in jobs:
                if stop_all.is_set():
                    break
                dev = devices[job.platform][0]
                started.add(job.no)
                if not open_driver(dev):
                    skip(job, dev.error)
                    errored = True
                    continue
                run_job(job, dev)
        else:
            queues = {p: queue.Queue() for p in devices}
            for job in jobs:
                queues[job.platform].put(job)

            def work(dev: Device) -> None:
                # The driver is opened before taking a job: a device that cannot start never holds one, and
                # the jobs are left to the other devices of the platform.
                if not open_driver(dev):
                    with printer_lock:
                        print(f"[{dev.label}] ✗ 使えない: {dev.error}", flush=True)
                    return
                try:
                    while not stop_all.is_set():
                        try:
                            job = queues[dev.platform].get_nowait()
                        except queue.Empty:
                            return
                        with lock:
                            started.add(job.no)
                        run_job(job, dev)
                finally:
                    close_driver(dev)  # Playwright objects must be closed in the thread that made them

            threads = [threading.Thread(target=work, args=(d,), daemon=True, name=d.label)
                       for ds in devices.values() for d in ds]
            if threads:
                _out("並列実行: " + "、".join(f"{p} {len(ds)} 台（{', '.join(d.label for d in ds)}）"
                                           for p, ds in devices.items()))
            for th in threads:
                th.start()
            while any(th.is_alive() for th in threads):
                for th in threads:
                    th.join(timeout=0.5)
            for job in jobs:
                if job.no not in started and not stop_all.is_set():
                    errs = "; ".join(f"{d.label}: {d.error}" for d in devices[job.platform] if d.error)
                    skip(job, f"実行できる端末がない（{errs or '端末なし'}）")
                    errored = True
    except KeyboardInterrupt:
        interrupted = True
        stop_all.set()
        _out("中断した")
    finally:
        if not a.parallel:
            for ds in devices.values():
                for d in ds:
                    close_driver(d)
    for job in jobs:
        if job.no not in started and stop_all.is_set() and not interrupted:
            skipped.append((f"{job.sc.name} @ {job.platform}", "on_failure: stop_all により未実行"))

    results.sort(key=lambda r: r[0])
    statuses = [r.status for _, r, _ in results]
    errored = errored or any(s == "error" for s in statuses)
    if errored or interrupted or skipped:
        code = 2
    elif any(s == "fail" for s in statuses):
        code = 1
    elif a.fail_on_warning and any(s == "pass_warn" for s in statuses):
        code = 1
    else:
        code = 0
    pairs = [(r, out) for _, r, out in results]
    summary = {k: statuses.count(k) for k in ("pass", "pass_warn", "fail", "error")}
    summary["skipped"] = len(skipped)
    summary_path = write_summary(pairs, run_dir, code, skipped, redactor)
    events.emit("run_end", exit_code=code, summary=summary, report=f" {summary_path}")
    events.close()
    _out("")
    for res, out in pairs:
        _out(f"{STATUS_LABEL[res.status]:<8} {res.name} @ {res.platform}  {out / 'report.html'}")
    for name, reason in skipped:
        _out(f"{'未実行':<8} {name}: {reason}")
    _out(f"まとめ: {summary_path}（終了コード {code}）")
    return code


def _dry_run(files: list[Path], overrides: dict[str, str], a: argparse.Namespace) -> int:
    """Report what `run` would do (platforms, missing variables) without touching devices or the AI."""
    from .platform import PlatformError, probe, resolve
    from .scenario import ScenarioError, load, resolve_variables

    available = None
    ok = True
    for f in files:
        try:
            sc = load(f)
        except ScenarioError as e:
            _out(f"✗ {f}: シナリオの形式エラー: " + "; ".join(str(i) for i in e.issues if i.level == "error"))
            ok = False
            continue
        _, missing = resolve_variables(sc, overrides, interactive=False)
        if available is None:
            available = probe(a.serial, a.udid)
        try:
            platforms = resolve(sc.app, a.platform, available)
        except PlatformError as e:
            _out(f"✗ {f}（{sc.name}）: {e}")
            ok = False
            continue
        if missing:
            parts = []
            for n in missing:
                var = sc.variables[n]
                notes = (["秘密"] if var.secret else []) + ([f"環境変数 {var.env}"] if var.env else [])
                parts.append(n + (f"（{'・'.join(notes)}）" if notes else ""))
            _out(f"✗ {f}（{sc.name}）: 値のない変数: {', '.join(parts)}")
            ok = False
            continue
        _out(f"OK {f}（{sc.name}）: {', '.join(platforms)} で実行できる")
    return 0 if ok else 2


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
    _out("OK   ANTHROPIC_API_KEY あり（--backend api で使える）" if os.environ.get("ANTHROPIC_API_KEY")
         else "--   ANTHROPIC_API_KEY なし（--backend api を使う場合だけ要る）")
    adb = shutil.which("adb")
    _out(f"OK   adb: {adb}" if adb else "--   adb なし（Android を使う場合は Android SDK Platform-Tools を入れる）")
    if sys.platform == "darwin":
        _out("OK   xcrun" if shutil.which("xcrun") else "--   xcrun なし（iOS を使う場合は Xcode を入れる）")
        _out(f"OK   axe: {shutil.which('axe')}" if shutil.which("axe")
             else "--   axe なし（iOS を使う場合は brew install cameroncooke/axe/axe）")
    if not a.skip_browser:
        _out("...  Playwright のブラウザ（Chromium）を取得する")
        cmd = [sys.executable, "-m", "playwright", "install"] + (["--with-deps"] if a.with_deps else []) + ["chromium"]
        r = subprocess.run(cmd)
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
    seen = 0
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
            seen += 1
            if seen <= a.skip:
                continue
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
    _out(f"[uiai] watch の時間切れ（実行はまだ続いている可能性がある）。続きを見る: "
         f"uiai watch --run {path.parent.name} --skip {seen}")
    return 3


# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="uiai", description="AI がスクリーンショットを見て操作・判定する UI テスト")
    ap.add_argument("--version", action="version", version=f"uiai {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="シナリオを実行する")
    r.add_argument("paths", nargs="+", help="シナリオのファイルかフォルダ")
    r.add_argument("--platform", choices=["android", "ios", "web", "all"])
    r.add_argument("--model", help=f"使うモデル（既定: config.model、なければ {DEFAULT_MODEL}）")
    r.add_argument("--rejudge-model", default=DEFAULT_REJUDGE_MODEL,
                   help=f"then の不合格を確定する前に判定し直すモデル（既定: {DEFAULT_REJUDGE_MODEL}。none で無効）")
    r.add_argument("--backend", choices=BACKENDS,
                   help="AI の呼び出し方。claude-code（既定）: Claude Code（claude -p）経由。"
                        "api: Anthropic API を直接呼ぶ（環境変数 ANTHROPIC_API_KEY が要る。従量課金。未検証）。"
                        "環境変数 UIAI_BACKEND でも指定できる")
    r.add_argument("--serial", action="append",
                   help="Android 端末のシリアル（adb -s）。--parallel では繰り返して複数指定できる")
    r.add_argument("--udid", action="append",
                   help="iOS シミュレータの UDID（起動中が複数あるとき）。--parallel では繰り返して複数指定できる")
    r.add_argument("--parallel", action="store_true",
                   help="端末ごとに並列で実行する（Android は接続中の全端末、iOS は起動中の全シミュレータ、"
                        "Web は --browsers 個のブラウザ。--serial・--udid で絞れる）")
    r.add_argument("--browsers", type=int, default=2, help="--parallel のときの Web のブラウザ数（既定 2）")
    r.add_argument("--browser-path", help="Chromium の実行ファイル（既定: Playwright のもの）")
    r.add_argument("--headed", action="store_true", help="ブラウザを表示して実行する")
    r.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    r.add_argument("--run-id", help="結果フォルダ名（uiai watch で先に見張るとき用）")
    r.add_argument("--var", action="append", metavar="NAME=VALUE", help="変数の値（繰り返し可）")
    r.add_argument("--webhook", help="失敗を送る Webhook の URL（既定: 環境変数 UIAI_WEBHOOK_URL）")
    r.add_argument("--notify", action="store_true",
                   help="失敗と終了を OS のデスクトップ通知でも知らせる（環境変数 UIAI_NOTIFY=1 でも可）")
    r.add_argument("--fail-on-warning", action="store_true", help="警告付き合格も終了コード 1 にする")
    r.add_argument("--dry-run", action="store_true",
                   help="実行せずに、対象のプラットフォームと値のない変数だけを表示する")
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("check", help="シナリオの形式を検査する")
    c.add_argument("paths", nargs="+")
    c.add_argument("--strict", action="store_true", help="警告も失敗として扱う")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    s = sub.add_parser("setup", help="実行環境を確認し、ブラウザを取得する")
    s.add_argument("--skip-browser", action="store_true")
    s.add_argument("--with-deps", action="store_true",
                   help="ブラウザに必要な OS のライブラリも入れる（Linux の CI 用。sudo が要る）")
    s.set_defaults(fn=cmd_setup)

    w = sub.add_parser("watch", help="実行中の失敗を 1 行ずつ表示する（Monitor 用）")
    w.add_argument("--run", default="latest", help="run id（既定: latest）")
    w.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    w.add_argument("--all", action="store_true", help="警告とシナリオごとの結果も表示する")
    w.add_argument("--wait", type=float, default=60, help="実行が始まるのを待つ秒数")
    w.add_argument("--timeout", type=float, default=3 * 3600, help="この秒数で見張りをやめる（実行は止めない）")
    w.add_argument("--skip", type=int, default=0, help="先頭のイベントをこの数だけ読み飛ばす（見張りの再開用）")
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
