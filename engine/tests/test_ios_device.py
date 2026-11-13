"""Real iPhones: usbmux framing, WDA's HTTP API through the driver, team choice, build/start of WDA, and which
iOS driver is picked. A fake usbmuxd (UNIX socket) and a fake WDA (local HTTP server) stand in for the iPhone."""

from __future__ import annotations

import base64
import io
import json
import plistlib
import shutil
import socket
import struct
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from uiai import platform as platform_mod
from uiai.drivers import DriverError, ios as ios_sim, ios_device, make_driver, usbmux, wda
from uiai.drivers.ios_device import IOSDeviceDriver
from uiai.drivers.wda import WDAClient, WDAError

# --------------------------------------------------------------------------- usbmux


class FakeUsbmuxd:
    """Answers ListDevices, and Connect to port 8100 of device 7 (then echoes one line back upper-cased)."""

    def __init__(self, devices: list[dict]):
        self.dir = tempfile.mkdtemp(prefix="um", dir="/tmp")  # AF_UNIX paths are short on macOS
        self.path = str(Path(self.dir) / "s")
        self.devices, self.got = devices, []
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(self.path)
        self.srv.listen()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(c,), daemon=True).start()

    def _one(self, c):
        with c:
            length, version, message, tag = struct.unpack("<IIII", c.recv(16))
            msg = plistlib.loads(c.recv(length - 16))
            self.got.append((version, message, tag, msg))
            if msg["MessageType"] == "ListDevices":
                reply = {"DeviceList": [{"DeviceID": d["id"], "MessageType": "Attached",
                                         "Properties": {"SerialNumber": d["udid"], "ConnectionType": d["conn"]}}
                                        for d in self.devices]}
            else:
                ok = msg["DeviceID"] == 7 and msg["PortNumber"] == 0xA41F  # 8100 = 0x1FA4, byte-swapped
                reply = {"MessageType": "Result", "Number": 0 if ok else 3}
            body = plistlib.dumps(reply)
            c.sendall(struct.pack("<IIII", 16 + len(body), 1, 8, tag) + body)
            if msg["MessageType"] == "Connect" and reply["Number"] == 0:
                c.sendall(c.recv(100).upper())

    def close(self):
        self.srv.close()
        shutil.rmtree(self.dir, ignore_errors=True)


@pytest.fixture
def usbmuxd():
    d = FakeUsbmuxd([{"id": 7, "udid": "00008101-00026C5914C2001E", "conn": "USB"},
                     {"id": 9, "udid": "00008101-00026C5914C2001E", "conn": "Network"}])
    yield d
    d.close()


def test_usbmux_lists_devices_and_connects_to_a_port(usbmuxd):
    devs = usbmux.devices(usbmuxd.path)
    assert devs == [{"id": 7, "udid": "00008101-00026C5914C2001E", "connection": "USB"},
                    {"id": 9, "udid": "00008101-00026C5914C2001E", "connection": "Network"}]
    assert usbmuxd.got[0][:2] == (1, 8) and usbmuxd.got[0][3]["ProgName"] == "uiai"
    s = usbmux.connect(7, 8100, usbmuxd.path)
    s.sendall(b"ping")
    assert s.recv(10) == b"PING"  # from here on the socket is the raw stream
    s.close()


def test_usbmux_refused_connection_says_why(usbmuxd):
    with pytest.raises(usbmux.UsbmuxError, match="WebDriverAgent が動いていない"):
        usbmux.connect(9, 8100, usbmuxd.path)


def test_usbmux_missing_daemon_is_an_oserror(tmp_path):
    with pytest.raises(OSError, match="usbmuxd につながらない"):
        usbmux.devices(str(tmp_path / "none"))


def test_udids_match_with_or_without_the_hyphen():
    assert usbmux.normalize_udid("00008101-00026C5914C2001E") == usbmux.normalize_udid("0000810100026c5914c2001e")


# --------------------------------------------------------------------------- fake WDA

SCREEN_PX, SCREEN_PT = (1170, 2532), (390, 844)


def jpeg_b64(size=SCREEN_PX) -> str:
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, "JPEG")
    return base64.b64encode(out.getvalue()).decode()


