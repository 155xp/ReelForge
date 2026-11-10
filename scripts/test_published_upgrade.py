"""Native macOS upgrade acceptance using the actual latest public download.

Run after package.py on each Mac architecture, before installing AgentCut:
  python scripts/test_published_upgrade.py --candidate-dir dist --prepared-tools ~/ReelForge

The installed release's own updater downloads the candidate from a local HTTP
server and performs its normal checksum/copy/dependency/regeneration steps. All
channel data belongs to a disposable installation. System shortcuts/jobs are
suppressed; the application, updater, Python dependencies, Bun and Blender are
real. Node/npm/HyperFrames commands fail and are recorded if anything calls them.
"""
from __future__ import annotations

import argparse
import functools
import fcntl
import hashlib
import http.server
import json
import os
import platform
import pty
import re
import select
import shlex
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import termios
import time
import tomllib
import zipfile
from pathlib import Path


def run(args, root, env, *, code=None, timeout=900):
    command = [str(a) for a in args]
    print("+", shlex.join(command if code is None else command[:2] + ["<acceptance probe>"]), flush=True)
    return subprocess.run(command, cwd=root, env=env, input=code, text=True,
                          check=True, timeout=timeout, capture_output=False)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fetch(url, path):
    # curl uses the runner's native certificate store and inherited proxy settings.
    subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--max-time", "180",
                    "--silent", "--show-error", "--output", str(path), url], check=True)


def verify(archive, sums):
    expected = next((line.split()[0] for line in sums.read_text().splitlines()
                     if line.split() and line.split()[-1].lstrip("*") == archive.name), None)
    assert expected and expected == digest(archive), f"Invalid checksum for {archive.name}"
    return expected


def extract(archive, target):
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            assert (target / info.filename).resolve().is_relative_to(target.resolve()), info.filename
        z.extractall(target)
        for info in z.infolist():
            path = target / info.filename
            if path.is_file() and (info.external_attr >> 16) & 0o111:
                path.chmod(0o755)
    roots = list(target.iterdir())
    assert len(roots) == 1 and (roots[0] / "studio/update.py").is_file()
    return roots[0]


def snapshot(root):
    """Byte-preserve data; allow generated instructions and settings metadata to change."""
    exact = {}
    for pattern in ("episodes/**/*", "completed videos/**/*", "research/**/*", "my-studio/**/*",
                    "dashboard/data/**/*", "profiles/**/*"):
        for p in root.glob(pattern):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            if "__pycache__" in p.relative_to(root).parts:
                continue
            if "my-studio" in p.parts and (p.name in {"studio.toml", "answers.json"}
                                          or "backups" in p.parts):
                continue
            if p.name in {"AGENTS.md", "CLAUDE.md", "config.toml", "updated.json", "last-opened.txt"}:
                continue
            if "windows" in p.parts or p.name.endswith(("-wal", "-shm")):
                continue
            exact[rel] = digest(p)
    settings = {}
    for prefix in (Path(), Path("profiles/second-channel")):
        for file in ("my-studio/answers.json", "my-studio/studio.toml", "dashboard/config.toml"):
            p = root / prefix / file
            value = json.loads(p.read_text()) if p.suffix == ".json" else tomllib.loads(p.read_text())
            if file.endswith("studio.toml"):
                value.pop("studio", None)
            settings[(prefix / file).as_posix()] = value
    return exact, settings


def contains(before, after, where=""):
    if isinstance(before, dict):
        assert isinstance(after, dict), where
        for key, value in before.items():
            assert key in after, f"Lost setting {where}.{key}"
            contains(value, after[key], f"{where}.{key}")
    else:
        assert before == after, f"Changed setting {where}: {before!r} -> {after!r}"


