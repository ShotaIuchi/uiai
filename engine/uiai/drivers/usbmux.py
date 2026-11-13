"""usbmuxd: the Mac's daemon that lists iPhones on USB and opens TCP connections to ports on them.

Used to reach WebDriverAgent's HTTP port on a real iPhone without iproxy, go-ios or Appium. The protocol is
the plist variant of usbmux: a 16-byte little-endian header (length, version 1, message 8 = plist, tag)
followed by an XML plist. After a successful Connect the socket carries the raw TCP stream.
"""

from __future__ import annotations

import plistlib
import socket
import struct

SOCKET_PATH = "/var/run/usbmuxd"
_HEADER = struct.Struct("<IIII")
_PLIST = 8
_RESULTS = {1: "usbmuxd が要求を受け付けない", 2: "その iPhone が見つからない（外れた？）",
            3: "iPhone の側で接続を断られた（WebDriverAgent が動いていない）", 6: "usbmuxd の版が合わない"}


class UsbmuxError(OSError):
    """An OSError, so that a failed connection reads like any other socket error to http.client's callers."""


def normalize_udid(udid: str) -> str:
    """UDIDs come with or without the hyphen of newer devices (00008101-000…); compare them without it."""
    return udid.replace("-", "").lower()


def xcode_udid(udid: str) -> str:
    """The UDID as Xcode writes it: newer devices (24 hex digits) have a hyphen after the first 8."""
    u = udid.strip()
    return f"{u[:8]}-{u[8:]}" if len(u) == 24 and "-" not in u else u


def _open(path: str, timeout: float) -> socket.socket:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(path)
    except OSError as e:
        s.close()
        raise UsbmuxError(f"usbmuxd につながらない（{path}）: {e}") from e
    return s


def _send(s: socket.socket, msg: dict, tag: int) -> None:
    body = plistlib.dumps({**msg, "ClientVersionString": "uiai", "ProgName": "uiai", "kLibUSBMuxVersion": 3})
    s.sendall(_HEADER.pack(_HEADER.size + len(body), 1, _PLIST, tag) + body)


def _recv_exact(s: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise UsbmuxError("usbmuxd が接続を閉じた")
        buf += chunk
    return buf


def _recv(s: socket.socket) -> dict:
    length, _version, _message, _tag = _HEADER.unpack(_recv_exact(s, _HEADER.size))
    if length < _HEADER.size:
        raise UsbmuxError(f"usbmuxd の応答が壊れている（長さ {length}）")
    try:
        return plistlib.loads(_recv_exact(s, length - _HEADER.size))
    except plistlib.InvalidFileException as e:
        raise UsbmuxError("usbmuxd の応答を読めない") from e


def devices(path: str = SOCKET_PATH, timeout: float = 5.0) -> list[dict]:
    """Attached devices: [{"id": DeviceID, "udid": serial number, "connection": "USB" | "Network"}]."""
    s = _open(path, timeout)
    try:
        _send(s, {"MessageType": "ListDevices"}, 1)
        reply = _recv(s)
    except OSError as e:
        raise UsbmuxError(f"usbmuxd から一覧を取れない: {e}") from e
    finally:
        s.close()
    out = []
    for d in reply.get("DeviceList", []):
        props = d.get("Properties", {})
        if "DeviceID" in d and props.get("SerialNumber"):
            out.append({"id": d["DeviceID"], "udid": props["SerialNumber"],
                        "connection": props.get("ConnectionType", "")})
    return out


def connect(device_id: int, port: int, path: str = SOCKET_PATH, timeout: float = 10.0) -> socket.socket:
    """A socket connected to `port` on the device (a plain TCP stream from here on)."""
    s = _open(path, timeout)
    try:
        # the port goes in network byte order inside the (little-endian) plist integer
        _send(s, {"MessageType": "Connect", "DeviceID": device_id,
                  "PortNumber": ((port & 0xFF) << 8) | (port >> 8)}, 2)
        reply = _recv(s)
    except (OSError, UsbmuxError) as e:
        s.close()
        raise UsbmuxError(f"iPhone のポート {port} につながらない: {e}") from e
    number = reply.get("Number")
    if reply.get("MessageType") != "Result" or number != 0:
        s.close()
        raise UsbmuxError(f"iPhone のポート {port} につながらない: {_RESULTS.get(number, f'結果 {number}')}")
    return s