class FakeWDA:
    def __init__(self):
        self.calls: list[tuple[str, str, object]] = []
        self.fail: dict[str, tuple[int, dict]] = {}   # path -> (status, value)
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n)) if n else None
                fake.calls.append((self.command, self.path, body))
                status, value = fake.answer(self.command, self.path, body)
                data = json.dumps({"value": value, "sessionId": "S1"}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_DELETE = _reply

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]

    def answer(self, method, path, body):
        if path in self.fail:
            return self.fail[path]
        if path == "/session":
            return 200, {"sessionId": "S1", "capabilities": {}}
        if path == "/screenshot":
            return 200, jpeg_b64()
        if path == "/session/S1/window/size":
            return 200, {"width": SCREEN_PT[0], "height": SCREEN_PT[1]}
        return 200, None

    def client(self) -> WDAClient:
        return WDAClient(lambda: socket.create_connection(("127.0.0.1", self.port)))

    def posts(self, prefix="/session/S1/"):
        return [(p[len(prefix):] if p.startswith(prefix) else p, b) for m, p, b in self.calls if m == "POST"]


@pytest.fixture
def fake_wda():
    f = FakeWDA()
    yield f
    f.srv.shutdown()


@pytest.fixture
def drv(fake_wda):
    d = IOSDeviceDriver(client=fake_wda.client())
    fake_wda.calls.clear()
    return d


def test_driver_starts_a_session_with_jpeg_screenshots_and_sizes_the_image(fake_wda):
    d = IOSDeviceDriver(client=fake_wda.client())
    assert fake_wda.posts()[:2] == [("/session", {"capabilities": {"alwaysMatch": {}, "firstMatch": [{}]}}),
                                    ("appium/settings", {"settings": {"screenshotQuality": 1}})]
    assert (d.w, d.h, d.pw, d.ph) == (*SCREEN_PX, *SCREEN_PT)
    assert (d.iw, d.ih) == (540, round(2532 * 540 / 1170))
    assert d.grab().size == (d.iw, d.ih)


def test_tap_and_input_are_sent_in_points(drv, fake_wda):
    assert drv.act({"type": "tap", "x": 270, "y": 584}, "app") == "ok"
    assert drv.act({"type": "input", "x": 270, "y": 100, "text": "東京タワー"}, "app") == "ok"
    pt = 390 / 540
    assert fake_wda.posts() == [("wda/tap", {"x": round(270 * pt, 1), "y": round(584 * pt, 1)}),
                                ("wda/tap", {"x": round(270 * pt, 1), "y": round(100 * pt, 1)}),
                                ("wda/keys", {"value": ["東京タワー"]})]  # not limited to ASCII as on the simulator


def test_keys_home_back_and_scroll(drv, fake_wda):
    assert drv.act({"type": "key", "key": "Enter"}, "app") == "ok"
    assert drv.act({"type": "key", "key": "home"}, "app") == "ok"
    assert drv.act({"type": "key", "key": "F13"}, "app") == "error: 未知のキー f13"
    assert drv.act({"type": "back"}, "app") == "ok"
    assert drv.act({"type": "scroll", "direction": "down"}, "app") == "ok"
    posts = fake_wda.posts()
    assert posts[0] == ("wda/keys", {"value": ["\n"]}) and posts[1] == ("/wda/homescreen", None)

    def path(body):
        moves = [a for a in body["actions"][0]["actions"] if a["type"] == "pointerMove"]
        return [(m["x"], m["y"]) for m in moves]

    assert posts[2][0] == "actions" and posts[2][1]["actions"][0]["parameters"] == {"pointerType": "touch"}
    assert path(posts[2][1]) == [(2, 422), (390 * 0.7, 422)]                       # from the left edge
    assert path(posts[3][1]) == [(195, 844 * 0.7), (195, 844 * 0.3)]                # finger moves up


def test_launch_error_reset_and_close(drv, fake_wda):
    fake_wda.fail["/session/S1/wda/apps/launch"] = (500, {"error": "unknown error",
                                                          "message": "App with bundle identifier 'x' unknown"})
    r = drv.act({"type": "launch"}, "x")
    assert r.startswith("error: 起動できない（x）") and "unknown" in r
    drv.settler.acted_at = 1.0
    drv.reset("com.example", SimpleNamespace(reset=["com.other"]))
    assert fake_wda.posts()[-3:] == [("wda/apps/terminate", {"bundleId": "com.example"}),
                                     ("wda/apps/terminate", {"bundleId": "com.other"}),
                                     ("/wda/homescreen", None)]
    assert drv.settler.acted_at is None
    drv.close()
    assert fake_wda.calls[-1][:2] == ("DELETE", "/session/S1")