SEED = r'''
import json, shutil, sqlite3, subprocess
from pathlib import Path
from studio import dashboard_config, generate, profiles, tools
from dashboard import db
root = Path.cwd()
for profile, name in ((profiles.main(), 'First channel'), (profiles.create('Second channel'), 'Second channel')):
    generate.write_all({'channel_name':name, 'about':'Disposable native upgrade fixture.',
                        'assistant':['codex'], 'background_stats':False,
                        'handle_tiktok':'@upgrade_fixture', 'handle_youtube':'@upgrade_fixture'}, profile)
    (profile.my_studio / 'user-notes.md').write_text('My handwritten channel notes must stay byte-for-byte.\n')
    profile.bible.write_text(profile.bible.read_text() + '\nCustom research notes and source credits: preserve exactly.\n')
    profile.config.write_text(dashboard_config.set_keys(profile.config.read_text(), {'':{'refresh_minutes':0}}))
    # These documented hand edits deliberately differ from the saved onboarding
    # answers. The actual old updater must not overwrite them during regeneration.
    profile.settings.write_text(profile.settings.read_text().replace('target_lufs = -25.5', 'target_lufs = -24.0'))
    profile.config.write_text(dashboard_config.set_keys(profile.config.read_text(), {'youtube':{'handle':'@hand_edited_account'}}))
    data = profile.data
    db.init(profile.db)
    with db.connect() as con:
        con.execute("INSERT INTO account_stats(platform,ts,handle,followers,views,likes,posts) VALUES(?,?,?,?,?,?,?)",
                    ('tiktok','2026-01-01T00:00:00+00:00','@upgrade_fixture',123,4567,89,2))
        con.execute("INSERT INTO meta(key,value) VALUES('upgrade_fixture','preserve me')")
    cookie = data / 'browser' / 'Default' / 'Cookies'
    cookie.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(cookie) as con:
        con.execute('CREATE TABLE fixture_account(host TEXT, value TEXT)')
        con.execute('INSERT INTO fixture_account VALUES(?,?)', ('fixture.invalid','synthetic-login-preserved'))
    (data / 'account-state.json').write_text(json.dumps({'connected':['tiktok','youtube']}))
    source = profile.folder / 'research' / 'Source footage with spaces.mp4'
    source.parent.mkdir(exist_ok=True)
    subprocess.run([str(tools.find_ffmpeg()), '-hide_banner','-loglevel','error','-y',
                    '-f','lavfi','-i','color=c=blue:s=108x192:r=30:d=1',
                    '-f','lavfi','-i','sine=frequency=440:duration=1',
                    '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
    dest = profile.completed / 'ep01_existing - Existing video'
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest / 'ep01_existing.mp4')
    (dest / 'caption.txt').write_text('My existing finished video #fixture\n')
print('Seeded actual released application with two channels, accounts, SQLite statistics and real media.')
'''


SMOKE = r'''
import io, json, os
from pathlib import Path
from studio import profiles, settings, ui
from studio.bridge import Loop
from dashboard import db, videos
from dashboard.service import Dashboard
assert not (Path('tools') / 'agentcut').exists()
assert ui.packages_ready() and ui.bun_path(), 'The existing window must remain ready'
for p in profiles.every():
    s = settings.load(p.settings)
    assert s['video'].get('backend','blender') == 'blender', (p.name,s['video'])
    answers = json.loads(p.answers.read_text())
    assert answers.get('backend','blender') == 'blender'
    db.init(p.db)
    with db.connect() as con:
        assert con.execute("SELECT value FROM meta WHERE key='upgrade_fixture'").fetchone()[0] == 'preserve me'
        assert con.execute('SELECT followers,views FROM account_stats').fetchone()[:] == (123,4567)
svc = Dashboard(Loop(io.StringIO()))
view = svc.start({'tab':'publish'})
assert view['tab'] == 'publish' and view['profile']['name'] == 'First channel'
assert any(p.name == 'ep01_existing.mp4' for p in videos.find(svc.cfg)), 'Existing video missing from Publish'
svc.stop()
print('Real dashboard service opens Publish, profiles remain Blender, accounts/statistics/video are present.')
'''


