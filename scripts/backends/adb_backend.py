"""ADB backend for compiled scenario execution."""

import os
import subprocess
import time


class ADBError(Exception):
    """Raised when an ADB command fails."""


class ADBBackend:
    """Wrapper for ADB commands used by the compiled runner."""

    def __init__(self, device_serial: str | None = None):
        self.device_serial = device_serial
        self._base_cmd = self._build_base_cmd()
        self.screen_width = 0
        self.screen_height = 0

    def _build_base_cmd(self) -> list[str]:
        cmd = ["adb"]
        if self.device_serial:
            cmd.extend(["-s", self.device_serial])
        return cmd

    def _run(
        self, args: list[str], timeout: int = 30, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run an ADB command."""
        cmd = self._base_cmd + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if check and result.returncode != 0:
                raise ADBError(
                    f"ADB command failed: {' '.join(cmd)}\n"
                    f"stderr: {result.stderr.strip()}"
                )
            return result
        except subprocess.TimeoutExpired as e:
            raise ADBError(f"ADB command timed out: {' '.join(cmd)}") from e

    def check_connection(self) -> bool:
        """Check if a device is connected."""
        result = self._run(["devices"], check=False)
        lines = result.stdout.strip().split("\n")[1:]
        for line in lines:
            parts = line.strip().split("\t")
            if len(parts) == 2 and parts[1] == "device":
                if not self.device_serial or parts[0] == self.device_serial:
                    return True
        return False

    def get_screen_size(self) -> tuple[int, int]:
        """Get device screen size."""
        result = self._run(["shell", "wm", "size"])
        for line in result.stdout.strip().split("\n"):
            if "Physical size" in line or "Override size" in line:
                size_str = line.split(":")[-1].strip()
                w, h = size_str.split("x")
                self.screen_width = int(w)
                self.screen_height = int(h)
                return self.screen_width, self.screen_height
        raise ADBError("Could not determine screen size")

    def launch_app(self, package: str) -> None:
        """Launch an app using monkey."""
        self._run([
            "shell", "monkey",
            "-p", package,
            "-c", "android.intent.category.LAUNCHER",
            "1",
        ])

    def stop_app(self, package: str) -> None:
        """Force stop an app."""
        self._run(["shell", "am", "force-stop", package])

    def clear_app_data(self, package: str) -> None:
        """Clear app data."""
        self._run(["shell", "pm", "clear", package])

    def tap(self, x: int, y: int) -> None:
        """Tap at coordinates."""
        self._run(["shell", "input", "tap", str(x), str(y)])

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
    ) -> None:
        """Swipe from (x1,y1) to (x2,y2)."""
        self._run([
            "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration_ms),
        ])

    def input_text(self, text: str) -> None:
        """Input text via ADB.

        Handles special characters by escaping them.
        """
        escaped = text.replace("\\", "\\\\")
        escaped = escaped.replace(" ", "%s")
        escaped = escaped.replace("&", "\\&")
        escaped = escaped.replace("<", "\\<")
        escaped = escaped.replace(">", "\\>")
        escaped = escaped.replace("'", "\\'")
        escaped = escaped.replace('"', '\\"')
        escaped = escaped.replace("(", "\\(")
        escaped = escaped.replace(")", "\\)")
        escaped = escaped.replace("|", "\\|")
        escaped = escaped.replace(";", "\\;")
        self._run(["shell", "input", "text", escaped])

    def keyevent(self, keycode: int) -> None:
        """Send a key event."""
        self._run(["shell", "input", "keyevent", str(keycode)])

    def screenshot(self, local_path: str) -> None:
        """Capture screenshot to local file."""
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        result = self._run(["exec-out", "screencap", "-p"], check=False)
        if result.returncode == 0:
            with open(local_path, "wb") as f:
                f.write(result.stdout.encode("latin-1") if isinstance(result.stdout, str) else result.stdout)
        else:
            # Fallback: capture on device then pull
            self._run(["shell", "screencap", "/sdcard/_uiai_screenshot.png"])
            self._run(["pull", "/sdcard/_uiai_screenshot.png", local_path])
            self._run(["shell", "rm", "/sdcard/_uiai_screenshot.png"], check=False)

    def dump_uitree(self) -> str:
        """Dump UITree XML and return as string."""
        self._run(["shell", "uiautomator", "dump", "/sdcard/_uiai_ui.xml"])
        result = self._run(["shell", "cat", "/sdcard/_uiai_ui.xml"])
        self._run(["shell", "rm", "/sdcard/_uiai_ui.xml"], check=False)
        return result.stdout.strip()

    def save_uitree(self, local_path: str) -> str:
        """Dump UITree XML and save to local file. Returns XML content."""
        xml_content = self.dump_uitree()
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(xml_content)
        return xml_content

    def scroll(
        self,
        direction: str,
        distance: int = 500,
        duration_ms: int = 300,
    ) -> None:
        """Scroll in a direction.

        Args:
            direction: 'up', 'down', 'left', 'right'.
            distance: Scroll distance in pixels.
            duration_ms: Swipe duration.
        """
        if not self.screen_width:
            self.get_screen_size()

        cx = self.screen_width // 2
        cy = self.screen_height // 2

        if direction == "down":
            self.swipe(cx, cy + distance // 2, cx, cy - distance // 2, duration_ms)
        elif direction == "up":
            self.swipe(cx, cy - distance // 2, cx, cy + distance // 2, duration_ms)
        elif direction == "left":
            self.swipe(cx + distance // 2, cy, cx - distance // 2, cy, duration_ms)
        elif direction == "right":
            self.swipe(cx - distance // 2, cy, cx + distance // 2, cy, duration_ms)
        else:
            raise ADBError(f"Unknown scroll direction: {direction}")

    def wait(self, seconds: float) -> None:
        """Wait for specified seconds."""
        time.sleep(seconds)