def test_wda_errors_and_an_unreachable_wda():
    with pytest.raises(WDAError, match="届かない"):
        WDAClient(lambda: socket.create_connection(("127.0.0.1", 9)), timeout=2).call("GET", "/status")
    assert not WDAClient(lambda: socket.create_connection(("127.0.0.1", 9))).ready()


def test_a_failing_session_is_a_driver_error(fake_wda):
    fake_wda.fail["/session"] = (500, {"error": "session not created", "message": "XCTest is not ready"})
    with pytest.raises(DriverError, match="XCTest is not ready"):
        IOSDeviceDriver(client=fake_wda.client())


# --------------------------------------------------------------------------- team, build, start

PREFS = {"IDEProvisioningTeamByIdentifier": {
    "acct-1": [{"teamID": "FREE111111", "teamName": "me (Personal Team)", "teamType": "Personal Team",
                "isFreeProvisioningTeam": True}],
    "acct-2": [{"teamID": "PAID222222", "teamName": "Me", "teamType": "Individual", "isFreeProvisioningTeam": False}]}}


def test_team_choice_prefers_the_paid_team_and_free_works_alone():
    teams = wda.teams_from_prefs(PREFS)
    assert {(t["id"], t["free"]) for t in teams} == {("FREE111111", True), ("PAID222222", False)}
    assert wda.choose_team(teams, None) == "PAID222222"
    assert wda.choose_team([t for t in teams if t["free"]], None) == "FREE111111"
    assert wda.choose_team(teams, "OTHER33333") == "OTHER33333"
    with pytest.raises(DriverError, match="Settings > Accounts"):
        wda.choose_team([], None)
    two_free = [{"id": "A", "name": "", "free": True}, {"id": "B", "name": "", "free": True}]
    with pytest.raises(DriverError, match="--ios-team で選ぶ: A"):
        wda.choose_team(two_free, None)


def test_bundle_id_is_per_team():
    assert wda.bundle_id("4SVXPPZZ7N") == "uiai.wda.team-4svxppzz7n"


@pytest.mark.parametrize("log, hint", [
    ("error: Developer Mode disabled", "デベロッパモード"),
    ("The test runner failed to initialize for UI testing. (Underlying Error: Enable UI Automation)", "UI オートメーション"),
    ("Unable to launch uiai.wda... because it has an invalid code signature, inadequate entitlements or its "
     "profile has not been explicitly trusted by the user.", "VPN とデバイス管理"),
    ("error: No Account for Team \"X\". Add a new account in Accounts settings", "Settings > Accounts"),
    ("Failed Registering Bundle Identifier: The app identifier \"uiai.wda\" cannot be registered", "bundle ID"),
    ("** BUILD FAILED ** something else", ""),
])
def test_xcodebuild_messages_get_a_hint(log, hint):
    assert (hint in wda.explain(log)) if hint else wda.explain(log) == ""


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("UIAI_CACHE_DIR", str(tmp_path))
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr(wda, "source_dir", lambda: src)
    return tmp_path / "wda"


def test_build_signs_with_the_team_and_a_bundle_id_of_its_own(cache, monkeypatch):
    seen = {}

    def run(cmd, stdout=None, **kw):
        seen["cmd"] = cmd
        products = cache / "build-TEAM123456" / "Build" / "Products"
        products.mkdir(parents=True, exist_ok=True)
        (products / "WebDriverAgentRunner_iphoneos26.2-arm64.xctestrun").write_text("x")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(wda.subprocess, "run", run)
    said = []
    r = wda.WDARunner("00008101-00026C5914C2001E", "TEAM123456", say=said.append)
    r.build()
    cmd = seen["cmd"]
    assert cmd[:2] == ["xcodebuild", "build-for-testing"] and "id=00008101-00026C5914C2001E" in cmd
    for arg in ("-allowProvisioningUpdates", "-allowProvisioningDeviceRegistration", "CODE_SIGN_STYLE=Automatic",
                "DEVELOPMENT_TEAM=TEAM123456", "PRODUCT_BUNDLE_IDENTIFIER=uiai.wda.team-team123456"):
        assert arg in cmd
    assert "初回" in said[0] and r.xctestrun().name.endswith(".xctestrun")