def blender_smoke(root, py, env, phase):
    episode = root / "episodes/ep01_existing_blender"
    if not episode.exists():
        run([py, "-m", "studio", "new-episode", "existing_blender"], root, env)
        episode = next(root.glob("episodes/ep*_existing_blender"))
    spec = json.loads((episode / "episode.json").read_text())
    assert spec.get("backend", "blender") == "blender"
    run([py, "pipeline/make_episode.py", episode, "--steps", "build"], root, env)
    # Hosted Intel Macs have no Metal. Cycles CPU renders the real pipeline-built
    # scene on both architectures; this is a required render, never continue-on-error.
    code = r'''
import subprocess, sys
from pathlib import Path
from studio import tools
ep = Path(sys.argv[1]); phase = sys.argv[2]
expr = "import bpy; s=bpy.context.scene; s.render.engine='CYCLES'; s.cycles.device='CPU'; s.cycles.samples=1; s.render.resolution_percentage=10; s.render.image_settings.file_format='PNG'; s.render.filepath=" + repr(str(ep/'build'/('upgrade-'+phase+'.png'))) + "; s.frame_set(31); bpy.ops.render.render(write_still=True)"
subprocess.run([str(tools.find_blender()),'-b',str(ep/'build/scene.blend'),'--python-exit-code','1','--python-expr',expr],check=True)
from PIL import Image
p=ep/'build'/('upgrade-'+phase+'.png')
with Image.open(p) as image:
    assert image.size == (108,192), image.size
    assert max(hi-lo for lo,hi in image.convert('RGB').getextrema()) > 20, 'Empty Blender render'
print('Native CPU Blender scene render passed:', p)
'''
    run([py, "-", episode, phase], root, env, code=code)
    return episode


