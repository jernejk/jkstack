#!/usr/bin/env python3
"""The feed at a glance for a keeper: chapters, the latest events, what is still open, status and lanes.

  python3 live/recent.py        # the last 12 events
  python3 live/recent.py 30

Cheaper than reading events.json: a keeper needs ids and titles to link `causedBy` and close starts, not every field.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

data = json.loads((Path(__file__).resolve().parent / "events.json").read_text())
n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
replaced = {e.get("supersedes") for e in data.get("events", [])}
events = [e for e in data.get("events", []) if e["id"] not in replaced]
print("CHAPTERS " + " · ".join(f"{c['id']} {c['title']}" for c in data.get("chapters", [])))
for e in events[-n:]:
    print(f"{e['id']} {e.get('time', '')[11:16]} {e['lane']} {e['kind']}{' ' + e['state'] if e.get('state') else ''} · {e['title']}")
still = [e for e in events if (e["kind"] == "start" and e.get("state") == "running")
         or (e["kind"] == "blocked" and e.get("state", "open") == "open")]
print("OPEN " + (" · ".join(f"{e['id']} {e['title']}" + (f" ({e['model']})" if e.get("model") and e["kind"] == "start" else "") for e in still) or "none"))
status = data.get("headline", {}).get("status", {})
print(f"STATUS {status.get('tone', '')}: {status.get('text', '')} · {status.get('note', '')} · set {(status.get('asOf') or '')[11:16] or 'never'}")
print("LANES " + " ".join(f"{l['id']}:{l.get('status', '')}" for l in data.get("lanes", [])))
busy = {e["lane"] for e in still}
limit = (data.get("run") or {}).get("staleAfterMin", 30)
now = datetime.now(timezone.utc)
recent = set()
for e in events:
    try:
        if (now - datetime.fromisoformat(e["time"])).total_seconds() / 60 <= limit:
            recent.add(e["lane"])
    except (KeyError, ValueError):
        pass
lanes = [l for l in data.get("lanes", []) if not l.get("human")]
over = (data.get("run") or {}).get("done")
active = [] if over else [l["id"] for l in lanes if l.get("status") not in ("done", "failed", "paused", "idle") and l["id"] in busy | recent]
print("ACTIVE " + (" ".join(active) or "none") + f" (an open start or blocker, or an event in the last {limit} min)")
idle = [l["id"] for l in lanes if l.get("status") == "running" and l["id"] not in active]
if idle:
    print("NOT ACTIVE (marked running): " + " ".join(idle) + ". Send lanes {id: \"done\"} only when the log says the lane finished.")
