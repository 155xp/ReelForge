"""The reelforge command's entry point. bin/reelforge.cmd (Windows), bin/reelforge (macOS/Linux), ReelForge.bat
and the shortcuts all run this with ReelForge's own Python (.venv). `reelforge help` lists what it can do."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.__main__ import main  # noqa: E402

sys.exit(main())
