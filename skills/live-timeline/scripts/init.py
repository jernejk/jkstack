#!/usr/bin/env python3
"""Scaffold a live timeline into a work folder.

  python3 <skill-dir>/scripts/init.py <folder> --title "Audit-risk research night" \
      --owner Owner --lanes "orch:Orchestrator,opus:Opus lane,sol:Sol lane" [--budget 1500] [--tz UTC]

Creates <folder>/live-timeline.html and <folder>/live/ (events.json, SCHEMA.md, scripts, keeper/config.json).
Refuses to overwrite an existing timeline unless --force; --upgrade replaces only the page and scripts.
"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = ["validate.py", "patch.py", "collect.py", "brief.py"]


def local_tz():
    try:
        link = os.readlink("/etc/localtime")
        return link.split("zoneinfo/")[-1]
    except OSError:
        return ""


def now_iso(tz):
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds")
    except Exception:
        return datetime.now().astimezone().isoformat(timespec="seconds")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--title", required=False, default="Live timeline")
    ap.add_argument("--owner", default="Owner")
    ap.add_argument("--lanes", default="main:Main lane", help="id:Name[:Short], comma-separated")
    ap.add_argument("--budget", type=float)
    ap.add_argument("--currency", default="US$")
    ap.add_argument("--tz", default=local_tz())
    ap.add_argument("--page", default="live-timeline.html")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--upgrade", action="store_true", help="refresh page + scripts + SCHEMA, keep events and config")
    a = ap.parse_args()

    root = Path(a.folder).expanduser().resolve()
    live = root / "live"
    page = root / a.page
    exists = (live / "events.json").exists()
    if exists and not (a.force or a.upgrade):
        sys.exit(f"{live / 'events.json'} exists; use --upgrade to refresh the page and scripts, or --force to start over")
    (live / "keeper").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SKILL / "assets/timeline.html", page)
    for s in SCRIPTS:
        shutil.copyfile(SKILL / "scripts" / s, live / s)
    shutil.copyfile(SKILL / "references/schema.md", live / "SCHEMA.md")
    if a.upgrade and exists:
        print(f"upgraded {page} and {live}/ scripts; events and config untouched")
        return

    now = now_iso(a.tz)
    owner_id = re.sub(r"[^a-z0-9]+", "", a.owner.lower()) or "owner"
    lanes = [{"id": owner_id, "name": a.owner, "short": a.owner[:8], "status": "running", "human": True}]
    for spec in filter(None, (x.strip() for x in a.lanes.split(","))):
        parts = spec.split(":")
        lid = parts[0].strip().lower()
        name = parts[1].strip() if len(parts) > 1 else lid
        lanes.append({"id": lid, "name": name, "short": (parts[2] if len(parts) > 2 else name.split()[0])[:8], "status": "running"})
    feed = {
        "schema": 2,
        "updated": now,
        "run": {"title": a.title, "owner": a.owner, "tz": a.tz, "start": now, "staleAfterMin": 30},
        "headline": {"status": {"tone": "good", "text": "Starting", "note": "Timeline set up"}},
        "lanes": lanes,
        "chapters": [{"id": "c1", "title": "Setting out", "start": now, "summary": "What we are trying to do, and how."}],
        "events": [{"id": "e001", "time": now, "lane": lanes[1]["id"] if len(lanes) > 1 else owner_id, "kind": "decision",
                    "importance": 2, "chapter": "c1", "title": "The timeline starts",
                    "summary": "A live timeline now tracks this work; the keeper adds events as they happen."}],
        "metrics": [],
    }
    if a.budget:
        feed["headline"]["spend"] = {"usd": 0, "budgetUsd": a.budget, "currency": a.currency, "byLane": {}, "asOf": now}
    (live / "events.json").write_text(json.dumps(feed, indent=2, ensure_ascii=False) + "\n")
    cfg_path = live / "keeper/config.json"
    if not cfg_path.exists() or a.force:
        cfg = {
            "sources": ["STATUS.md", "*/STATUS.md", "*/FINDINGS.md"],
            "exclude": ["/private/"],
            "jsonlDropKeys": [],
            "firstPassTail": 25,
            "maxLinesPerSource": 80,
            "t3": {"root": "", "titles": [], "quietAfterMin": 30},
            "spend": {"sources": [], "budgetUsd": a.budget, "currency": a.currency, "step": 100, "lane": lanes[1]["id"] if len(lanes) > 1 else owner_id},
            "deny": {"wordsFromDirs": [], "wordsFile": "", "phrases": []},
            "blockedLinks": "",
        }
        cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    (live / "README.md").write_text(
        f"# live/\n\nFeed for **`../{a.page}`** — {a.title}.\n\n"
        "- `events.json` is the only file the page reads; it reloads every 60 s.\n"
        "- Change it only through `python3 live/patch.py` (patch JSON on stdin), which validates and installs atomically.\n"
        "- `collect.py` prints what changed in the sources since the last pass; `brief.py` writes a progress update.\n"
        "- `SCHEMA.md` has the fields, kinds, style guide and worked examples. `keeper/config.json` lists sources, spend and the deny list.\n")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(live))
    import validate
    errors, warnings, _ = validate.check(live / "events.json")
    print("\n".join(["warn: " + w for w in warnings] + ["error: " + e for e in errors]) or "feed OK")
    print(f"page   {page}\nfeed   {live / 'events.json'}\nconfig {cfg_path}  (fill in sources, t3, spend, deny)")


if __name__ == "__main__":
    main()
