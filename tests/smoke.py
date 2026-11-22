#!/usr/bin/env python3
"""Offline smoke checks. All generated installs use temporary homes."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, env=None, input=None, ok=True):
    result = subprocess.run([str(a) for a in args], text=True, input=input, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if ok and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result


class Smoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jkstack-smoke-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1")

    def setup(self, *args, ok=True):
        return run(sys.executable, ROOT / "setup", *args, env=self.env, ok=ok)

    def init(self):
        work = self.base / "work"
        run(sys.executable, ROOT / "skills/live-timeline/scripts/init.py", work,
            "--owner", "Owner", "--lanes", "main:Main lane", "--tz", "UTC", env=self.env)
        return work

    def test_setup_dry_run_and_both(self):
        self.setup("--both", "--dry-run")
        self.assertEqual(list(self.home.iterdir()), [])
        self.setup("--both")
        for harness in (".claude", ".agents"):
            for source in (ROOT / "skills").iterdir():
                target = self.home / harness / "skills" / source.name
                self.assertTrue(target.is_symlink())
                self.assertEqual(target.resolve(), source.resolve())
        for harness in (".claude", ".agents"):
            for blueprint in (ROOT / "blueprints").iterdir():
                self.assertFalse(os.path.lexists(self.home / harness / "skills" / blueprint.name))
        result = self.setup("--both")
        self.assertIn("already linked", result.stdout)
        self.assertNotIn("\nlink:", result.stdout)

    def test_setup_individual_targets(self):
        self.setup("--codex")
        self.assertFalse((self.home / ".claude").exists())
        self.assertTrue((self.home / ".agents/skills/live-timeline").is_symlink())

    def test_setup_conflicts_are_preflighted(self):
        folder = self.home / ".agents/skills"
        folder.mkdir(parents=True)
        target = folder / "live-timeline"
        for kind in ("dir", "file", "symlink"):
            if kind == "dir":
                target.mkdir()
            elif kind == "file":
                target.write_text("preserve")
            else:
                target.symlink_to(self.base / "absent")
            result = self.setup("--both", ok=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((self.home / ".claude").exists())
            self.assertEqual(list(folder.iterdir()), [target])
            target.rmdir() if kind == "dir" else target.unlink()

    def test_setup_refuses_symlink_parent(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.home / ".claude").symlink_to(outside)
        self.assertNotEqual(self.setup("--both", ok=False).returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.home / ".agents").exists())

    def test_timeline_patch_and_privacy_rejection(self):
        work = self.init()
        feed = work / "live/events.json"
        patch = {"events": [{"ref": "check", "lane": "main", "kind": "success", "importance": 2,
                             "title": "Batch check passes", "summary": "All three rows match.",
                             "images": [{"path": "live/thumbs/check.png", "caption": "Synthetic check",
                                         "full": "assets/check.png"}]}],
                 "headline": {"best": {"text": "Three rows match", "eventId": "@check"}}}
        result = run(sys.executable, work / "live/patch.py", input=json.dumps(patch), env=self.env)
        self.assertEqual(json.loads(result.stdout)["new"], ["e002"])
        run(sys.executable, work / "live/validate.py", env=self.env)
        before = feed.read_bytes()
        for value in ("../private.png", "https://example.com/tracker.png", "private/a.png",
                      "live/%2e%2e/a.png", "live/../a.png", "\\\\host/a.png", "./PRIVATE/a.png"):
            patch["events"][0]["images"][0]["path"] = value
            result = run(sys.executable, work / "live/patch.py", input=json.dumps(patch), env=self.env, ok=False)
            self.assertNotEqual(result.returncode, 0, value)
            self.assertEqual(feed.read_bytes(), before)
        patch["events"][0]["images"][0]["path"] = "live/thumbs/check.png"
        patch["events"][0]["kind"] = "sealed"
        result = run(sys.executable, work / "live/patch.py", input=json.dumps(patch), env=self.env, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(feed.read_bytes(), before)
        result = run(sys.executable, work / "live/brief.py", "--since", "all", env=self.env)
        self.assertIn("Batch check passes", result.stdout)
        run(sys.executable, ROOT / "skills/live-timeline/scripts/init.py", work, "--upgrade", env=self.env)
        self.assertEqual(feed.read_bytes(), before)

    def test_collector_excludes_private_sources(self):
        work = self.init()
        (work / "STATUS.md").write_text("First batch passed.\n")
        (work / "private").mkdir()
        (work / "private/STATUS.md").write_text("Do not collect this sentence.\n")
        result = run(sys.executable, work / "live/collect.py", env=self.env)
        self.assertIn("First batch passed", result.stdout)
        self.assertNotIn("Do not collect", result.stdout)
        result = run(sys.executable, work / "live/collect.py", env=self.env)
        self.assertNotIn("SOURCE", result.stdout)

    def test_patch_dates_chapters_and_metrics_from_events(self):
        work = self.init()
        feed = work / "live/events.json"
        first = json.loads(feed.read_text())["chapters"][0]
        at = lambda h: (datetime.fromisoformat(first["start"]) + timedelta(hours=h)).isoformat(timespec="seconds")
        patch = {"chapters": [{"ref": "two", "title": "Second pass"}],
                 "events": [{"ref": "a", "time": at(2), "lane": "main", "kind": "start", "importance": 2, "state": "running",
                             "chapter": "@two", "title": "Second pass starts", "summary": "Rows re-checked."},
                            {"ref": "b", "time": at(1), "lane": "main", "kind": "success", "importance": 2,
                             "title": "First pass clean", "summary": "No errors.", "causedBy": ["@b"]}],
                 "metrics": [{"name": "Rows", "value": 12, "event": "@b"}]}
        run(sys.executable, work / "live/patch.py", input=json.dumps(patch), env=self.env)
        data = json.loads(feed.read_text())
        b = data["events"][-1]
        self.assertEqual(data["chapters"][-1]["start"], at(2))
        self.assertEqual(b["chapter"], first["id"])
        self.assertNotIn("causedBy", b)
        self.assertEqual((data["metrics"][-1]["time"], data["metrics"][-1]["lane"]), (at(1), "main"))

    def test_collector_keeps_tags_and_repeated_lines(self):
        work = self.init()
        config = work / "live/keeper/config.json"
        cfg = json.loads(config.read_text())
        cfg.update(sources=["LOG.md"])
        config.write_text(json.dumps(cfg))
        log = work / "LOG.md"
        log.write_text("- 00:01 (main) [result] " + "long " * 100 + "[img: shots/a.png | A] [metric: Rows = 12]\n- Same line.\n")
        first = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertIn("[img: shots/a.png | A]", first)
        self.assertIn("[metric: Rows = 12]", first)
        with log.open("a") as f:
            f.write("- Same line.\n")
        second = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertIn("Same line.", second)
        cfg.update(maxLinesPerSource=3)
        config.write_text(json.dumps(cfg))
        with log.open("a") as f:
            f.write("".join(f"- 00:0{i} (main) [result] Paged beat {i}.\n" for i in range(5)))
        paged = run(sys.executable, work / "live/collect.py", env=self.env).stdout + \
            run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertEqual([paged.count(f"Paged beat {i}.") for i in range(5)], [1] * 5)

    def test_collector_holds_overflow_and_lists_next(self):
        work = self.init()
        config = work / "live/keeper/config.json"
        cfg = json.loads(config.read_text())
        cfg.update(maxChars=200, sources=["LOG.md", "*/REPORT.md"])
        config.write_text(json.dumps(cfg))
        (work / "LOG.md").write_text("".join(f"- 00:0{i} (main) [result] Beat number {i} of the lead log.\n" for i in range(1, 7)))
        (work / "sol").mkdir()
        (work / "sol/REPORT.md").write_text("Sol found two risks.\n")
        first = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        second = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        third = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        for i in range(1, 7):
            self.assertEqual((first + second + third).count(f"Beat number {i} "), 1, i)
        self.assertIn("Sol found two risks", first + second + third)
        self.assertIn("HELD", first)
        self.assertIn("NEXT put all of this in one patch: LOG.md", first)
        self.assertNotIn("STATUS", first)
        cfg["statusStaleMin"] = 0
        config.write_text(json.dumps(cfg))
        stale = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertIn("NEXT send headline.status", stale)
        run(sys.executable, work / "live/patch.py", input='{"headline": {"status": {"tone": "warn", "text": "Slow"}}}', env=self.env)
        feed = json.loads((work / "live/events.json").read_text())
        self.assertIn("asOf", feed["headline"]["status"])
        self.assertIn("set ", run(sys.executable, work / "live/recent.py", env=self.env).stdout)

    def test_blueprint_links_and_brand_profiles(self):
        for skill in sorted((ROOT / "blueprints").iterdir()):
            for doc in [skill / "SKILL.md", *sorted((skill / "references").glob("*.md"))]:
                for target in re.findall(r"\]\(([^)#\s]+)", doc.read_text()):
                    if "://" not in target:
                        self.assertTrue((doc.parent / target).exists(), f"{skill.name}/{doc.name} -> {target}")
        for profile in (ROOT / "blueprints/demo-video/assets").glob("brand-*.json"):
            brand = json.loads(profile.read_text())
            self.assertTrue({"stage", "surface", "ink", "accent", "caption", "rail"} <= brand["colors"].keys())

    def test_transcript_preserves_distinct_lines(self):
        vtt = self.base / "input.vtt"
        vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nFirst line\nSecond line\n\n"
                       "00:00:02.000 --> 00:00:03.000\nSecond line\n<c>Third line</c>\n")
        out = self.base / "transcript.txt"
        run(sys.executable, ROOT / "skills/deep-yt-analysis/vtt-to-transcript.py", vtt, out, env=self.env)
        self.assertEqual(out.read_text(), "[00:01] First line\n[00:01] Second line\n[00:02] Third line\n")
        run(sys.executable, ROOT / "skills/deep-yt-analysis/vtt-dedupe.py", vtt, out, env=self.env)
        self.assertEqual(out.read_text(), "[00:01] Second line\n[00:02] Third line\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
