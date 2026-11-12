# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml==6.0.3",
#   "pillow==13.0.0",
#   "playwright==1.65.1",
# ]
# ///
"""uiai engine entry point.

Run with uv (the only prerequisite; it also provides Python):

    uv run --script engine/main.py run path/to/scenario.yaml
    uv run --script engine/main.py check sample/
    uv run --script engine/main.py setup
    uv run --script engine/main.py watch --run latest

Dependency versions are pinned on purpose: the Chromium build fetched by
`uiai setup` must match the Playwright version.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from uiai.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
