"""WebDriverAgent (WDA) for real iPhones: get it, sign and build it, start it, talk to it.

WDA (https://github.com/appium/WebDriverAgent) is an XCTest UI-test bundle that serves an HTTP API on the
iPhone (port 8100): screenshots, touches, typing, buttons, app launch. uiai uses it the way Appium does,
without Appium or Node.js:

- The source is cloned once at a pinned commit into ~/Library/Caches/uiai/wda.
- It is built with `xcodebuild build-for-testing` and Xcode's automatic signing for the user's team. The
  runner gets a bundle ID of its own per team (com.facebook.* is taken), and -allowProvisioningUpdates
  lets Xcode register the device and renew profiles. A free (personal) team's profile expires after
  7 days; since the build step runs every time WDA is started, Xcode renews it then.
- `xcodebuild test-without-building` starts it on the device and runs as long as WDA does.
- The Mac reaches the port over USB through usbmuxd (usbmux.py).
"""

from __future__ import annotations

import base64
import fcntl
import http.client
import json
import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from .base import DriverError

WDA_VERSION = "16.15.3"
WDA_COMMIT = "02cb92f0e93c8b021443bcbb8eeb80932c113220"
WDA_REPO = "https://github.com/appium/WebDriverAgent.git"
WDA_PORT = 8100
FIRST_BUILD_HINT = "初回はビルドに数分かかる"


class WDAError(Exception):
    """WDA answered with an error, or could not be reached."""


def cache_dir() -> Path:
    return Path(os.environ.get("UIAI_CACHE_DIR") or Path.home() / "Library" / "Caches" / "uiai") / "wda"


# --------------------------------------------------------------------------- #
# signing team
# --------------------------------------------------------------------------- #


def xcode_teams() -> list[dict]:
    """Teams of the accounts signed in to Xcode: [{"id", "name", "free"}] (empty if unknown)."""
    try:
        r = subprocess.run(["defaults", "export", "com.apple.dt.Xcode", "-"], capture_output=True, timeout=10)
        prefs = plistlib.loads(r.stdout) if r.returncode == 0 and r.stdout else {}
    except Exception:  # noqa: BLE001 - best effort: no Xcode, no prefs, or prefs in an unexpected shape
        return []
    return teams_from_prefs(prefs)


def teams_from_prefs(prefs: dict) -> list[dict]:
    out: dict[str, dict] = {}
    by_account = prefs.get("IDEProvisioningTeamByIdentifier") or prefs.get("IDEProvisioningTeams") or {}
    for teams in by_account.values():
        for t in teams if isinstance(teams, list) else []:
            tid = t.get("teamID")
            if tid:
                out[tid] = {"id": tid, "name": t.get("teamName", ""),
                            "free": bool(t.get("isFreeProvisioningTeam")) or t.get("teamType") == "Personal Team"}
    return list(out.values())


def choose_team(teams: list[dict], wanted: str | None) -> str:
    """--ios-team (or UIAI_IOS_TEAM), else the only paid team, else the only team."""
    if wanted:
        return wanted
    paid = [t for t in teams if not t["free"]]
    if len(paid) == 1:
        return paid[0]["id"]
    if not teams:
        raise DriverError("署名に使うチームがない。Xcode の Settings > Accounts で Apple ID を追加する"
                          "（無料の Apple ID でもよい）。チーム ID が分かっていれば --ios-team で指定する")
    if len(teams) == 1:
        return teams[0]["id"]
    names = ", ".join(f"{t['id']}（{t['name'] or '名前なし'}{'・無料' if t['free'] else ''}）" for t in teams)
    raise DriverError(f"署名に使えるチームが複数ある。--ios-team で選ぶ: {names}")


def bundle_id(team: str) -> str:
    """The runner's bundle ID: unique per team, as an App ID must be (com.facebook.* belongs to someone else)."""
    return f"uiai.wda.team-{team.lower()}"


# --------------------------------------------------------------------------- #
# source, build, start
# --------------------------------------------------------------------------- #


