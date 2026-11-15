#!/usr/bin/env python3
"""The feed at a glance for a keeper: chapters, the latest events, what is still open, status and lanes.

  python3 live/recent.py        # the last 12 events
  python3 live/recent.py 30

Cheaper than reading events.json: a keeper needs ids and titles to link `causedBy` and close starts, not every field.
"""
import json
import sys
from pathlib import Path

data = json.loads((Path(__file__).resolve().parent / "events.json").read_text())
n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
events = data.get("events", [])
print("CHAPTERS " + " · ".join(f"{c['id']} {c['title']}" for c in data.get("chapters", [])))
for e in events[-n:]:
    print(f"{e['id']} {e.get('time', '')[11:16]} {e['lane']} {e['kind']}{' ' + e['state'] if e.get('state') else ''} · {e['title']}")
still = [e for e in events if (e["kind"] == "start" and e.get("state", "running") == "running")
         or (e["kind"] == "blocked" and e.get("state", "open") == "open")]
print("OPEN " + (" · ".join(f"{e['id']} {e['title']}" for e in still) or "none"))
status = data.get("headline", {}).get("status", {})
print(f"STATUS {status.get('tone', '')}: {status.get('text', '')} · {status.get('note', '')} · set {(status.get('asOf') or '')[11:16] or 'never'}")
print("LANES " + " ".join(f"{l['id']}:{l.get('status', '')}" for l in data.get("lanes", [])))
