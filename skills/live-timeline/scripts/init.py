#!/usr/bin/env python3
"""Scaffold a live timeline into a work folder.

  python3 <skill-dir>/scripts/init.py <folder> --title "Audit-risk research night" \
      --owner Owner --lanes "orch:Orchestrator,opus:Opus lane,sol:Sol lane" [--budget 1500] [--tz UTC] [--lead-log LEAD-LOG.md]

Creates <folder>/live-timeline.html and <folder>/live/ (events.json, SCHEMA.md, scripts, keeper/config.json).
Refuses to overwrite an existing timeline unless --force; --upgrade replaces only the page and scripts.
Inside a T3 thread ($T3CODE_THREAD_ID, or --t3-thread ID) it records run.t3 and watches that thread; --no-t3 turns that off.
--upgrade never edits the feed: when run.t3 is missing it prints the patch.py command that adds it.
"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = ["validate.py", "patch.py", "collect.py", "ingest.py", "digest.py", "brief.py", "recent.py", "snap.py"]


def local_tz():
    try:
        link = os.readlink("/etc/localtime")
        return link.split("zoneinfo/")[-1]
    except OSError:
        return ""


def safe_id(value):
    return bool(re.fullmatch(r"[A-Za-z0-9_:%.-]{1,200}", value)) and not re.search(r"\.\.|%2[ef]|%5c", value, re.I)


def t3_detect(a):
    """run.t3 for this thread, and the thread id; (None, None) outside T3 or with --no-t3."""
    thread = None if a.no_t3 else (a.t3_thread or os.environ.get("T3CODE_THREAD_ID") or "").strip()
    if not thread or not safe_id(thread):
        return None, None
    home = Path(os.environ.get("T3CODE_HOME") or Path.home() / ".t3").expanduser()
    try:
        env = (home / "userdata/environment-id").read_text().strip()
    except OSError:
        return None, thread
    return ({"env": env, "thread": thread} if safe_id(env) else None), thread


def now_iso(tz):
    m = re.fullmatch(r"(?:UTC|GMT)?([+-])(\d\d):?(\d\d)", str(tz or ""))
    if m:
        off = timedelta(hours=int(m[2]), minutes=int(m[3])) * (-1 if m[1] == "-" else 1)
        return datetime.now(timezone(off)).isoformat(timespec="seconds")
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
    ap.add_argument("--lead-log", help="lead log path (relative to the work folder): collect.py turns it into a draft patch")
    ap.add_argument("--t3-thread", help="T3 thread id; default $T3CODE_THREAD_ID")
    ap.add_argument("--no-t3", action="store_true", help="don't record run.t3 or watch this T3 thread")
    ap.add_argument("--empty", action="store_true", help="no starter chapter or event, for seeding history that predates the scaffold")
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
    shutil.copyfile(SKILL / "references/lead-log.md", live / "LOG-TAGS.md")
    t3_run, thread = t3_detect(a)
    if a.upgrade and exists:
        print(f"upgraded {page} and {live}/ scripts; events and config untouched")
        try:
            has = "t3" in (json.loads((live / "events.json").read_text()).get("run") or {})
        except (OSError, ValueError):
            has = True
        if t3_run and not has:
            print("run.t3 is missing; add it with:\n  python3 live/patch.py <<'EOF'\n" + json.dumps({"run": {"t3": t3_run}}) + "\nEOF")
        return

    now = now_iso(a.tz)
    owner_id = re.sub(r"[^a-z0-9]+", "", a.owner.lower()) or "owner"
    lanes = [{"id": owner_id, "name": a.owner, "short": a.owner[:8], "status": "running", "human": True}]
    for spec in filter(None, (x.strip() for x in a.lanes.split(","))):
        parts = spec.split(":")
        lid = parts[0].strip().lower()
        if lid == owner_id:
            continue
        name = parts[1].strip() if len(parts) > 1 else lid
        lanes.append({"id": lid, "name": name, "short": (parts[2] if len(parts) > 2 else name.split()[0])[:8], "status": "running"})
    feed = {
        "schema": 2,
        "updated": now,
        "run": {"title": a.title, "owner": a.owner, "tz": a.tz, "start": now, "staleAfterMin": 30, **({"t3": t3_run} if t3_run else {})},
        "headline": {"status": {"tone": "good", "text": "Starting", "note": "Timeline set up", "asOf": now}},
        "lanes": lanes,
        "chapters": [] if a.empty else [{"id": "c1", "title": "Setting out", "start": now, "summary": "What we are trying to do, and how."}],
        "events": [] if a.empty else [{"id": "e001", "time": now, "lane": lanes[1]["id"] if len(lanes) > 1 else owner_id, "kind": "decision",
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
            "maxChars": 8000,
            "statusStaleMin": 20,
            "t3": {"root": thread or "", "titles": [], "quietAfterMin": 30},
            "spend": {"sources": [], "budgetUsd": a.budget, "currency": a.currency, "step": 100, "lane": lanes[1]["id"] if len(lanes) > 1 else owner_id},
            "deny": {"wordsFromDirs": [], "wordsFile": "", "phrases": []},
            "blockedLinks": "",
        }
        if a.lead_log:
            cfg["leadLog"] = a.lead_log
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
