# Third-party material

| What | Licence | In the download? |
|---|---|---|
| Sound effects by **Kenney** (`assets/sfx/kenney/`, Impact Sounds and Sci-fi Sounds packs) | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (public domain); `License.txt` in each pack | Yes |
| Sound effects from **Mixkit** (listed in `assets/sfx/manifest.json`) | [Mixkit Sound Effects Free License](https://mixkit.co/license/#sfxFree): free for commercial and personal projects, including YouTube and social media, no attribution required; the files may not be redistributed as they are | **No.** Setup downloads them from Mixkit on your computer after you accept the licence |
| Sounds in `assets/sfx/generated/` | Synthesized by the kit (`pipeline/post/sfx_generate.py`) | Yes |
| **JetBrains Mono** font (`assets/fonts/`, used on macOS and Linux) | [SIL Open Font License 1.1](assets/fonts/JetBrainsMono-OFL.txt) | Yes |
| Georgia and Consolas fonts (Windows) | Microsoft's licence, part of Windows | No: used from your Windows fonts folder |
| **Blender** 4.5 LTS | [GPL](https://www.blender.org/about/license/); what you make with it is yours | No: setup downloads it from download.blender.org (checksum verified) |
| **ffmpeg** (builds by gyan.dev for Windows, Martin Riedl for macOS, BtbN for Linux) | [GPL](https://ffmpeg.org/legal.html) | No: setup downloads it from gyan.dev, ffmpeg.martin-riedl.de or BtbN's GitHub releases (checksum verified), or use your own |
| **Python** (macOS and Linux, only without Python 3.11+) | [PSF licence](https://docs.python.org/3/license.html) | No: setup downloads it from the python-build-standalone releases on GitHub (checksum verified) into `tools/python` |
| **Chromium** (macOS and Linux, only without Chrome or Edge) | [BSD and others](https://www.chromium.org/chromium-projects/) | No: Playwright downloads it into its own cache folder |
| Python packages: numpy, Pillow, Jinja2, httpx, Playwright, certifi, truststore | Their own open-source licences (BSD, MIT-CMU, MIT, Apache 2.0, MPL 2.0) | No: installed by pip from PyPI |
| **Bun** (runs ReelForge's window) | [MIT and others](https://bun.com/docs/project/licensing) | No: setup downloads it from Bun's GitHub releases (checksum verified) into `tools/bun` |
| **OpenTUI** (`@opentui/core`, `@opentui/react`) and **React**, the window's packages | [MIT](https://github.com/anomalyco/opentui/blob/main/LICENSE) | No: installed by Bun from npm into `ui/node_modules`, exactly the versions in `ui/bun.lock` |

The videos you make are yours. The kit never uploads anything; you post by hand from ReelForge.