def _git_head(d: Path) -> str:
    r = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def source_dir() -> Path:
    """The pinned WDA checkout, cloned on first use and checked against WDA_COMMIT."""
    d = cache_dir() / f"WebDriverAgent-{WDA_VERSION}"
    if (d / "WebDriverAgent.xcodeproj").is_dir() and _git_head(d) == WDA_COMMIT:
        return d
    if not shutil.which("git"):
        raise DriverError("git が見つからない（WebDriverAgent の取得に使う。Xcode の Command Line Tools に含まれる）")
    tmp = d.with_name(d.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", f"v{WDA_VERSION}", WDA_REPO,
                            str(tmp)], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as e:
        raise DriverError(f"WebDriverAgent の取得が 10 分で終わらない（{WDA_REPO}）") from e
    if r.returncode != 0:
        raise DriverError(f"WebDriverAgent を取得できない（{WDA_REPO}）: {(r.stderr or r.stdout).strip()[-300:]}")
    head = _git_head(tmp)
    if head != WDA_COMMIT:
        shutil.rmtree(tmp, ignore_errors=True)
        raise DriverError(f"取得した WebDriverAgent v{WDA_VERSION} のコミットが想定と違う（{head[:12]}）。取得をやめた")
    shutil.rmtree(d, ignore_errors=True)
    tmp.rename(d)
    return d


# What xcodebuild says when the iPhone or the account needs a hand -> what to do (checked in this order).
HINTS = [
    (r"developer mode", "iPhone のデベロッパモードをオンにする（設定 > プライバシーとセキュリティ > デベロッパモード）"),
    (r"(ui ?automation|automation mode)",
     "iPhone の設定 > デベロッパ で「UI オートメーションを有効にする」をオンにする"),
    (r"(not been explicitly trusted|untrusted developer|invalid code signature|is not trusted|profile has not been)",
     "iPhone の設定 > 一般 > VPN とデバイス管理 で、デベロッパ App の開発元を信頼する"),
    (r"(device is locked|is passcode protected|unlock the device|unlock .* to continue)",
     "iPhone のロックを解除して、もう一度実行する"),
    (r"(is not paired|pairing (failed|is required)|trust this computer)", "iPhone で「このコンピュータを信頼」を選ぶ"),
    (r"maximum (number|limit) of", "無料のチームの上限（7 日で 10 個の App ID など）に達した。数日待つか、有料のチームを使う"),
    (r"(no account|no accounts|sign in with your apple id|requires a development team|no signing certificate)",
     "Xcode の Settings > Accounts でチームの Apple ID にサインインする（--ios-team でチームを選ぶ）"),
    (r"(failed registering bundle identifier|bundle identifier .{0,80}(cannot be registered|is not available))",
     "WebDriverAgent の bundle ID を登録できない（同じ ID を別のチームが使っている）"),
]


def explain(log: str) -> str:
    low = log.lower()
    for pattern, hint in HINTS:
        if re.search(pattern, low):
            return hint
    return ""


