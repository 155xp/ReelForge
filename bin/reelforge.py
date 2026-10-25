"""The reelforge command's entry point. bin/reelforge.cmd (Windows), bin/reelforge (macOS/Linux), ReelForge.bat
and the shortcuts all run this with ReelForge's own Python (.venv). `reelforge help` lists what it can do.

First it checks that ReelForge's Python packages are all there. A setup that stopped part way (its window closed
while it was making .venv, say) leaves some out: then it exits with code 3, and the launchers run setup to repair
.venv instead of ReelForge crashing on its first import."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPAIR = 3  # the exit code that asks the launchers to run setup
# requirements.txt's packages by the names Python imports them as, and rich, which the first-run screens import
# directly (tests/test_studio.py keeps this in step with requirements.txt)
PACKAGES = ("numpy", "PIL", "jinja2", "textual", "rich", "httpx", "playwright", "certifi", "truststore")


def missing() -> list[str]:
    """The packages this Python can't find."""
    return [name for name in PACKAGES if importlib.util.find_spec(name) is None]


if __name__ == "__main__":
    if gone := missing():
        print(f"ReelForge's Python packages aren't all installed ({', '.join(gone)} missing): the last setup "
              "probably stopped part way.")
        sys.exit(REPAIR)
    sys.path.insert(0, str(ROOT))
    from studio.__main__ import main

    sys.exit(main())
