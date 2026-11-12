"""Claude Code backend: one persistent `claude -p` process per session (stream-json in/out).

Runs with the user's Claude Code login locally; CI needs ANTHROPIC_API_KEY or a long-lived token
(design doc 6.4). Tools, MCP servers, slash commands and user settings are disabled.
"""

from __future__ import annotations

import base64
import json
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from . import AIError


class ClaudeCodeSession:
    backend = "claude-code"

    def __init__(self, model: str, system: str, timeout: float = 120.0):
        exe = shutil.which("claude")  # resolves claude.exe / claude.cmd on Windows via PATHEXT
        if not exe:
            raise AIError("claude（Claude Code CLI）が見つからない")
        self.model = model
        self.timeout = timeout
        self.workdir = Path(tempfile.mkdtemp(prefix="uiai-ai-"))
        sp = self.workdir / "system-prompt.txt"
        sp.write_text(system, encoding="utf-8")
        self._stderr = open(self.workdir / "stderr.log", "w+", encoding="utf-8")
        cmd = [
            exe, "-p",
            "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--model", model,
            "--tools", "",
            "--system-prompt-file", str(sp),
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--setting-sources", "project",
        ]
        try:
            self.p = subprocess.Popen(cmd, cwd=self.workdir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=self._stderr, text=True, encoding="utf-8", errors="replace",
                                      bufsize=1)
        except OSError as e:
            raise AIError(f"claude を起動できない: {e}") from e
        self._q: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self._api_ms_total = 0  # duration_api_ms in result events is cumulative per session

    def _read(self) -> None:
        assert self.p.stdout
        for line in self.p.stdout:
            self._q.put(line)
        self._q.put(None)

    def _stderr_tail(self) -> str:
        try:
            self._stderr.flush()
            self._stderr.seek(0)
            return self._stderr.read()[-500:].strip()
        except (OSError, ValueError):
            return ""

    def ask(self, text: str, image: bytes | None = None) -> tuple[str, dict]:
        content: list[dict] = []
        if image is not None:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                         "data": base64.b64encode(image).decode()}})
        content.append({"type": "text", "text": text})
        msg = {"type": "user", "message": {"role": "user", "content": content}}
        start = time.time()
        try:
            assert self.p.stdin
            self.p.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.p.stdin.flush()
        except (OSError, ValueError) as e:
            raise AIError(f"claude が終了している: {self._stderr_tail() or e}") from e
        reply = ""
        while True:
            left = self.timeout - (time.time() - start)
            try:
                line = self._q.get(timeout=max(0.1, left))
            except queue.Empty:
                raise AIError(f"claude の応答が {self.timeout:.0f} 秒以内に返らない") from None
            if line is None:
                raise AIError(f"claude が終了した: {self._stderr_tail() or '(stderr なし)'}")
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "assistant":
                for c in ev.get("message", {}).get("content", []):
                    if c.get("type") == "text":
                        reply += c["text"]
            elif ev.get("type") == "result":
                if ev.get("is_error") or str(ev.get("subtype", "")).startswith("error"):
                    raise AIError(f"claude がエラーを返した: {str(ev.get('result') or ev.get('subtype'))[:300]}")
                usage = ev.get("usage", {})
                api_total = ev.get("duration_api_ms", 0) or 0
                api_delta, self._api_ms_total = api_total - self._api_ms_total, api_total
                return (reply or ev.get("result", "")), {
                    "wall_s": round(time.time() - start, 2),
                    "api_s": round(api_delta / 1000, 2),
                    "in_tokens": usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0),
                    "out_tokens": usage.get("output_tokens", 0),
                }

    def close(self) -> None:
        try:
            if self.p.stdin:
                self.p.stdin.close()
            self.p.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            self.p.kill()
        finally:
            self._stderr.close()
            shutil.rmtree(self.workdir, ignore_errors=True)
