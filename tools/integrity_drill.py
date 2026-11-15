"""CLI entry point for the local integrity, backup and migration drill."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mission_control.integrity_drill import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
