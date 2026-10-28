"""The read-only JSON profile listing, through the command entry point."""

import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from studio import generate, profiles, reset, settings
from studio.__main__ import main

from test_profiles import ANSWERS, KIT, Scratch


class ProfilesJSON(Scratch):
    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.stat().st_mode, p.stat().st_mtime_ns,
                                               p.read_bytes() if p.is_file() else None)
                for p in [self.root, *self.root.rglob("*")]}

    def run_json(self, argv=None, code=0):
        before, env = self.snapshot(), dict(os.environ)
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            self.assertEqual(main(argv if argv is not None else ["profiles", "--json"]), code)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(dict(os.environ), env)
        if code:
            return out.getvalue(), err.getvalue()
        self.assertEqual(err.getvalue(), "")
        return json.loads(out.getvalue())

    def test_first_profile_before_onboarding_creates_no_files(self):
        self.assertEqual(self.run_json(), {
            "current": ".", "profiles": [
                {"key": ".", "name": "My channel", "folder": str(self.root), "main": True,
                 "onboarded": False, "platforms": list(settings.PLATFORMS)}
            ]})
        self.assertFalse(profiles.FOLDER.exists())
        self.assertFalse(profiles.main().config.exists())

    def test_lists_metadata_unicode_names_and_enabled_platform_keys(self):
        self.onboard_main(channel_name="Nuit étoilée 🌙")
        extra = profiles.create("世界の科学 🔬")
        with redirect_stdout(io.StringIO()):
            generate.write_all({**ANSWERS, "channel_name": extra.name, "platforms": ["instagram", "x"]}, extra)
        self.assertEqual(self.run_json(), {
            "current": ".", "profiles": [
                {"key": ".", "name": "Nuit étoilée 🌙", "folder": str(self.root), "main": True,
                 "onboarded": True, "platforms": ["tiktok", "youtube"]},
                {"key": extra.key, "name": "世界の科学 🔬", "folder": str(extra.folder), "main": False,
                 "onboarded": True, "platforms": ["instagram", "x"]}
            ]})

    def test_remembered_profile_is_selected_without_switching_this_process(self):
        extra = profiles.create("Cool Epic Facts")
        profiles.remember(extra)
        self.assertEqual(self.run_json()["current"], extra.key)
        self.assertEqual(profiles.current(), profiles.main())
        self.assertEqual(profiles.last(), extra)

    def test_explicit_profile_overrides_environment_and_remembered_selection(self):
        extra = profiles.create("Cool Epic Facts")
        profiles.remember(extra)
        profiles.use(profiles.main())
        for argv, want in ((["-p", "Cool", "profiles", "--json"], extra.key),
                           (["profiles", "-p", "2", "--json"], extra.key),
                           (["profiles", "--json", "--profile", extra.key], extra.key),
                           (["--profile=cool-epic-facts", "profiles", "--json"], extra.key),
                           (["profiles", "--json", "-p", "1"], ".")):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_json(argv)["current"], want)
                self.assertEqual(profiles.current(), profiles.main())
                self.assertEqual(profiles.last(), extra)

    def test_environment_selection_takes_precedence_over_remembered_profile(self):
        extra = profiles.create("Cool Epic Facts")
        profiles.remember(extra)
        profiles.use(profiles.main())
        self.assertEqual(self.run_json()["current"], ".")
        profiles.remember(profiles.main())
        profiles.use(extra)
        self.assertEqual(self.run_json()["current"], extra.key)

    def test_missing_environment_or_remembered_profile_uses_existing_fallbacks(self):
        extra = profiles.create("Cool Epic Facts")
        profiles.remember(extra)
        os.environ[profiles.ENV] = "profiles/no-such-profile"
        self.assertEqual(self.run_json()["current"], extra.key)
        (profiles.FOLDER / profiles.LAST).write_text("profiles/no-such-profile\n", encoding="utf-8")
        self.assertEqual(self.run_json()["current"], ".")

    def test_listing_leaves_pending_actions_and_launcher_permissions_alone(self):
        pending = self.root / ".reelforge-pending.json"
        pending.write_text('{"do": "reset"}', encoding="utf-8")
        os.utime(pending, (0, 0))  # a regression can consume this request, but cannot perform a reset
        launcher = self.root / "setup.sh"
        launcher.write_text("#!/bin/sh\n", encoding="utf-8")
        launcher.chmod(0o644)
        with mock.patch.object(reset, "PENDING", pending):
            self.assertEqual(self.run_json()["current"], ".")

    def test_only_metadata_is_emitted_even_when_settings_and_logins_contain_secrets(self):
        self.onboard_main()
        p = profiles.main()
        with p.settings.open("a", encoding="utf-8") as f:
            f.write('\n[private]\ntoken = "studio-secret"\n')
        with p.config.open("a", encoding="utf-8") as f:
            f.write('\n[private]\ncookie = "config-secret"\n')
        p.data.mkdir(parents=True, exist_ok=True)
        (p.data / "tokens.json").write_text('{"browser:instagram": {"token": "login-secret"}}', encoding="utf-8")
        data = self.run_json()
        self.assertEqual(set(data), {"current", "profiles"})
        self.assertEqual(set(data["profiles"][0]), {"key", "name", "folder", "main", "onboarded", "platforms"})
        text = json.dumps(data)
        for secret in ("studio-secret", "config-secret", "login-secret", "@nightphysics"):
            self.assertNotIn(secret, text)

    def test_json_rejects_mutating_subcommands_and_extra_arguments(self):
        extra = profiles.create("Cool Epic Facts")
        gone = profiles.delete(profiles.create("Deleted channel"))
        commands = (["new"], ["add"], ["delete", extra.name, "--yes"], ["remove", extra.name, "--yes"],
                    ["restore", gone.name], ["restore"], ["unknown"], ["--json"])
        for command in commands:
            for args in (["--json", *command], [*command, "--json"]):
                with self.subTest(args=args):
                    out, err = self.run_json(["profiles", *args], code=2)
                    self.assertEqual(out, "")
                    self.assertIn("usage: reelforge profiles", err)
                    self.assertIn("--json only works with the profile listing", err)

    def test_unknown_explicit_profile_is_rejected_without_changing_selection(self):
        profiles.remember(profiles.create("Cool Epic Facts"))
        out, _ = self.run_json(["profiles", "--json", "-p", "nope"], code=2)
        self.assertIn("There's no profile called 'nope'", out)

    def test_default_text_listing_is_unchanged(self):
        profiles.remember(profiles.create("Cool Epic Facts"))
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["profiles"]), 0)
        self.assertEqual(out.getvalue(),
                         "Your profiles (one for each channel):\n"
                         f"    1. {'My channel':<28} the ReelForge folder\n"
                         f"  * 2. {'Cool Epic Facts':<28} profiles{os.sep}cool-epic-facts\n"
                         "\nreelforge -p NAME opens one (the name, the start of it, or its number); "
                         "reelforge profiles new adds one.\n")

    def test_help_mentions_json_listing(self):
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["help"]), 0)
        self.assertIn("reelforge profiles --json", out.getvalue())

    def test_module_entry_point_emits_one_json_object(self):
        extra = profiles.create("世界の科学 🔬")
        profiles.remember(extra)
        script = ("import runpy\n"
                  "from pathlib import Path\n"
                  "from studio import paths, profiles\n"
                  f"paths.ROOT = profiles.ROOT = Path({str(self.root)!r})\n"
                  "profiles.FOLDER = profiles.ROOT / 'profiles'\n"
                  "runpy.run_module('studio', run_name='__main__')\n")
        before, env = self.snapshot(), dict(os.environ)
        result = subprocess.run([sys.executable, "-c", script, "profiles", "--json"], cwd=KIT,
                                capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout)["current"], extra.key)
        self.assertEqual(self.snapshot(), before)
