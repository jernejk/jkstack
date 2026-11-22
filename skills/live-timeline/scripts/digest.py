#!/usr/bin/env python3
"""Print every chapter compactly so a model can write the story layer (chapter digests, outcomes, key beats, run digest).

  python3 live/digest.py            # all chapters
  python3 live/digest.py --missing  # only chapters without a digest
  python3 live/digest.py c4         # one chapter

Each chapter block stays near 1.5k tokens: past that, quiet importance-1 updates collapse to a count and summaries shorten.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

LIMIT = 6000


def t(s):
    return datetime.fromisoformat(s)


def clip(text, n):
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def block(c, events):
    span = [t(e["time"]) for e in events] or [t(c["start"])]
    first, last = t(c["start"]) if c.get("start") else min(span), t(c["end"]) if c.get("end") else max(span)
    when = f"{first:%a %H:%M}–{last:%H:%M}" if first.date() == last.date() else f"{first:%a %H:%M}–{last:%a %H:%M}"
    head = f"{c['id']} {c['title']} · {when} · {len(events)} beat{'' if len(events) == 1 else 's'}"
    meta = [f"  {k}: {c[k]}" for k in ("digest", "outcome") if c.get(k)]
    if c.get("keyBeats"):
        meta.append("  keyBeats: " + " ".join(c["keyBeats"]))

    def render(items, width, collapse):
        out, quiet = [], 0
        for e in items:
            if collapse and e["importance"] == 1 and e["kind"] == "update" and e["id"] not in c.get("keyBeats", []):
                quiet += 1
                continue
            state = f" {e['state']}" if e.get("state") else ""
            gist = e["title"] if not width else e["summary"] if e["summary"].startswith(e["title"]) else f"{e['title']} — {e['summary']}"
            out.append(f"  {e['id']} {t(e['time']):%H:%M} {e['lane']} {e['kind']}{state} {e['importance']} · {clip(gist, 40 + width if width else 90)}")
        if quiet:
            out.append(f"  (+{quiet} quiet updates)")
        return out

    for width, collapse in ((140, False), (140, True), (100, True), (60, True), (0, True)):
        lines = [head] + meta + render(events, width, collapse)
        if sum(len(l) + 1 for l in lines) <= LIMIT:
            break
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    data = json.loads((Path(__file__).resolve().parent / "events.json").read_text())
    chapters = sorted(data.get("chapters", []), key=lambda c: c.get("start", ""))
    pick = [a for a in args if not a.startswith("--")]
    if pick:
        chapters = [c for c in chapters if c["id"] in pick]
        if not chapters:
            sys.exit(f"no chapter {', '.join(pick)}")
    if "--missing" in args:
        chapters = [c for c in chapters if not c.get("digest")]
    by = {}
    for e in sorted(data.get("events", []), key=lambda e: e["time"]):
        by.setdefault(e.get("chapter"), []).append(e)
    out = [block(c, by.get(c["id"], [])) for c in chapters]
    if not out:
        print("Every chapter already has a digest." if "--missing" in args else "No chapters.")
        return
    first = chapters[0]["id"]
    shape = ('{"editChapters": {"%s": {"digest": "2–3 plain sentences", "outcome": "one line", "keyBeats": ["e…", ≤4]}}, '
             '"run": {"digest": ["≤3 lines for the whole run"]}}' % first)
    body = "\n\n".join(out)
    print(body)
    print("\nNEXT send one patch like " + shape + " (digest ≤ 700 chars, outcome ≤ 200, keyBeats are ids from that chapter; one entry per chapter above).")
    print(f"SIZE ~{len(body):,} chars (~{len(body) // 4:,} tokens) for {len(chapters)} chapter{'' if len(chapters) == 1 else 's'}")


if __name__ == "__main__":
    main()