def test_a_failed_build_explains_itself(cache, monkeypatch):
    def run(cmd, stdout=None, **kw):
        stdout.write("Signing for \"WebDriverAgentRunner\" requires a development team.\n** BUILD FAILED **\n")
        return SimpleNamespace(returncode=65)

    monkeypatch.setattr(wda.subprocess, "run", run)
    with pytest.raises(DriverError, match="ビルドできない。Xcode の Settings > Accounts") as e:
        wda.WDARunner("U", "T", say=lambda s: None).build()
    assert "BUILD FAILED" in str(e.value)


def test_waiting_for_wda_stops_when_xcodebuild_ends(cache, monkeypatch):
    r = wda.WDARunner("U", "T", say=lambda s: None)
    r.log_path.parent.mkdir(parents=True, exist_ok=True)
    r.log_path.write_text("Developer Mode disabled\n", encoding="utf-8")
    r.proc = SimpleNamespace(poll=lambda: 70, pid=0)
    monkeypatch.setattr(wda.time, "sleep", lambda s: None)
    with pytest.raises(DriverError, match="起動できない。iPhone のデベロッパモード"):
        wda.wait_ready(WDAClient(lambda: socket.create_connection(("127.0.0.1", 9))), r, timeout=5)


# --------------------------------------------------------------------------- which iOS driver


@pytest.fixture
def ios_world(monkeypatch):
    made = []
    monkeypatch.setattr(ios_device, "IOSDeviceDriver", lambda udid, team: made.append(("device", udid, team)))
    monkeypatch.setattr(ios_sim, "IOSDriver", lambda udid: made.append(("sim", udid)))
    world = SimpleNamespace(made=made, devices=[], sims=[])
    monkeypatch.setattr(ios_device, "usb_devices", lambda: world.devices)
    monkeypatch.setattr(ios_sim, "booted_simulators", lambda: world.sims)
    return world


IPHONE = {"id": 7, "udid": "00008101-00026C5914C2001E", "connection": "USB"}
SIM = {"udid": "SIM-1", "name": "iPhone 17"}


def test_a_connected_iphone_is_used_when_no_simulator_is_booted(ios_world):
    ios_world.devices = [IPHONE]
    make_driver("ios", team="T")
    assert ios_world.made == [("device", None, "T")]


def test_with_iphone_and_simulator_udid_decides(ios_world):
    ios_world.devices, ios_world.sims = [IPHONE], [SIM]
    with pytest.raises(DriverError, match="両方がある。--udid で選ぶ: 00008101-00026C5914C2001E（iPhone・USB）, SIM-1"):
        make_driver("ios")
    make_driver("ios", udid="0000810100026c5914c2001e")
    make_driver("ios", udid="SIM-1")
    assert ios_world.made == [("device", "0000810100026c5914c2001e", None), ("sim", "SIM-1")]


def test_without_an_iphone_the_simulator_driver_is_used(ios_world):
    ios_world.sims = [SIM]
    make_driver("ios")
    assert ios_world.made == [("sim", None)]


def test_probe_counts_usb_iphones_as_ios(monkeypatch):
    monkeypatch.setattr(platform_mod, "android_serials", lambda: [])
    monkeypatch.setattr(platform_mod, "booted_udids", lambda: [])
    monkeypatch.setattr(platform_mod, "ios_device_udids", lambda: [IPHONE["udid"]])
    assert platform_mod.probe()["ios"]
    assert platform_mod.probe(udid="0000810100026C5914C2001E")["ios"]
    assert not platform_mod.probe(udid="SIM-1")["ios"]


def test_xcode_gets_the_hyphenated_udid_of_newer_devices():
    assert usbmux.xcode_udid("0000810100026C5914C2001E") == "00008101-00026C5914C2001E"
    assert usbmux.xcode_udid("00008101-00026C5914C2001E") == "00008101-00026C5914C2001E"
    old = "a" * 40  # older devices: 40 hex digits, no hyphen
    assert usbmux.xcode_udid(old) == old


def test_a_build_that_never_ends_is_a_driver_error(cache, monkeypatch):
    def run(cmd, stdout=None, timeout=None, **kw):
        raise wda.subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(wda.subprocess, "run", run)
    with pytest.raises(DriverError, match="30 分以内にビルドできない"):
        wda.WDARunner("U", "T", say=lambda s: None).build()
