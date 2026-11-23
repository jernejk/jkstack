#!/usr/bin/env python3
"""Write a progress update from live/events.json — for a check-in, a stakeholder, or a handover.

  python3 live/brief.py                 # since 2 h ago
  python3 live/brief.py --since today   # also: all, 30m, 6h, 2d, or an ISO time
  python3 live/brief.py --blockers      # only what is waiting on the owner
"""
import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

FEED = Path(__file__).resolve().parent / "events.json"
MARK = {"start": "▶", "update": "·", "success": "✓", "breakthrough": "★", "fail": "✕", "blocked": "!", "nudge": "◆",
        "decision": "⬢", "orchestrator": "⬢", "review": "△", "spend": "$", "sealed": "🔒"}


def t(s):
    return datetime.fromisoformat(s)


def options(e):
    labels = [c.get("label", "") if isinstance(c, dict) else c for c in e.get("choices") or []]
    return f" Options: {' / '.join(labels)}." if labels else ""


def since_of(arg, now, start):
    if arg == "all":
        return start
    if arg == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    m = re.fullmatch(r"(\d+)([mhd])", arg)
    if m:
        return now - timedelta(**{{"m": "minutes", "h": "hours", "d": "days"}[m[2]]: int(m[1])})
    return t(arg)


def num(v):
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) >= 1 else f"{v:.3g}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def fmt_metric(m):
    v = num(m["value"])
    if m.get("of") is not None:
        return f"{v}/{m['of']}"
    u = m.get("unit", "")
    return f"{u}{v}" if u.endswith("$") else f"{v}%" if u == "%" else f"{v} {u}".strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2h")
    ap.add_argument("--blockers", action="store_true")
    a = ap.parse_args()
    d = json.loads(FEED.read_text())
    run = d.get("run") or d.get("night") or {}
    ev = sorted(d["events"], key=lambda e: t(e["time"]))
    now = datetime.now(t(ev[-1]["time"]).tzinfo) if ev else datetime.now().astimezone()
    start = t(run["start"]) if run.get("start") else (t(ev[0]["time"]) if ev else now)
    start = min([start] + [t(ev[0]["time"])] if ev else [start])
    since = since_of(a.since, now, start)
    gone = {e["supersedes"] for e in ev if e.get("supersedes")}
    ev = [e for e in ev if e["id"] not in gone]
    blockers = [e for e in ev if e["kind"] in ("blocked", "blocker") and e.get("state") != "cleared"]
    hm = lambda e: t(e["time"]).strftime("%a %H:%M" if (now - start).total_seconds() > 72000 else "%H:%M")

    if a.blockers:
        for e in blockers:
            print(f"! {hm(e)} {e['title']} — {e.get('ask') or e['summary']}{options(e)}  [{e['id']}]")
        if not blockers:
            print("Nothing is waiting on you.")
        return

    h = d.get("headline") or {}
    out = [f"{run.get('title', 'Progress')} — update {now:%a %d %b %H:%M}", ""]
    if (h.get("status") or {}).get("text"):
        out.append(f"Status: {h['status']['text']}" + (f" — {h['status']['note']}" if h["status"].get("note") else ""))
    if (h.get("progress") or {}).get("of"):
        p = h["progress"]
        out.append(f"Progress: {p['value']} of {p['of']} {p.get('label', '')}".rstrip())
    if (h.get("best") or {}).get("text"):
        out.append(f"Best so far: {h['best']['text']}" + (f" ({h['best']['note']})" if h["best"].get("note") else ""))
    beats = [e for e in ev if t(e["time"]) >= since and (e["importance"] >= 2 or e in blockers) and e["kind"] != "spend"]
    out += ["", "What happened:" if a.since == "all" else f"Since {since.strftime('%a %H:%M' if since.date() != now.date() else '%H:%M')}:"]
    line = lambda e: f"- {hm(e)} {MARK.get(e['kind'], '·')} {e['title']} — {e['summary']}"
    chapters = {c["id"]: c for c in d.get("chapters", [])}
    if a.since == "all" and any((chapters.get(e.get("chapter")) or {}).get("digest") for e in beats):
        for cid in dict.fromkeys(e.get("chapter") for e in beats):
            c, inside = chapters.get(cid) or {}, [e for e in beats if e.get("chapter") == cid]
            out.append(f"{c.get('title', 'Other')}:" if c else "Other:")
            if c.get("digest"):
                out.append(f"  {c['digest']}")
            keys = [e for e in inside if e["id"] in c.get("keyBeats", [])] if c.get("digest") and len(inside) > 12 else inside
            if not (c.get("digest") and len(inside) > 12 and not keys):
                out += ["  " + line(e) for e in keys]
    else:
        out += [line(e) for e in beats] or ["- Nothing major; work continues."]
    running = [e for e in ev if e["kind"] == "start" and e.get("state") == "running"]
    if running:
        out += ["", "In progress:"] + [f"- {e['title']} (since {hm(e)})" for e in running]
    if blockers:
        out += ["", "Waiting on a decision:"] + [f"- {e['title']} — {e.get('ask') or e['summary']}{options(e)}" for e in blockers]
    groups = {}
    for m in sorted(d.get("metrics", []), key=lambda m: t(m["time"])):
        groups.setdefault(m["name"], []).append(m)
    groups = {k: v for k, v in groups.items() if a.since == "all" or t(v[-1]["time"]) >= since}
    if groups:
        out += ["", "Measures:" if a.since == "all" else "Measures that moved:"]
        for name, pts in groups.items():
            first = next((p for p in pts if t(p["time"]) >= since), None)
            was = f" (was {fmt_metric(first)})" if first and first is not pts[-1] else ""
            out.append(f"- {name}: {fmt_metric(pts[-1])}{was}" + (f" · {pts[-1]['note']}" if pts[-1].get("note") else ""))
    sp = h.get("spend") or {}
    if sp.get("usd") is not None:
        cur = sp.get("currency", "US$")
        out += ["", f"Spend: {cur}{sp['usd']:,.2f}" + (f" of {cur}{sp['budgetUsd']:,}" if sp.get("budgetUsd") else "")]
    print("\n".join(out))


if __name__ == "__main__":
    main()