class WDARunner:
    """Builds WDA for one device and keeps it running (xcodebuild test-without-building) until stop()."""

    def __init__(self, udid: str, team: str, say: Callable[[str], None] | None = None):
        self.udid, self.team = udid, team
        self.say = say or (lambda s: print(s, file=sys.stderr, flush=True))
        self.derived = cache_dir() / f"build-{team}"
        self.log_path = cache_dir() / f"wda-{udid}.log"
        self.proc: subprocess.Popen | None = None
        self._log = None

    def _signing(self) -> list[str]:
        return ["CODE_SIGN_STYLE=Automatic", f"DEVELOPMENT_TEAM={self.team}",
                f"PRODUCT_BUNDLE_IDENTIFIER={bundle_id(self.team)}",
                "GCC_TREAT_WARNINGS_AS_ERRORS=0", "COMPILER_INDEX_STORE_ENABLE=NO"]

    def _fail(self, what: str, log: str) -> DriverError:
        hint = explain(log)
        tail = "\n".join(ln for ln in log.strip().splitlines()[-6:])
        return DriverError(f"WebDriverAgent を{what}できない。" + (hint + "。" if hint else "")
                           + f"記録: {self.log_path}\n{tail}")

    def build(self) -> None:
        src = source_dir()
        self.derived.mkdir(parents=True, exist_ok=True)
        cmd = ["xcodebuild", "build-for-testing", "-project", str(src / "WebDriverAgent.xcodeproj"),
               "-scheme", "WebDriverAgentRunner", "-destination", f"id={self.udid}",
               "-derivedDataPath", str(self.derived),
               "-allowProvisioningUpdates", "-allowProvisioningDeviceRegistration", *self._signing()]
        first = not self.xctestrun()
        self.say(f"uiai: WebDriverAgent をビルドする（{FIRST_BUILD_HINT}）" if first else
                 "uiai: WebDriverAgent のビルドを確かめる")
        # one build at a time per team: parallel runs on several iPhones share the build folder
        try:
            with open(self.derived / ".lock", "w") as lock, open(self.log_path, "w", encoding="utf-8") as log:
                fcntl.flock(lock, fcntl.LOCK_EX)
                r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=src, timeout=1800)
        except FileNotFoundError as e:
            raise DriverError("xcodebuild が見つからない（iPhone には Xcode が要る）") from e
        except subprocess.TimeoutExpired as e:
            raise self._fail("30 分以内にビルド", self.log_path.read_text(encoding="utf-8", errors="replace")) from e
        if r.returncode != 0 or not self.xctestrun():
            raise self._fail("ビルド", self.log_path.read_text(encoding="utf-8", errors="replace"))

    def xctestrun(self) -> Path | None:
        found = sorted((self.derived / "Build" / "Products").glob("WebDriverAgentRunner_iphoneos*.xctestrun"),
                       key=lambda p: p.stat().st_mtime)
        return found[-1] if found else None

    def start(self) -> None:
        run = self.xctestrun()
        assert run is not None
        self._log = open(self.log_path, "a", encoding="utf-8")
        self._log.write("\n==== test-without-building ====\n")
        self._log.flush()
        try:
            self.proc = subprocess.Popen(
                ["xcodebuild", "test-without-building", "-xctestrun", str(run), "-destination", f"id={self.udid}"],
                stdout=self._log, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as e:
            raise DriverError(f"xcodebuild を起動できない: {e}") from e

    def failed(self) -> DriverError | None:
        """The error if xcodebuild has ended (WDA is not going to come up)."""
        if self.proc is None or self.proc.poll() is None:
            return None
        return self._fail("起動", self.log_path.read_text(encoding="utf-8", errors="replace"))

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGINT)  # xcodebuild stops the test (and WDA) on an interrupt
                self.proc.wait(timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except OSError:
                    pass
        self.proc = None
        if self._log is not None:
            self._log.close()
            self._log = None


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


class _Conn(http.client.HTTPConnection):
    def __init__(self, connect: Callable[[], Any], timeout: float):
        super().__init__("localhost", WDA_PORT, timeout=timeout)
        self._factory = connect

    def connect(self) -> None:
        self.sock = self._factory()
        self.sock.settimeout(self.timeout)


class WDAClient:
    """WDA's HTTP API over a socket factory (usbmux in use, a local TCP server in the tests)."""

    def __init__(self, connect: Callable[[], Any], timeout: float = 60.0):
        self.connect, self.timeout = connect, timeout
        self.conn: _Conn | None = None
        self.sid: str | None = None

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def call(self, method: str, path: str, body: Any = None, timeout: float | None = None) -> Any:
        """The response's `value`. Errors (HTTP or WDA's own) raise WDAError."""
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"} if data is not None else {}
        for attempt in (0, 1):
            if self.conn is None:
                self.conn = _Conn(self.connect, timeout or self.timeout)
            self.conn.timeout = timeout or self.timeout
            try:
                self.conn.request(method, path, body=data, headers=headers)
                resp = self.conn.getresponse()
                raw = resp.read()
                break
            except (OSError, http.client.HTTPException) as e:
                self.close()
                # a kept-alive connection the server closed fails before anything is done: try once more
                if attempt == 0 and isinstance(e, (http.client.RemoteDisconnected, BrokenPipeError,
                                                   ConnectionResetError)):
                    continue
                raise WDAError(f"WebDriverAgent に届かない（{method} {path}）: {e}") from e
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError as e:
            raise WDAError(f"WebDriverAgent の応答を読めない（{method} {path}）: {raw[:120]!r}") from e
        value = payload.get("value") if isinstance(payload, dict) else None
        if resp.status >= 400 or (isinstance(value, dict) and "error" in value):
            msg = value.get("message") or value.get("error") if isinstance(value, dict) else raw[:200]
            raise WDAError(f"{method} {path}: {msg}")
        return value

    def s(self, path: str) -> str:
        """A path in the current session."""
        return f"/session/{self.sid}{path}"

    # -- commands used by the driver ----------------------------------------------------------------
    def ready(self, timeout: float = 3.0) -> bool:
        try:
            self.call("GET", "/status", timeout=timeout)
            return True
        except WDAError:
            self.close()
            return False

    def start_session(self) -> None:
        value = self.call("POST", "/session", {"capabilities": {"alwaysMatch": {}, "firstMatch": [{}]}})
        self.sid = (value or {}).get("sessionId")
        if not self.sid:
            raise WDAError(f"セッションを作れない: {value}")
        # JPEG (0.8): the default HEIC cannot be decoded by Pillow, and PNG is larger to send
        self.call("POST", self.s("/appium/settings"), {"settings": {"screenshotQuality": 1}})

    def screenshot(self) -> bytes:
        return base64.b64decode(self.call("GET", "/screenshot"))

    def window_size(self) -> tuple[float, float]:
        v = self.call("GET", self.s("/window/size"))
        return float(v["width"]), float(v["height"])

    def tap(self, x: float, y: float) -> None:
        self.call("POST", self.s("/wda/tap"), {"x": x, "y": y})

    def type_text(self, text: str, frequency: int | None = None) -> None:
        """frequency: characters per second (WDA's default is 60)."""
        body: dict[str, Any] = {"value": [text]}
        if frequency:
            body["frequency"] = frequency
        self.call("POST", self.s("/wda/keys"), body)

    def drag(self, x1: float, y1: float, x2: float, y2: float, ms: int = 300) -> None:
        """A one-finger touch drag (W3C actions, coordinates in points)."""
        self.call("POST", self.s("/actions"), {"actions": [{
            "type": "pointer", "id": "finger1", "parameters": {"pointerType": "touch"},
            "actions": [{"type": "pointerMove", "duration": 0, "x": x1, "y": y1},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pointerMove", "duration": ms, "x": x2, "y": y2},
                        {"type": "pointerUp", "button": 0}]}]})

    def home(self) -> None:
        self.call("POST", "/wda/homescreen")

    def launch(self, bundle: str) -> None:
        self.call("POST", self.s("/wda/apps/launch"), {"bundleId": bundle})

    def terminate(self, bundle: str) -> None:
        self.call("POST", self.s("/wda/apps/terminate"), {"bundleId": bundle})


def wait_ready(client: WDAClient, runner: WDARunner | None, timeout: float = 180.0) -> None:
    """Wait for WDA's /status while xcodebuild starts it; fail early if xcodebuild ends."""
    end = time.time() + timeout
    while time.time() < end:
        if client.ready():
            return
        if runner is not None and (err := runner.failed()) is not None:
            raise err
        time.sleep(1.0)
    raise DriverError(f"WebDriverAgent が {timeout:g} 秒たっても応答しない。iPhone のロックを解除して、"
                      f"もう一度実行する（記録: {runner.log_path if runner else '-'}）")
