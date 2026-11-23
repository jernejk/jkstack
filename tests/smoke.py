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
            pending = (work / "live/keeper/draft.json").exists()
            run(sys.executable, work / "live/patch.py", input='{"draft": true}' if pending else "{}", env=self.env)
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
        out = self.patch(work, {"editChapters": {"c1": {"keyBeats": [ids["Pick one"]]}}}, ok=False)
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

    def test_choices_may_carry_reviewed_images(self):
        work = self.init()
        ask = lambda choices: {"events": [{"lane": "main", "kind": "blocked", "importance": 3, "title": "Pick the art", "summary": "Two sets pass.",
                                           "ask": "Which set ships?", "choices": choices}]}
        self.patch(work, ask([{"label": "Neon", "image": "live/thumbs/neon.jpg"}, "Paper"]))
        self.assertEqual(self.feed(work)["events"][-1]["choices"][0], {"label": "Neon", "image": "live/thumbs/neon.jpg"})
        for image in ("../neon.jpg", "private/neon.jpg", "https://example.com/neon.jpg", "/abs/neon.jpg", "live/thumbs/a b.jpg"):
            out = self.patch(work, ask([{"label": "Neon", "image": image}, "Paper"]), ok=False)
            self.assertIn("image path must stay", out.stdout, image)
        for bad in ([{"label": "Neon", "url": "x"}, "Paper"], [{"image": "live/thumbs/neon.jpg"}, "Paper"], [{"label": "x" * 81}, "Paper"]):
            self.assertNotEqual(self.patch(work, ask(bad), ok=False).returncode, 0, bad)
        brief = run(sys.executable, work / "live/brief.py", "--blockers", env=self.env).stdout
        self.assertIn("Options: Neon / Paper.", brief)

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
                                      "title": "Opus is working", "summary": "Now."}], "run": {"done": None}})
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
        snapshot = lambda: {str(p.relative_to(work)): p.read_bytes() for p in (work / "live").rglob("*") if p.is_file()}
        before = snapshot()
        out = run(sys.executable, work / "live/ingest.py", "--dry-run", "--all", env=self.env).stdout
        self.assertIn("10 events", out)
        self.assertEqual(snapshot(), before)
        self.collect(work)
        with (work / "LEAD-LOG.md").open("a") as f:
            f.write("- 00:50 (main) [result] Later the same night.\n- 17:40 (main) [result] The next evening.\n- 00:05 (main) [result] The day after.\n")
        self.collect(work, commit=False)
        draft = json.loads((work / "live/keeper/draft.json").read_text())
        self.assertEqual([e["time"][:16] for e in draft["events"]], ["2026-11-21T00:50", "2026-11-21T17:40", "2026-11-22T00:05"])

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

    LOG_HEAD = "# Lead log: demo (2026-11-20, UTC+10)\n"

    def lead_work(self, text, lanes="main:Main lane,sol:Sol lane,qa:QA lane", name="work"):
        work = self.init(lanes, "+10:00", "--empty", name=name)
        self.lead_log(work, self.LOG_HEAD + text)
        return work

    def draft(self, work):
        return json.loads((work / "live/keeper/draft.json").read_text())

    def crash(self, work, script, patch=None):
        (work / "live/crash.py").write_text(script)
        return run(sys.executable, work / "live/crash.py", env=self.env, input=patch, ok=False)

    def test_unapplied_draft_and_cursor_survive_a_plain_patch(self):
        work = self.lead_work("- 10:00 (main) [result] Keep me.\n")
        run(sys.executable, work / "live/collect.py", env=self.env)
        out = self.patch(work, {})
        self.assertFalse(self.last_json(out)["committed"])
        self.assertIn("a lead-log draft is pending", out.stdout)
        keeper = work / "live/keeper"
        self.assertTrue((keeper / "draft.json").exists() and (keeper / "state.next.json").exists())
        self.assertFalse((keeper / "state.json").exists())
        self.assertIn("Keep me", run(sys.executable, work / "live/collect.py", env=self.env).stdout)
        out = self.patch(work, {"draft": True})
        self.assertTrue(self.last_json(out)["committed"])
        self.assertEqual([e["summary"] for e in self.feed(work)["events"]], ["Keep me."])
        self.assertFalse((keeper / "draft.json").exists())
        self.assertNotIn("SOURCE", run(sys.executable, work / "live/collect.py", env=self.env).stdout)

    def test_draft_from_another_pass_than_the_cursor_is_refused(self):
        work = self.lead_work("- 10:00 (main) [result] First.\n")
        run(sys.executable, work / "live/collect.py", env=self.env)
        staged = work / "live/keeper/state.next.json"
        state = json.loads(staged.read_text())
        staged.write_text(json.dumps({**state, "batch": "older-pass"}))
        out = self.patch(work, {"draft": True}, ok=False)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("draft and cursor are from different passes; run collect.py again", out.stderr)
        self.assertEqual(self.feed(work)["events"], [])
        self.assertTrue((work / "live/keeper/draft.json").exists())

    def test_crash_between_draft_and_cursor_staging_cannot_apply_the_stale_pair(self):
        work = self.lead_work("- 10:00 (main) [result] Old draft.\n- 10:01 (main) [result] Unstaged beat.\n")
        self.crash(work, "import os\nimport collect\nwrite = collect.write_state\n"
                         "def crash(state, target):\n    if target == collect.STAGED: os._exit(77)\n    write(state, target)\n"
                         "collect.write_state = crash\ncollect.main()\n")
        self.assertTrue((work / "live/keeper/draft.json").exists())
        self.assertNotEqual(self.patch(work, {"draft": True}, ok=False).returncode, 0)
        self.assertEqual(self.feed(work)["events"], [])
        run(sys.executable, work / "live/collect.py", env=self.env)
        self.patch(work, {"draft": True})
        self.assertEqual([e["summary"] for e in self.feed(work)["events"]], ["Old draft.", "Unstaged beat."])

    def test_crash_after_install_before_commit_cannot_duplicate_beats(self):
        work = self.lead_work("- 10:00 (main) [result] Once only.\n")
        run(sys.executable, work / "live/collect.py", env=self.env)
        self.crash(work, "import os\nimport patch\ninstall = patch.validate.install\n"
                         "def crash(path):\n    install(path)\n    os._exit(77)\npatch.validate.install = crash\npatch.main()\n",
                   json.dumps({"draft": True}))
        keeper = work / "live/keeper"
        self.assertTrue((keeper / "draft.json").exists() and (keeper / "state.next.json").exists())
        self.assertEqual(len(self.feed(work)["events"]), 1)
        self.assertEqual(self.feed(work)["batch"], json.loads((keeper / "state.next.json").read_text())["batch"])
        self.assertNotIn("SOURCE", run(sys.executable, work / "live/collect.py", env=self.env).stdout)
        self.assertTrue((keeper / "state.json").exists())
        self.assertFalse((keeper / "draft.json").exists())
        self.assertNotEqual(self.patch(work, {"draft": True}, ok=False).returncode, 0)
        self.patch(work, {})
        self.assertEqual([e["summary"] for e in self.feed(work)["events"]], ["Once only."])

    def test_bad_times_go_unparsed_and_late_appends_keep_the_day(self):
        work = self.lead_work("- 09:00 (main) [result] Valid.\n- 10:60 (main) [result] Impossible time.\n    [metric: Lost = 1]\n"
                              "- 10:00 (main) [date: 2026-02-30] Impossible date.\n- 11:00 (main) [result] Also valid.\n"
                              "- 23:55 (main) [start] Night.\n- 00:10 (main) [result] Morning.\n"
                              "- 23:58 (main) [review] Late append.\n- 00:12 (main) [result] Still morning.\n")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertIn("UNPARSED", out)
        self.assertIn("- 10:60 (main) [result] Impossible time.", out)
        self.assertIn("    [metric: Lost = 1]", out)
        self.assertIn("- 10:00 (main) [date: 2026-02-30] Impossible date.", out)
        self.assertIn("invalid time 10:60", out)
        self.assertIn("invalid [date: 2026-02-30]", out)
        self.assertEqual([e["time"][:16] for e in self.draft(work)["events"]],
                         ["2026-11-20T09:00", "2026-11-20T11:00", "2026-11-20T23:55", "2026-11-21T00:10", "2026-11-20T23:58", "2026-11-21T00:12"])

    def test_a_half_written_last_line_waits_and_a_split_beat_stays_unparsed(self):
        work = self.lead_work("- 10:00 (main) [result] Whole.\n- 10:05 (main) [result] Half")
        run(sys.executable, work / "live/collect.py", env=self.env)
        self.assertEqual([e["summary"] for e in self.draft(work)["events"]], ["Whole."])
        self.patch(work, {"draft": True})
        self.assertNotIn("SOURCE", run(sys.executable, work / "live/collect.py", env=self.env).stdout)
        with (work / "LEAD-LOG.md").open("a") as f:
            f.write(" written.\n")
        run(sys.executable, work / "live/collect.py", env=self.env)
        self.assertEqual([e["summary"] for e in self.draft(work)["events"]], ["Half written."])
        self.patch(work, {"draft": True})
        log = work / "LEAD-LOG.md"
        log.write_text(log.read_text() + "    [metric: Late = 5]\n")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertIn("UNPARSED (handle by hand):\n      [metric: Late = 5]", out)

    def test_tags_ignore_code_spans_and_nest_one_bracket_level(self):
        work = self.lead_work("- 10:00 (sol) [ask: Pick [default on] | Fast | Slow]\n- 10:02 (sol) [result] Keep `[fail]` literal.\n"
                              "- 10:04 (main) [start] Build parser.\n- 10:05 (main) [start] [done: Build parser] Build parser retries.\n")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        ev = {e["ref"]: e for e in self.draft(work)["events"]}
        self.assertEqual((ev["d1"]["kind"], ev["d1"]["ask"], ev["d1"]["choices"]), ("blocked", "Pick [default on]", ["Fast", "Slow"]))
        self.assertEqual((ev["d2"]["kind"], ev["d2"]["summary"]), ("success", "Keep `[fail]` literal."))
        self.assertEqual(self.draft(work)["edit"], {"@d3": {"state": "done", "end": "2026-11-20T10:05:00+10:00"}})
        self.assertNotIn("UNMATCHED", out)

    def test_done_never_closes_its_own_line_and_ties_across_lanes_stay_unresolved(self):
        work = self.lead_work("- 10:00 (sol) [start] Check parser cases.\n- 10:05 (qa) [start] Check formatter cases.\n"
                              "- 10:10 (main) [result] [done: check cases] Checks done.\n- 10:20 (main) [start] [done: Fix lone] Fix lone.\n")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertEqual(self.draft(work).get("edit", {}), {})
        self.assertIn("AMBIGUOUS done: check cases", out)
        self.assertIn("UNMATCHED done: Fix lone", out)

    def test_cleared_stays_on_its_lane_unless_the_owner_clears(self):
        work = self.lead_work("- 10:00 (sol) [blocker: Need access] Sol waits.\n- 10:01 (main) [cleared] Main clears.\n"
                              "- 10:02 (qa) [blocker: Need data] QA waits.\n- 10:03 (owner) [cleared] Owner clears the newest.\n"
                              "- 10:04 (qa) [cleared] Own lane, nothing open.\n- 10:05 (sol) [cleared] Own lane.\n", lanes="main:Main lane,sol:Sol lane,qa:QA lane")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertEqual(self.draft(work)["edit"], {"@d2": {"state": "cleared"}, "@d1": {"state": "cleared"}})
        self.assertEqual(out.count("UNMATCHED cleared"), 2)
        self.assertIn("UNMATCHED cleared on 10:01 line", out)

    def test_private_lead_logs_and_images_are_refused_through_symlinks(self):
        work = self.lead_work("- 10:00 (main) [result] Private marker. [img: shots/innocent.png | Marker]\n")
        (work / "private").mkdir()
        (work / "private/LEAD-LOG.md").write_text((work / "LEAD-LOG.md").read_text())
        (work / "LEAD-LOG.md").unlink()
        (work / "LEAD-LOG.md").symlink_to(work / "private/LEAD-LOG.md")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertIn("SKIPPED lead log: LEAD-LOG.md is a symlink", out)
        self.assertNotIn("Private marker", out)
        self.assertFalse((work / "live/keeper/draft.json").exists())
        (work / "LEAD-LOG.md").unlink()
        (work / "open").symlink_to(work / "private")
        config = work / "live/keeper/config.json"
        config.write_text(json.dumps({**json.loads(config.read_text()), "leadLog": "open/LEAD-LOG.md"}))
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertIn("SKIPPED lead log: open/LEAD-LOG.md resolves into a private folder", out)
        self.assertNotIn("Private marker", out)

        work = self.lead_work("- 10:00 (main) [result] Shot. [img: shots/innocent.png | Marker] [img: shots/fine.png | Fine]\n", name="work2")
        self.png(work / "private/secret.png")
        self.png(work / "shots/fine.png")
        (work / "shots").mkdir(exist_ok=True)
        (work / "shots/innocent.png").symlink_to(work / "private/secret.png")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertIn("refused image shots/innocent.png", out)
        images = self.draft(work)["events"][0]["images"]
        self.assertEqual([i.get("full", i["path"]) for i in images], ["shots/fine.png"])
        thumbs = [p.name for p in (work / "live/thumbs").glob("*")]
        self.assertLessEqual(len(thumbs), 1)
        self.assertTrue(all(re.fullmatch(r"1000-fine-[0-9a-f]{12}\.jpg", n) for n in thumbs), thumbs)

    def set_config(self, work, **cfg_extra):
        config = work / "live/keeper/config.json"
        config.write_text(json.dumps({**json.loads(config.read_text()), **cfg_extra}))

    def test_raw_sources_follow_the_lead_log_privacy_checks(self):
        work = self.init()
        (work / "private").mkdir()
        (work / "private/STATUS.md").write_text("Private marker.\n")
        (work / "open").symlink_to(work / "private")
        self.set_config(work, sources=["*/STATUS.md"], leadLog="open/STATUS.md")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertNotIn("Private marker", out)
        self.set_config(work, sources=["*/STATUS.md"], leadLog="")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertNotIn("Private marker", out)
        (work / "open").unlink()
        (work / "shared").mkdir()
        (work / "shared/STATUS.md").write_text("Shared marker.\n")
        self.set_config(work, sources=["*/STATUS.md"], leadLog="shared/STATUS.md", exclude=["/shared/"])
        self.assertNotIn("Shared marker", run(sys.executable, work / "live/collect.py", env=self.env).stdout)

    def test_keeper_brief_sends_the_draft_only_when_collect_staged_one(self):
        brief = (ROOT / "skills/live-timeline/references/keeper-brief.md").read_text()
        self.assertRegex(brief, r"(?i)only when collect\.py printed a `DRAFT from")
        work = self.init()
        (work / "STATUS.md").write_text("Changed report.\n")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertIn("Changed report", out)
        self.assertNotIn("DRAFT from", out)
        failed = self.patch(work, {"draft": True}, ok=False)
        self.assertIn("no readable live/keeper/draft.json", failed.stderr)
        lead = self.lead_work("- 10:00 (main) [result] Staged.\n", name="lead")
        self.assertIn("DRAFT from LEAD-LOG.md", run(sys.executable, lead / "live/collect.py", env=self.env).stdout)

    def test_bounded_briefs_keep_events_and_only_all_uses_digests(self):
        work = self.init()
        data = self.feed(work)
        e = {"lane": "main", "kind": "success", "importance": 2}
        now = datetime.now().astimezone()
        before = (now - timedelta(days=2)).isoformat(timespec="seconds")
        data["chapters"] = [{"id": "c1", "title": "Build", "start": before, "digest": "DIGEST of the whole chapter.", "keyBeats": ["e001"]}]
        data["events"] = [dict(e, id="e001", chapter="c1", time=before, title="Earlier work", summary="Yesterday."),
                          dict(e, id="e002", chapter="c1", time=now.isoformat(timespec="seconds"), title="Today detail", summary="Detail today.")]
        (work / "live/events.json").write_text(json.dumps(data))
        today = run(sys.executable, work / "live/brief.py", "--since", "today", env=self.env).stdout
        self.assertIn("Today detail", today)
        self.assertNotIn("DIGEST of the whole chapter", today)
        self.assertNotIn("Earlier work", today)
        every = run(sys.executable, work / "live/brief.py", "--since", "all", env=self.env).stdout
        self.assertIn("DIGEST of the whole chapter", every)

    def test_thumbnails_of_same_named_images_do_not_collide(self):
        work = self.lead_work("- 10:00 (main) [result] Two. [img: build/screen.png | A] [img: qa/screen.png | B]\n"
                              "- 10:00 (main) [date: 2026-11-21] [result] Next day. [img: build/screen.png | C]\n")
        self.png(work / "build/screen.png")
        self.png(work / "qa/screen.png")
        run(sys.executable, work / "live/collect.py", env=self.env)
        images = [i for e in self.draft(work)["events"] for i in e["images"]]
        self.assertEqual(len(images), 3)
        thumbs = [i["path"] for i in images if i["path"].startswith("live/thumbs/")]
        self.assertEqual(len(set(thumbs)), len(thumbs), thumbs)
        self.assertTrue(all((work / i["path"]).is_file() for i in images), images)

    def test_a_replaced_image_with_the_same_size_and_mtime_gets_a_new_thumbnail(self):
        work = self.lead_work("- 10:00 (main) [result] One. [img: build/screen.png | A]\n")
        self.png(work / "build/screen.png")
        thumb = lambda: subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'live'); import ingest; "
                                        "print(ingest.thumb('build/screen.png', '1000', '2026-11-20', False)[0]['path'])"],
                                       cwd=work, capture_output=True, text=True, check=True).stdout.strip()
        first = thumb()
        img = work / "build/screen.png"
        st, raw = img.stat(), bytearray(img.read_bytes())
        raw[-13] ^= 1
        img.write_bytes(bytes(raw))
        os.utime(img, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.assertNotEqual(thumb(), first)

    def test_closure_tags_skip_superseded_events(self):
        work = self.lead_work("- 10:30 (sol) [result] [done: Fix parser] [cleared] Closed.\n")
        data = self.feed(work)
        e = {"lane": "sol", "importance": 2, "summary": "x"}
        data["events"] = [dict(e, id="e001", kind="start", state="running", time="2026-11-20T09:00:00+10:00", title="Fix parser"),
                          dict(e, id="e002", kind="start", state="running", time="2026-11-20T08:00:00+10:00", title="Fix parser", supersedes="e001"),
                          dict(e, id="e003", kind="blocked", state="open", time="2026-11-20T09:10:00+10:00", title="Wait"),
                          dict(e, id="e004", kind="blocked", state="open", time="2026-11-20T08:10:00+10:00", title="Wait", supersedes="e003")]
        (work / "live/events.json").write_text(json.dumps(data))
        run(sys.executable, work / "live/collect.py", env=self.env)
        edit = self.draft(work)["edit"]
        self.assertEqual(edit["e002"]["state"], "done")
        self.assertEqual(edit["e004"], {"state": "cleared"})
        self.assertNotIn("e001", edit)
        self.assertNotIn("e003", edit)

    def t3_profile(self):
        import sqlite3
        home = self.base / "t3profile"
        (home / "userdata").mkdir(parents=True)
        con = sqlite3.connect(home / "userdata/state.sqlite")
        con.execute("CREATE TABLE orchestration_v2_projection_threads (thread_id, title, updated_at, payload_json, deleted_at, archived_at)")
        con.execute("CREATE TABLE orchestration_v2_projection_runtime_requests (thread_id, kind, created_at, status)")
        con.execute("INSERT INTO orchestration_v2_projection_threads VALUES ('th_p', 'Profile lane', ?, '{}', NULL, NULL)",
                    (datetime.now().astimezone().isoformat(),))
        con.commit()
        con.close()
        return home

    def test_collect_reads_the_t3_database_of_the_t3code_home_profile(self):
        home = self.t3_profile()
        work = self.init()
        self.set_config(work, t3={"root": "th_p"})
        env = dict(self.env, T3CODE_HOME=str(home))
        out = run(sys.executable, work / "live/collect.py", env=env).stdout
        self.assertIn("T3 THREADS 1 watched", out)
        self.assertNotIn("unavailable", out)

    def test_an_unreadable_t3_database_keeps_the_previous_observations(self):
        home = self.t3_profile()
        work = self.init()
        self.set_config(work, t3={"root": "th_p"})
        env = dict(self.env, T3CODE_HOME=str(home))
        state = work / "live/keeper/state.json"
        run(sys.executable, work / "live/collect.py", env=env)
        self.patch(work, {})
        self.assertIn("th_p", json.loads(state.read_text())["threads"])
        (home / "userdata/state.sqlite").unlink()
        out = run(sys.executable, work / "live/collect.py", env=env).stdout
        self.patch(work, {})
        self.assertIn("unavailable", out)
        self.assertIn("th_p", json.loads(state.read_text())["threads"])

    def test_chapterless_events_join_the_last_appended_chapter_on_equal_starts(self):
        work = self.init()
        start = self.feed(work)["chapters"][0]["start"]
        self.patch(work, {"chapters": [{"title": "Second", "start": start}],
                          "events": [{"lane": "main", "kind": "update", "importance": 2, "title": "Later", "summary": "Later.",
                                      "time": (datetime.fromisoformat(start) + timedelta(minutes=5)).isoformat()}]})
        data = self.feed(work)
        self.assertEqual([c["id"] for c in data["chapters"]], ["c1", "c2"])
        self.assertEqual(data["events"][-1]["chapter"], "c2")

    def test_a_replayed_draft_after_install_is_refused_until_collect_commits(self):
        work = self.lead_work("- 10:00 (main) [result] Once only.\n")
        run(sys.executable, work / "live/collect.py", env=self.env)
        self.crash(work, "import os\nimport patch\ninstall = patch.validate.install\n"
                         "def crash(path):\n    install(path)\n    os._exit(77)\npatch.validate.install = crash\npatch.main()\n",
                   json.dumps({"draft": True}))
        again = self.patch(work, {"draft": True}, ok=False)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("run collect.py", again.stderr)
        self.assertEqual(len(self.feed(work)["events"]), 1)

    def test_draft_and_patch_nulls_delete_headline_fields(self):
        work = self.lead_work("- 10:00 (main) [result] Beat.\n")
        self.patch(work, {"headline": {"best": {"text": "Old best"}, "progress": {"value": 1, "of": 2}}})
        run(sys.executable, work / "live/collect.py", env=self.env)
        self.patch(work, {"draft": True, "headline": {"best": None}})
        head = self.feed(work)["headline"]
        self.assertNotIn("best", head)
        self.assertIn("progress", head)

    def test_refs_resolve_only_where_ids_belong_and_duplicates_are_refused(self):
        work = self.init()
        out = self.patch(work, {"events": [{"ref": "a", "lane": "main", "kind": "update", "importance": 1, "title": "Owner note",
                                            "summary": "@owner said ship it."}]})
        self.assertEqual(self.feed(work)["events"][-1]["summary"], "@owner said ship it.")
        patch = {"events": [{"ref": "a", "lane": "main", "kind": "update", "importance": 1, "title": "One", "summary": "x"},
                            {"ref": "a", "lane": "main", "kind": "update", "importance": 1, "title": "Two", "summary": "y"}]}
        before = self.feed(work)
        bad = self.patch(work, patch, ok=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("ref a is declared twice", bad.stderr)
        self.assertEqual(self.feed(work), before)
        ok = self.patch(work, {"events": [{"ref": "b", "lane": "main", "kind": "success", "importance": 2, "title": "B", "summary": "b",
                                           "causedBy": ["@b"]}, {"ref": "c", "lane": "main", "kind": "success", "importance": 2, "title": "C",
                                                                 "summary": "c", "causedBy": ["@b"]}],
                               "headline": {"best": {"text": "@b is literal text", "eventId": "@c"}},
                               "metrics": [{"name": "M", "value": 1, "event": "@c"}]})
        data = self.feed(work)
        ids = {e["title"]: e["id"] for e in data["events"]}
        self.assertEqual(data["events"][-1]["causedBy"], [ids["B"]])
        self.assertEqual(data["headline"]["best"], {"text": "@b is literal text", "eventId": ids["C"]})
        self.assertEqual(data["metrics"][-1]["event"], ids["C"])

    def test_draft_refs_clash_with_extra_event_refs(self):
        work = self.lead_work("- 10:00 (main) [result] Lead result. [metric: Rows = 12]\n")
        run(sys.executable, work / "live/collect.py", env=self.env)
        extra = {"ref": "d1", "lane": "sol", "kind": "success", "importance": 2, "title": "Other result", "summary": "Other result"}
        bad = self.patch(work, {"draft": True, "events": [extra]}, ok=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("ref d1 is declared twice", bad.stderr)
        self.assertEqual(self.feed(work)["events"], [])

    def feed_with(self, work, mutate):
        data = self.feed(work)
        mutate(data)
        file = work / "live/events.next.json"
        file.write_text(json.dumps(data))
        return run(sys.executable, work / "live/validate.py", file, env=self.env, ok=False)

    def test_validation_limits_key_beats_digest_and_t3_ids(self):
        work = self.init()
        def story(data):
            data["chapters"] = [{"id": "c1", "title": "A", "start": "2026-11-20T10:00:00Z"}, {"id": "c2", "title": "B", "start": "2026-11-20T11:00:00Z"}]
            e = {"lane": "main", "kind": "success", "importance": 2, "time": "2026-11-20T10:30:00Z"}
            data["events"] = [dict(e, id="e001", title="One", summary="One", chapter="c1"), dict(e, id="e002", title="Two", summary="Two", chapter="c2"),
                              dict(e, id="e003", title="Implicit", summary="Implicit"), dict(e, id="e004", time="2026-11-20T11:30:00Z", title="Late", summary="Late")]
        self.assertEqual(self.feed_with(work, story).returncode, 0)
        def key_beats(beats):
            return lambda d: (story(d), d["chapters"][0].update(keyBeats=beats))
        self.assertEqual(self.feed_with(work, key_beats(["e001", "e003"])).returncode, 0)
        for beats, needle in ((["e001", "e002"], "belongs to another chapter"), (["e001", "e001"], "duplicates"), (["e001", "e003", "e001", "e003", "e001"], "at most 4"),
                              (["e004"], "belongs to another chapter"), (["e999"], "does not exist")):
            result = self.feed_with(work, key_beats(beats))
            self.assertNotEqual(result.returncode, 0, beats)
            self.assertIn(needle, result.stdout)
        for run_fields in ({"digest": ["a", "b", "c", "d"]}, {"t3": {"env": "%2e%2e", "thread": "th_1"}}, {"t3": {"env": "e", "thread": "a..b"}},
                           {"t3": {"env": "e", "thread": "x%2Fy"}}, {"t3": {"env": "e", "thread": "x%5Cy"}}):
            self.assertNotEqual(self.feed_with(work, lambda d: d["run"].update(run_fields)).returncode, 0, run_fields)
        self.assertEqual(self.feed_with(work, lambda d: d["run"].update(digest=["a", "b", "c"], t3={"env": "env-1", "thread": "th_1:v.2"})).returncode, 0)
        self.assertNotEqual(self.feed_with(work, lambda d: (story(d), d["events"][0].update(thread="%2E%2e"))).returncode, 0)
        (self.home / ".t3/userdata").mkdir(parents=True)
        (self.home / ".t3/userdata/environment-id").write_text("env-1")
        for thread, expect in (("th_ok", True), ("a..b", False), ("x%2Fy", False)):
            target = self.base / f"t3-{thread[:4]}"
            run(sys.executable, ROOT / "skills/live-timeline/scripts/init.py", target, "--owner", "Owner", "--lanes", "main:Main", "--t3-thread", thread,
                env=dict(self.env, T3CODE_HOME=str(self.home / ".t3")))
            self.assertEqual("t3" in json.loads((target / "live/events.json").read_text())["run"], expect, thread)

    def test_digest_skips_superseded_events_and_places_chapterless_ones_by_time(self):
        work = self.init()
        data = self.feed(work)
        e = {"time": "2026-11-20T10:30:00Z", "kind": "success", "importance": 2, "lane": "main"}
        data["chapters"] = [{"id": "c1", "title": "Chapter", "start": "2026-11-20T10:00:00Z"}]
        data["events"] = [dict(e, id="e001", chapter="c1", title="Wrong count", summary="Wrong count"),
                          dict(e, id="e002", title="Correct count", summary="Correct count", supersedes="e001")]
        (work / "live/events.json").write_text(json.dumps(data))
        out = run(sys.executable, work / "live/digest.py", env=self.env).stdout
        self.assertIn("Correct count", out)
        self.assertNotIn("Wrong count", out)
        self.assertIn("c1 Chapter · ", out)

    def test_first_pass_cut_keeps_a_beat_with_its_continuation(self):
        work = self.lead_work("- 10:00 (main) [result] One.\n- 10:05 (main) [result] Two.\n    [metric: Rows = 5]\n")
        self.set_config(work, firstPassTail=1)
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertNotIn("UNPARSED", out)
        draft = self.draft(work)
        self.assertEqual([e["summary"] for e in draft["events"]], ["Two."])
        self.assertEqual([m["name"] for m in draft["metrics"]], ["Rows"])

    def test_a_pending_draft_blocks_a_new_pass_and_its_beats_are_not_lost(self):
        work = self.lead_work("- 10:00 (main) [result] Keep me.\n")
        run(sys.executable, work / "live/collect.py", env=self.env)
        with (work / "LEAD-LOG.md").open("a") as f:
            f.write("stray note\n")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertIn('PENDING draft ', out)
        self.assertIn("Keep me", out)
        self.assertEqual([e["summary"] for e in self.draft(work)["events"]], ["Keep me."])
        self.assertTrue(self.last_json(self.patch(work, {"draft": True}))["committed"])
        self.assertEqual([e["summary"] for e in self.feed(work)["events"]], ["Keep me."])
        again = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertNotIn("PENDING", again)
        self.assertIn("UNPARSED (handle by hand):\n  stray note", again)

    def test_done_and_review_ignore_starts_after_the_closing_beat(self):
        work = self.lead_work("- 10:30 (sol) [start] Fix parser.\n- 10:05 (sol) [review] Early review.\n"
                              "- 10:20 (sol) [result] [done: Fix parser] Closed too early.\n")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertEqual(self.draft(work).get("edit", {}), {})
        self.assertIn("UNMATCHED done: Fix parser", out)

    def test_patch_refuses_when_the_cursor_changes_while_it_applies(self):
        work = self.lead_work("- 10:00 (main) [result] Once.\n")
        run(sys.executable, work / "live/collect.py", env=self.env)
        out = self.crash(work, "import json\nimport patch\ncheck = patch.validate.check\n"
                               "def hooked(*a, **k):\n    r = check(*a, **k)\n    patch.STAGED.write_text(json.dumps({'batch': 'newer-pass'}))\n    return r\n"
                               "patch.validate.check = hooked\npatch.main()\n", json.dumps({"draft": True}))
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("cursor changed", out.stderr)
        self.assertEqual(self.feed(work)["events"], [])
        self.assertFalse((work / "live/keeper/state.json").exists())

    def test_stale_status_reminder_survives_a_quiet_collection_but_not_a_wait(self):
        work = self.init()
        (work / "STATUS.md").write_text("Report.\n")
        old = time.time() - 7200
        os.utime(work / "STATUS.md", (old, old))
        self.collect(work)
        data = self.feed(work)
        data["headline"]["status"]["asOf"] = (datetime.now().astimezone() - timedelta(hours=1)).isoformat(timespec="seconds")
        (work / "live/events.json").write_text(json.dumps(data))
        self.assertIn("STATUS set", run(sys.executable, work / "live/collect.py", env=self.env).stdout)
        self.assertIn("QUIET", run(sys.executable, work / "live/collect.py", "--wait", "1s", env=self.env).stdout)

    def test_a_source_that_vanishes_after_enumeration_is_skipped(self):
        work = self.init()
        result = self.crash(work, "import collect\ngone = [('GONE.md', collect.ROOT / 'GONE.md')]\ncollect.sources = lambda cfg: gone\n"
                                  "collect.something_new(collect.load_config(), {})\ncollect.collect()\n")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_stray_line_ends_the_continuation_group_and_backtick_runs_pair_up(self):
        work = self.lead_work("- 10:00 (main) [result] Beat.\nstray text\n    [metric: Late = 5]\n")
        out = run(sys.executable, work / "live/collect.py", env=self.env).stdout
        self.assertNotIn("metrics", self.draft(work))
        self.assertIn("UNPARSED (handle by hand):\n  stray text\n      [metric: Late = 5]", out)
        work = self.lead_work("- 10:00 (main) Wrote `` ` `` quote then [fail] `x` done.\n- 10:01 (main) [result] Keep ``a ` [fail] b`` literal.\n", name="work2")
        run(sys.executable, work / "live/collect.py", env=self.env)
        ev = self.draft(work)["events"]
        self.assertEqual([e["kind"] for e in ev], ["fail", "success"])
        self.assertIn("``a ` [fail] b``", ev[1]["summary"])

    def test_init_survives_a_bad_environment_id_a_bad_offset_and_odd_feeds(self):
        t3home = self.base / "t3x"
        (t3home / "userdata").mkdir(parents=True)
        (t3home / "userdata/environment-id").write_bytes(b"\xff\xfe")
        env = dict(self.env, T3CODE_THREAD_ID="th_1", T3CODE_HOME=str(t3home))
        work = self.init(env=env)
        self.assertNotIn("t3", self.feed(work)["run"])
        self.assertEqual(json.loads((work / "live/keeper/config.json").read_text())["t3"]["root"], "th_1")
        bad = self.base / "badtz"
        result = run(sys.executable, ROOT / "skills/live-timeline/scripts/init.py", bad, "--tz", "UTC+24:00", env=env, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((bad / "live").exists())
        (t3home / "userdata/environment-id").write_text("env-1")
        for text in ("[]", '{"run": 5}'):
            (work / "live/events.json").write_text(text)
            run(sys.executable, ROOT / "skills/live-timeline/scripts/init.py", work, "--upgrade", env=env)
        (work / "live/events.json").write_text('{"run": {}}')
        self.assertIn('"t3"', run(sys.executable, ROOT / "skills/live-timeline/scripts/init.py", work, "--upgrade", env=env).stdout)

    def test_recent_ignores_superseded_starts_finished_lanes_and_finished_runs(self):
        work = self.init("main:Main lane,sol:Sol lane,qa:QA lane")
        data = self.feed(work)
        now, old = datetime.now().astimezone(), datetime.now().astimezone() - timedelta(hours=3)
        e = lambda i, lane, at, **extra: {"id": f"e{i:03d}", "lane": lane, "kind": "update", "importance": 2, "title": f"T{i}", "summary": "x",
                                          "time": at.isoformat(timespec="seconds"), **extra}
        data["events"] = [e(1, "qa", old, kind="start", state="running"), e(2, "qa", old, supersedes="e001"), e(3, "sol", now), e(4, "main", now)]
        for lane in data["lanes"]:
            lane["status"] = "done" if lane["id"] == "sol" else "running"
        (work / "live/events.json").write_text(json.dumps(data))
        out = run(sys.executable, work / "live/recent.py", env=self.env).stdout
        self.assertRegex(out, r"(?m)^ACTIVE main \(")
        data["run"]["done"] = True
        (work / "live/events.json").write_text(json.dumps(data))
        self.assertRegex(run(sys.executable, work / "live/recent.py", env=self.env).stdout, r"(?m)^ACTIVE none \(")

    def test_a_non_object_run_is_a_validation_error(self):
        work = self.init()
        result = self.feed_with(work, lambda d: d.update(run=5))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("run must be an object", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_digest_output_stays_bounded_after_the_last_trial(self):
        work = self.init()
        data = self.feed(work)
        data["chapters"] = [{"id": "c1", "title": "Big", "start": "2026-11-20T10:00:00+00:00"}]
        data["events"] = [{"id": f"e{i:03d}", "time": f"2026-11-20T10:{i % 60:02d}:00+00:00", "lane": "main", "kind": "success", "importance": 2,
                           "chapter": "c1", "title": f"Beat number {i}", "summary": "s"} for i in range(1, 301)]
        (work / "live/events.json").write_text(json.dumps(data))
        out = run(sys.executable, work / "live/digest.py", env=self.env).stdout
        self.assertLess(len(out.split("\n\nNEXT")[0]), 6200)
        self.assertIn("more lines omitted", out)

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