def window_smoke(root, py, env, phase):
    """Open the real Bun/OpenTUI window in a terminal, see Publish, then close it."""
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 42, 132, 0, 0))
    proc = subprocess.Popen([str(py), "-m", "studio", "publish"], cwd=root,
                            env={**env, "TERM": "xterm-256color", "COLUMNS": "132", "LINES": "42"},
                            stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    os.close(slave)
    output = bytearray()
    opened = False
    deadline = time.monotonic() + 45
    try:
        while time.monotonic() < deadline and proc.poll() is None:
            if select.select([master], [], [], 0.2)[0]:
                try:
                    output.extend(os.read(master, 65536))
                except OSError:
                    break
                text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output.decode("utf-8", "replace"))
                if not opened and "Publish" in text and "ep01_existing.mp4" in text:
                    opened = True
                    os.write(master, b"\x03")  # the app's normal Ctrl-C close command
        assert opened, "The real window did not show the existing Publish video:\n" + output.decode("utf-8", "replace")[-4000:]
        assert proc.wait(timeout=15) == 0, "The real application did not close normally"
        print(f"Real native window opened and closed on Publish ({phase}), without optional software.")
    finally:
        if proc.poll() is None:
            import signal
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        os.close(master)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate-dir", required=True, type=Path)
    ap.add_argument("--prepared-tools", type=Path, help="copy only ordinary tools/sounds from a setup installation")
    ap.add_argument("--report", type=Path, default=Path("published-upgrade-result.json"))
    args = ap.parse_args()
    assert sys.platform == "darwin", "This acceptance test requires real native macOS"
    assert platform.machine() in {"arm64", "x86_64"}, platform.machine()
    candidates = list(args.candidate_dir.resolve().glob("ReelForge-*-macOS.zip"))
    assert len(candidates) == 1, "Build exactly one candidate Mac package first"
    candidate = candidates[0]
    candidate_sha = verify(candidate, candidate.parent / "SHA256SUMS.txt")
    version = re.fullmatch(r"ReelForge-(.+)-macOS.zip", candidate.name).group(1)
    result = {"platform": platform.platform(), "architecture": platform.machine(),
              "candidate": candidate.name, "candidate_sha256": candidate_sha, "pass": False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="ReelForge native upgrade with spaces ") as tmp:
            work = Path(tmp)
            fetch("https://api.github.com/repos/dan2756/ReelForge/releases/latest", work / "latest.json")
            release = json.loads((work / "latest.json").read_text())
            assert not release["draft"] and not release["prerelease"]
            assets = {a["name"]: a for a in release["assets"]}
            name = f"ReelForge-{release['tag_name'].lstrip('v')}-macOS.zip"
            archive = work / name
            fetch(assets[name]["browser_download_url"], archive)
            fetch(assets["SHA256SUMS.txt"]["browser_download_url"], work / "SHA256SUMS.txt")
            result.update(baseline=release["tag_name"], baseline_url=release["html_url"],
                          baseline_sha256=verify(archive, work / "SHA256SUMS.txt"))
            print(json.dumps(result, indent=2), flush=True)
            root = extract(archive, work / "installed")
            guard = work / "unavailable optional executables"
            guard.mkdir()
            forbidden = work / "unexpected optional command.log"
            for exe in ("node", "npm", "npx", "hyperframes"):
                p = guard / exe
                p.write_text(f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(exe)} >> {shlex.quote(str(forbidden))}\nexit 127\n")
                p.chmod(0o755)
            env = {**os.environ, "PATH": str(guard) + os.pathsep + os.environ["PATH"],
                   "STUDIO_DRY_SYSTEM": "1", "PYTHONUTF8": "1"}
            for key in ("REELFORGE_PROFILE", "REELFORGE_BUN", "REELFORGE_ROOT", "REELFORGE_PYTHON",
                        "STUDIO_BLENDER", "STUDIO_FFMPEG"):
                env.pop(key, None)
            if args.prepared_tools:
                prepared = args.prepared_tools.expanduser().resolve()
                for relative in ("tools", "assets/sfx/mixkit", "assets/sfx/_cache"):
                    source = prepared / relative
                    if source.is_dir():
                        shutil.copytree(source, root / relative, dirs_exist_ok=True, symlinks=True,
                                        ignore=shutil.ignore_patterns("agentcut", "agentcut-*", ".agentcut-*", "downloads"))
            run(["bash", "setup.sh", "--yes", "--no-onboard"], root, env, timeout=1800)
            py = root / ".venv/bin/python"
            run([py, "-"], root, env, code=SEED)
            episode = blender_smoke(root, py, env, "before")
            run([py, "-"], root, env, code=SMOKE)
            window_smoke(root, py, env, "before")
            before, settings_before = snapshot(root)
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(
                http.server.SimpleHTTPRequestHandler, directory=str(candidate.parent)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}/"
                code = '''import sys
from studio import update
version, base = sys.argv[1:]
name = update.asset_name(version)
release = update.Release(version, 'v'+version, assets={name:(base+name,0),'SHA256SUMS.txt':(base+'SHA256SUMS.txt',0)})
print(update.apply(release))
'''
                run([py, "-", version, base], root, env, code=code)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
            after, settings_after = snapshot(root)
            for file, sha in before.items():
                assert after.get(file) == sha, f"Upgrade changed or lost user data: {file}"
            for file, values in settings_before.items():
                contains(values, settings_after[file], file)
            marker = json.loads((root / "dashboard/data/updated.json").read_text())
            assert marker["from"] == release["tag_name"].lstrip("v") and marker["to"] == version, marker
            for path in ("setup.sh", "bin/reelforge", "Open ReelForge.command"):
                assert os.access(root / path, os.X_OK), f"Upgrade lost launcher permission: {path}"
            run([py, "-m", "studio", "doctor"], root, env)
            run([py, "-"], root, env, code=SMOKE)
            window_smoke(root, py, env, "after")
            blender_smoke(root, py, env, "after")
            run([py, "-m", "studio", "new-episode", "after_upgrade"], root, env)
            created = next(root.glob("episodes/ep*_after_upgrade/episode.json"))
            assert json.loads(created.read_text())["backend"] == "blender"
            if forbidden.exists():
                raise AssertionError("Opening/updating/Blender invoked optional software: " + forbidden.read_text())
            assert not (root / "tools/agentcut").exists()
            result.update(pass_=True, preserved_files=len(before),
                          checks=["released-package checksum", "released-code setup", "two profiles and settings",
                                  "accounts and browser data", "SQLite statistics", "source footage and finished video",
                                  "actual old updater and candidate checksum", "native window and dashboard Publish service",
                                  "Blender scene build and native CPU render before/after", "no optional commands"])
            result["pass"] = result.pop("pass_")
    finally:
        args.report.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
