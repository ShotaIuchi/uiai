"""Hide secret values in everything that is written or sent (results, reports, events, webhooks)."""

from __future__ import annotations

from typing import Any

MASK = "****"


class Redactor:
    def __init__(self, secrets: list[str] | None = None):
        self.secrets: list[str] = []
        self.add(secrets or [])

    def add(self, secrets: list[str]) -> None:
        self.secrets = sorted({*self.secrets, *(s for s in secrets if s)}, key=len, reverse=True)

    def text(self, s: str) -> str:
        for sec in self.secrets:
            s = s.replace(sec, MASK)
        return s

    def __call__(self, obj: Any) -> Any:
        if not self.secrets:
            return obj
        if isinstance(obj, str):
            return self.text(obj)
        if isinstance(obj, dict):
            return {k: self(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self(v) for v in obj]
        return obj


def traceback_to_stderr(redactor: Redactor) -> None:
    """The traceback of the exception being handled, secrets hidden. For diagnosis: a result records an
    unexpected error as one line, which does not say where it happened."""
    import sys
    import traceback

    sys.stderr.write(redactor.text(traceback.format_exc()))
    sys.stderr.flush()
