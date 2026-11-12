"""AI backends. Phase 1: Claude Code (`claude -p`). Phase 4: Anthropic API (optional)."""

from __future__ import annotations


class AIError(Exception):
    """The AI backend is not usable (CLI missing, not logged in, crashed, timed out)."""
