"""Read every platform's stats once, save them, and exit, without opening a window.

This is what ReelForge's hourly background job runs (reelforge stats on), so your charts keep filling in and the
bell has news for you while ReelForge is closed. Each run adds a line to data/refresh.log.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # the ReelForge folder: the dashboard and studio packages live here
sys.path.insert(0, str(ROOT))

from dashboard.__main__ import main  # noqa: E402

try:
    main(["refresh"])
except SystemExit:
    pass
