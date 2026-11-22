#!/usr/bin/env python3
"""Offline smoke checks. All generated installs use temporary homes."""
import json
import os
import re
import subprocess
import sys
import struct
import tempfile
import time
import unittest
import zlib
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

    def init(self, lanes="main:Main lane", tz="UTC", *extra, env=None, name="work"):
        work = self.base / name
        run(sys.executable, ROOT / "skills/live-timeline/scripts/init.py", work,
            "--owner", "Owner", "--lanes", lanes, "--tz", tz, *extra, env=env or self.env)
        return work

    def collect(self, work, *args, commit=True):
        out = run(sys.executable, work / "live/collect.py", *args, env=self.env).stdout
        if commit:
            run(sys.executable, work / "live/patch.py", input="{}", env=self.env)
        return out

    def patch(self, work, patch, ok=True):
        return run(sys.executable, work / "live/patch.py", input=json.dumps(patch), env=self.env, ok=ok)

    def last_json(self, result):
        return json.loads(result.stdout.strip().splitlines()[-1])

    def feed(self, work):
        return json.loads((work / "live/events.json").read_text())

    def lead_log(self, work, text, **cfg_extra):
        config = work / "live/keeper/config.json"
        cfg = json.loads(config.read_text())
        cfg.update(leadLog="LEAD-LOG.md", sources=[], **cfg_extra)
        config.write_text(json.dumps(cfg))
        (work / "LEAD-LOG.md").write_text(text)

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
        out = self.collect(work)
        self.assertIn("First batch passed", out)
        self.assertNotIn("Do not collect", out)
        self.assertNotIn("SOURCE", self.collect(work))

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
        first = self.collect(work)
        self.assertIn("[img: shots/a.png | A]", first)
        self.assertIn("[metric: Rows = 12]", first)
        with log.open("a") as f:
            f.write("- Same line.\n")
        second = self.collect(work)
        self.assertIn("Same line.", second)
        cfg.update(maxLinesPerSource=3)
        config.write_text(json.dumps(cfg))
        with log.open("a") as f:
            f.write("".join(f"- 00:0{i} (main) [result] Paged beat {i}.\n" for i in range(5)))
        paged = self.collect(work) + self.collect(work)
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
        first, second, third = self.collect(work), self.collect(work), self.collect(work)
        for i in range(1, 7):
            self.assertEqual((first + second + third).count(f"Beat number {i} "), 1, i)
        self.assertIn("Sol found two risks", first + second + third)
        self.assertIn("HELD", first)
        self.assertIn("NEXT put all of this in one patch: LOG.md", first)
        self.assertNotIn("STATUS", first)
        cfg["statusStaleMin"] = 0
        config.write_text(json.dumps(cfg))
        stale = self.collect(work, commit=False)
        self.assertIn("NEXT send headline.status", stale)
        run(sys.executable, work / "live/patch.py", input='{"headline": {"status": {"tone": "warn", "text": "Slow"}}}', env=self.env)
        feed = json.loads((work / "live/events.json").read_text())
        self.assertIn("asOf", feed["headline"]["status"])
        self.assertIn("set ", run(sys.executable, work / "live/recent.py", env=self.env).stdout)

    SYNTHETIC_LOG = """# Lead log: demo (2026-11-20, UTC+10)
Snapshots: see header. Ignore this prose.

- 23:50 (main/opus-5) [start] Opus builds the path on grey boxes. [thread: th_abc-1]
- 23:55 (sol) [start] Sol checks the maths for the path.
- 00:10 (Main lane) [result] [done: Opus builds the path] Path passes 40 tests. [metric: Path tests = 40] [img: shots/a.png | Grey boxes] [img: shots/gone.png | Missing]
- 00:12 (owner) [ask: Which art style? | Neon | Paper | Pixel] JK must pick one.
- 00:14 (lead) [nudge] JK: keep it small.
- 00:20 (main) [chapter: Core loop - The loop gets built.] [decision] Loop work begins.
- 00:25 (sol) [result] [done: Sol maths for path] Maths verified. [metric: Cost = US$0.41] [metric: Levels = 3/6] [metric: Rows = 1,200] [metric: Idle = 36.7 %]
- 00:26 (sol) [metric: Cases = 12 of 20]
- 00:30 (qa) [blocker: Log in to the test account] Tests stall on a login. [status: warn Waiting on JK] [progress: 3/6 levels]
- 00:31 (qa) [cleared] The login works again. [key]
- 00:40 (main) [weird] Odd tag stays text. [best: Path in 31 s] [end]
  and a second sentence on the next line.
"""

    def png(self, path):
        raw = b"\x00" + b"\xff\x00\x00" * 4
        chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 1, 8, 2, 0, 0, 0))
                         + chunk(b"IDAT", zlib.compress(raw * 1)) + chunk(b"IEND", b""))

    def synthetic(self, name="work"):
        work = self.init("main:Main lane,sol:Sol lane", "+10:00", "--empty", name=name)
        self.png(work / "shots/a.png")
        self.lead_log(work, self.SYNTHETIC_LOG)
        return work

    def test_ingest_turns_a_lead_log_into_a_draft(self):
        work = self.synthetic()
        out = self.collect(work, commit=False)
        draft = json.loads((work / "live/keeper/draft.json").read_text())
        ev = {e["ref"]: e for e in draft["events"]}
        self.assertEqual(len(ev), 10)
        self.assertEqual(ev["d1"]["time"], "2026-11-20T23:50:00+10:00")
        self.assertEqual(ev["d3"]["time"], "2026-11-21T00:10:00+10:00")
        self.assertEqual((ev["d1"]["lane"], ev["d1"]["model"], ev["d1"]["thread"], ev["d1"]["state"]), ("main", "opus-5", "th_abc-1", "running"))
        self.assertEqual(ev["d3"]["lane"], "main")
        self.assertEqual(ev["d1"]["title"], "Opus builds the path on grey boxes")
        self.assertEqual((ev["d4"]["kind"], ev["d4"]["ask"], ev["d4"]["choices"]), ("blocked", "Which art style?", ["Neon", "Paper", "Pixel"]))
        self.assertEqual(ev["d5"]["lane"], "owner")
        self.assertEqual(draft["edit"]["@d1"], {"state": "done", "end": "2026-11-21T00:10:00+10:00"})
        self.assertEqual(draft["edit"]["@d2"]["state"], "done")
        self.assertEqual(draft["edit"]["@d8"]["state"], "cleared")
        metrics = {m["name"]: m for m in draft["metrics"]}
        self.assertEqual((metrics["Path tests"]["value"], metrics["Path tests"]["event"]), (40, "@d3"))
        self.assertEqual((metrics["Cost"]["value"], metrics["Cost"]["unit"]), (0.41, "US$"))
        self.assertEqual((metrics["Levels"]["value"], metrics["Levels"]["of"]), (3, 6))
        self.assertEqual(metrics["Rows"]["value"], 1200)
        self.assertEqual((metrics["Idle"]["value"], metrics["Idle"]["unit"]), (36.7, "%"))
        self.assertEqual((metrics["Cases"]["value"], metrics["Cases"]["of"], metrics["Cases"]["lane"]), (12, 20, "sol"))
        self.assertNotIn("event", metrics["Cases"])
        self.assertEqual(len(ev["d3"]["images"]), 1)
        image = ev["d3"]["images"][0]
        self.assertEqual((image["caption"], image.get("full", "shots/a.png")), ("Grey boxes", "shots/a.png"))
        self.assertTrue(image["path"].startswith("live/thumbs/0010-a") or image["path"] == "shots/a.png")
        self.assertEqual(draft["chapters"][0]["title"], "Core loop")
        self.assertEqual((draft["chapters"][0]["summary"], ev["d6"]["chapter"]), ("The loop gets built.", "@k1"))
        self.assertEqual((ev["d10"]["importance"], ev["d9"]["importance"]), (1, 3))
        self.assertIn("[weird]", ev["d10"]["summary"])
        self.assertIn("second sentence", ev["d10"]["summary"])
        self.assertEqual((draft["headline"]["status"]["tone"], draft["headline"]["progress"]["of"], draft["headline"]["best"]["text"]), ("done", 6, "Path in 31 s"))
        self.assertEqual([l["id"] for l in draft["addLanes"]], ["qa"])
        self.assertTrue(draft["run"]["done"])
        for needle in ("NEW LANE qa", "unknown tag [weird]", "missing image shots/gone.png", "DRAFT from LEAD-LOG.md: 10 beats"):
            self.assertIn(needle, out)
        self.assertIn('{"draft": true, "fill"', out)
        self.assertNotIn("UNPARSED", out)

    def test_draft_fill_and_draft_alone_install_and_validate(self):
        work = self.synthetic()
        self.collect(work, commit=False)
        result = self.patch(work, {"draft": True, "fill": {"d1": {"title": "Opus builds the path", "causedBy": ["@d2"]},
                                                           "d2": {"skip": True}, "d3": {"images": [{"path": "live/thumbs/x.jpg"}]}},
                                   "events": [{"lane": "main", "kind": "update", "importance": 1, "title": "Own beat", "summary": "After the draft."}]})
        out = self.last_json(result)
        self.assertTrue(out["committed"])
        data = self.feed(work)
        self.assertEqual(len(data["events"]), 10)
        self.assertEqual(data["events"][-1]["title"], "Own beat")
        self.assertNotIn("d2", out["refs"])
        first = data["events"][0]
        self.assertEqual((first["state"], first["end"]), ("done", "2026-11-21T00:10:00+10:00"))
        self.assertNotIn("causedBy", first)
        self.assertEqual(len(next(e for e in data["events"] if e["summary"].startswith("Path passes"))["images"]), 2)
        self.assertFalse((work / "live/keeper/draft.json").exists())
        self.assertTrue(data["run"]["done"])
        run(sys.executable, work / "live/validate.py", env=self.env)
        self.assertNotEqual(self.patch(work, {"draft": True}, ok=False).returncode, 0)

        again = self.synthetic("again")
        self.collect(again, commit=False)
        result = self.patch(again, {"draft": True})
        self.assertEqual(len(self.last_json(result)["new"]), 10)
        for bad in ({"draft": True, "fill": {"d1": {"titel": "x"}}}, {"draft": True, "fill": {"d99": {"title": "x"}}}, {"fill": {"d1": {}}}):
            run(sys.executable, again / "live/collect.py", "--reset", env=self.env)
            self.assertNotEqual(self.patch(again, bad, ok=False).returncode, 0)

    def test_collect_cursor_is_staged_until_patch_commits(self):
        work = self.init()
        (work / "STATUS.md").write_text("First batch passed.\n")
        first, second = self.collect(work, commit=False), self.collect(work, commit=False)
        self.assertIn("First batch passed", first)
        self.assertIn("First batch passed", second)
        self.assertIn("patch.py commits this pass", second)
        keeper = work / "live/keeper"
        self.assertTrue((keeper / "state.next.json").exists())
        self.assertFalse((keeper / "state.json").exists())
        self.patch(work, {"events": [{"lane": "main", "kind": "update", "importance": 1, "title": "Bad lane", "summary": "x"}],
                          "headline": {"status": {"tone": "nope", "text": "x"}}}, ok=False)
        self.assertFalse((keeper / "state.json").exists())
        self.assertTrue(self.last_json(self.patch(work, {}))["committed"])
        self.assertTrue((keeper / "state.json").exists())
        self.assertFalse((keeper / "state.next.json").exists())
        self.assertNotIn("SOURCE", self.collect(work))
        self.assertFalse(self.last_json(self.patch(work, {}))["committed"])
        (work / "STATUS.md").write_text("First batch passed.\nSecond batch passed.\n")
        run(sys.executable, work / "live/collect.py", "--mark", env=self.env)
        self.assertTrue((keeper / "state.json").exists())
        self.assertNotIn("SOURCE", self.collect(work, commit=False))

    def test_collect_wait_times_out_and_wakes_on_change(self):
        work = self.init()
        (work / "STATUS.md").write_text("One.\n")
        self.collect(work)
        started = time.monotonic()
        out = run(sys.executable, work / "live/collect.py", "--wait", "1s", env=self.env).stdout
        self.assertIn("QUIET for 1 s: nothing new. NEXT send {}.", out)
        self.assertLess(time.monotonic() - started, 10)
        (work / "STATUS.md").write_text("One.\nTwo.\n")
        started = time.monotonic()
        out = run(sys.executable, work / "live/collect.py", "--wait", "1m", env=self.env).stdout
        self.assertIn("Two.", out)
        self.assertLess(time.monotonic() - started, 10)
        self.assertNotEqual(run(sys.executable, work / "live/collect.py", "--wait", "soon", env=self.env, ok=False).returncode, 0)

    def test_patch_stamps_end_on_closed_starts_and_never_moves_one(self):
        work = self.init()
        at = lambda m: f"2026-11-20T10:{m:02d}:00+00:00"
        start = lambda ref, extra={}: {"ref": ref, "time": at(0), "lane": "main", "kind": "start", "importance": 2, "state": "running",
                                       "title": ref.upper(), "summary": f"{ref} runs.", **extra}
        self.patch(work, {"events": [start("a"), start("b"), start("c", {"end": at(5)}), start("d")]})
        ids = {e["title"]: e["id"] for e in self.feed(work)["events"]}
        result = lambda ref, minute, causes: {"ref": ref, "time": at(minute), "lane": "main", "kind": "success", "importance": 2,
                                              "title": ref.upper(), "summary": "r", "causedBy": [ids[c] for c in causes]}
        self.patch(work, {"events": [result("r1", 10, ["A"]), result("r2", 20, ["A", "B"])],
                          "edit": {ids["A"]: {"state": "done"}, ids["C"]: {"state": "failed"}, ids["B"]: {"state": "done", "end": at(30)}}})
        data = {e["title"]: e for e in self.feed(work)["events"]}
        self.assertEqual(data["A"]["end"], at(20))
        self.assertEqual(data["B"]["end"], at(30))
        self.assertEqual(data["C"]["end"], at(5))
        self.patch(work, {"edit": {ids["D"]: {"state": "done"}}})
        end = {e["title"]: e for e in self.feed(work)["events"]}["D"]["end"]
        self.assertEqual(end, self.feed(work)["updated"])

    def test_edit_chapters_key_beats_and_new_schema_fields(self):
        work = self.init()
        first = self.feed(work)["events"][0]["id"]
        self.patch(work, {"chapters": [{"ref": "two", "title": "Second"}],
                          "events": [{"ref": "x", "lane": "main", "kind": "blocked", "importance": 3, "chapter": "@two", "title": "Pick one",
                                      "summary": "Needs a pick.", "ask": "Pick.", "choices": ["A", "B"], "model": "opus-5", "thread": "th_1"}]})
        data = self.feed(work)
        ids = {e["title"]: e["id"] for e in data["events"]}
        cid = data["chapters"][-1]["id"]
        out = self.patch(work, {"editChapters": {cid: {"digest": "Two sentences.", "outcome": "One line.", "keyBeats": [ids["Pick one"]]}},
                                "run": {"digest": ["Line one."], "t3": {"env": "env-1", "thread": "th_1"}}}).stdout
        data = self.feed(work)
        self.assertEqual(data["chapters"][-1]["keyBeats"], [ids["Pick one"]])
        self.assertEqual(data["run"]["t3"]["thread"], "th_1")
        out = self.patch(work, {"editChapters": {"c1": {"keyBeats": [ids["Pick one"]]}}})
        self.assertIn("belongs to another chapter", out.stdout)
        bad = [{"editChapters": {"c99": {"digest": "x"}}}, {"editChapters": {cid: {"keyBeats": ["e999"]}}},
               {"editChapters": {cid: {"digest": "x" * 701}}}, {"editChapters": {cid: {"keyBeats": [first] * 7}}},
               {"run": {"digest": ["a"] * 5}}, {"run": {"t3": {"env": "bad id", "thread": "t"}}},
               {"events": [{"lane": "main", "kind": "update", "importance": 1, "title": "T", "summary": "s", "choices": ["A", "B"]}]},
               {"events": [{"lane": "main", "kind": "blocked", "importance": 1, "title": "T", "summary": "s", "choices": ["A"]}]},
               {"events": [{"lane": "main", "kind": "update", "importance": 1, "title": "T", "summary": "s", "end": "2026-11-20T10:00:00+00:00"}]},
               {"events": [{"lane": "main", "kind": "update", "importance": 1, "title": "T", "summary": "s", "thread": "no spaces"}]},
               {"events": [{"lane": "main", "kind": "update", "importance": 1, "title": "T", "summary": "s", "model": "m" * 33}]}]
        for patch in bad:
            self.assertNotEqual(self.patch(work, patch, ok=False).returncode, 0, patch)
        self.patch(work, {"metrics": [{"name": "Pass rate", "value": 1}]})
        out = self.patch(work, {"metrics": [{"name": "Pass rates", "value": 2}]}).stdout
        self.assertIn('metric "Pass rates" looks like existing "Pass rate"', out)

    def test_digest_recent_and_brief_use_the_story_layer(self):
        work = self.synthetic()
        self.collect(work, commit=False)
        self.patch(work, {"draft": True})
        out = run(sys.executable, work / "live/digest.py", env=self.env).stdout
        self.assertIn("c1 Core loop", out)
        self.assertIn("e001 23:50", out)
        self.assertIn('{"editChapters": {"c1": {"digest"', out)
        self.assertIn("SIZE ~", out)
        cid = next(c["id"] for c in self.feed(work)["chapters"] if c["title"] == "Core loop")
        self.patch(work, {"editChapters": {cid: {"digest": "The loop gets built in one night.", "outcome": "Loop playable."}}})
        missing = run(sys.executable, work / "live/digest.py", "--missing", env=self.env).stdout
        self.assertNotIn(f"{cid} Core loop", missing)
        one = run(sys.executable, work / "live/digest.py", cid, env=self.env).stdout
        self.assertIn("digest: The loop gets built in one night.", one)
        brief = run(sys.executable, work / "live/brief.py", "--since", "all", env=self.env).stdout
        self.assertIn("The loop gets built in one night.", brief)
        self.patch(work, {"events": [{"lane": "main", "kind": "start", "importance": 2, "state": "running", "model": "opus-5",
                                      "title": "Opus is working", "summary": "Now."}]})
        recent = run(sys.executable, work / "live/recent.py", env=self.env).stdout
        self.assertIn("Opus is working (opus-5)", recent)
        self.assertIn("ACTIVE main", recent)
        self.assertNotIn("IDLE", recent)

    def test_init_records_the_t3_thread_and_lead_log(self):
        t3home = self.base / "t3"
        (t3home / "userdata").mkdir(parents=True)
        (t3home / "userdata/environment-id").write_text("env-abc\n")
        env = dict(self.env, T3CODE_THREAD_ID="th_123", T3CODE_HOME=str(t3home))
        work = self.init("main:Main lane", "UTC", "--lead-log", "LEAD-LOG.md", env=env)
        data = self.feed(work)
        self.assertEqual(data["run"]["t3"], {"env": "env-abc", "thread": "th_123"})
        cfg = json.loads((work / "live/keeper/config.json").read_text())
        self.assertEqual((cfg["t3"]["root"], cfg["leadLog"]), ("th_123", "LEAD-LOG.md"))
        for script in ("ingest.py", "digest.py"):
            self.assertTrue((work / "live" / script).exists())
        run(sys.executable, work / "live/validate.py", env=self.env)
        other = self.base / "other"
        run(sys.executable, ROOT / "skills/live-timeline/scripts/init.py", other, "--no-t3", env=env)
        self.assertNotIn("t3", json.loads((other / "live/events.json").read_text())["run"])
        third = self.base / "third"
        run(sys.executable, ROOT / "skills/live-timeline/scripts/init.py", third, "--t3-thread", "th_9", env=dict(self.env, T3CODE_HOME=str(t3home)))
        self.assertEqual(json.loads((third / "live/events.json").read_text())["run"]["t3"]["thread"], "th_9")
        feed = work / "live/events.json"
        data["run"].pop("t3")
        feed.write_text(json.dumps(data))
        out = run(sys.executable, ROOT / "skills/live-timeline/scripts/init.py", work, "--upgrade", env=env).stdout
        self.assertIn('"t3"', out)
        self.assertNotIn("t3", json.loads(feed.read_text())["run"])

    def test_bare_blocker_is_text_not_an_owner_ask(self):
        work = self.init("main:Main lane", "+10:00", "--empty")
        self.lead_log(work, "# Lead log: demo (2026-11-20, UTC+10)\n\n- 10:00 (main) The [blocker] was a flaky test. [status: good Fine]\n")
        self.collect(work, commit=False)
        ev = json.loads((work / "live/keeper/draft.json").read_text())["events"]
        self.assertEqual([(e["kind"], "[blocker]" in e["summary"]) for e in ev], [("update", True)])

    def test_ingest_dry_run_writes_nothing_and_handles_rollover_state(self):
        work = self.synthetic()
        before = sorted(p.name for p in (work / "live").rglob("*"))
        out = run(sys.executable, work / "live/ingest.py", "--dry-run", "--all", env=self.env).stdout
        self.assertIn("10 events", out)
        self.assertEqual(sorted(p.name for p in (work / "live").rglob("*")), before)
        self.collect(work)
        with (work / "LEAD-LOG.md").open("a") as f:
            f.write("- 00:50 (main) [result] Later the same night.\n- 23:40 (main) [result] The next evening.\n- 00:05 (main) [result] The day after.\n")
        self.collect(work, commit=False)
        draft = json.loads((work / "live/keeper/draft.json").read_text())
        self.assertEqual([e["time"][:16] for e in draft["events"]], ["2026-11-21T00:50", "2026-11-21T23:40", "2026-11-22T00:05"])

    def test_ingest_continues_the_day_count_and_matches_existing_starts(self):
        work = self.init("main:Main lane", "+10:00", "--empty")
        self.lead_log(work, "# Lead log (2026-11-20, UTC+10)\n- 22:00 (main) [start] Opus builds the screens for the shop.\n"
                            "- 23:30 (main) [start] Sol checks the maths.\n- 00:10 (main) [result] Screens pass.\n"
                            "- 00:20 (main) [result] [done: Opus builds the screens] Screens done.\n", firstPassTail=2)
        self.collect(work, commit=False)
        draft = json.loads((work / "live/keeper/draft.json").read_text())
        self.assertEqual([e["time"][:16] for e in draft["events"]], ["2026-11-21T00:10", "2026-11-21T00:20"])
        self.assertIn("UNMATCHED done: Opus builds the screens", run(sys.executable, work / "live/collect.py", env=self.env).stdout)
        self.patch(work, {"draft": True, "fill": {"d1": {"title": "Screens pass"}}})
        self.patch(work, {"events": [{"time": "2026-11-21T00:25:00+10:00", "lane": "main", "kind": "start", "importance": 2, "state": "running",
                                      "title": "Opus builds the screens", "summary": "Screens."},
                                     {"time": "2026-11-21T00:26:00+10:00", "lane": "main", "kind": "start", "importance": 2, "state": "running",
                                      "title": "Haiku reviews copy", "summary": "Copy."}]})
        ids = {e["title"]: e["id"] for e in self.feed(work)["events"]}
        with (work / "LEAD-LOG.md").open("a") as f:
            f.write(f"- 01:00 (main) [result] [done: opus builds the screen] Fuzzy.\n- 01:05 (main) [result] [done: {ids['Haiku reviews copy']}] Exact.\n"
                    "Stray prose that is not a beat.\n")
        out = self.collect(work, commit=False)
        draft = json.loads((work / "live/keeper/draft.json").read_text())
        self.assertEqual(sorted(draft["edit"]), sorted([ids["Opus builds the screens"], ids["Haiku reviews copy"]]))
        self.assertEqual(draft["edit"][ids["Opus builds the screens"]]["end"], "2026-11-21T01:00:00+10:00")
        self.assertIn("UNPARSED", out)
        self.assertIn("Stray prose that is not a beat.", out)

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
