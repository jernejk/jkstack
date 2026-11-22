#!/usr/bin/env python3
"""Apply a story patch (JSON on stdin) to live/events.json, refresh spend, validate, install atomically.

  python3 live/patch.py <<'EOF'
  {"events": [{"ref": "a", "time": "...", "lane": "sol", "kind": "start", ...}],
   "edit": {"e012": {"state": "done"}}, "headline": {"best": {"text": "...", "eventId": "@a"}}}
  EOF

Keys: events, edit, chapters, metrics, lanes ({id: status}), addLanes, headline (merged; null deletes), run (merged).
Sending headline.status stamps its asOf, which collect.py uses to flag a stale status.
New events and chapters get the next id; "@ref" anywhere in the patch resolves to the id given to that ref.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import validate  # noqa: E402

FEED = HERE / "events.json"
NEXT = HERE / "events.next.json"


def now_iso(tz):
    m = re.fullmatch(r"(?:UTC|GMT)?([+-])(\d\d):?(\d\d)", str(tz or ""))
    if m:
        off = timedelta(hours=int(m[2]), minutes=int(m[3])) * (-1 if m[1] == "-" else 1)
        return datetime.now(timezone(off)).isoformat(timespec="seconds")
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds") if tz else datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        return datetime.now().astimezone().isoformat(timespec="seconds")


def next_id(items, prefix, width):
    nums = [int(m[1]) for i in items if (m := re.fullmatch(rf"{prefix}(\d+)", str(i.get("id", ""))))]
    return f"{prefix}{(max(nums) + 1 if nums else 1):0{width}d}"


def chapter_at(chapters, time):
    t = validate.when(time)
    started = [c for c in chapters if c.get("start") and validate.when(c["start"]) <= t]
    return max(started, key=lambda c: validate.when(c["start"]))["id"] if started else chapters[0]["id"]


def resolve(value, refs):
    if isinstance(value, str) and value.startswith("@"):
        if value[1:] not in refs:
            raise SystemExit(f"unknown ref {value}")
        return refs[value[1:]]
    if isinstance(value, list):
        return [resolve(v, refs) for v in value]
    if isinstance(value, dict):
        return {k: resolve(v, refs) for k, v in value.items()}
    return value


def merge(dst, src):
    for k, v in src.items():
        if v is None:
            dst.pop(k, None)
        elif isinstance(v, dict) and isinstance(dst.get(k), dict) and k not in ("best", "status", "progress"):
            merge(dst[k], v)
        else:
            dst[k] = v


def refresh_spend(data, cfg, now):
    spend_cfg = cfg.get("spend") or {}
    sources = spend_cfg.get("sources") or []
    if not sources:
        return
    amounts = {}
    for s in sources:
        p = Path(s["path"]).expanduser()
        p = p if p.is_absolute() else HERE.parent / p
        try:
            m = re.search(s["regex"], p.read_text(errors="replace"))
        except OSError:
            continue
        if m:
            amounts[s["lane"]] = amounts.get(s["lane"], 0) + float(m[1].replace(",", "").rstrip("."))
    if len(amounts) < len({s["lane"] for s in sources}):
        print(f"warn: spend read {len(amounts)} of {len(sources)} sources; headline spend left as it was")
        return
    head = data.setdefault("headline", {})
    old = (head.get("spend") or {}).get("usd") or 0
    total = round(sum(amounts.values()), 2)
    spend = head.setdefault("spend", {})
    spend.update(usd=total, byLane={k: round(v, 2) for k, v in amounts.items()}, asOf=now)
    for k in ("budgetUsd", "currency", "note"):
        if spend_cfg.get(k) is not None:
            spend.setdefault(k, spend_cfg[k])
    if total == old:
        return
    data.setdefault("metrics", []).append({"name": spend_cfg.get("metric", "Spend"), "value": total, "unit": spend.get("currency", "US$"),
                                           "better": "lower", "time": now})
    step = spend_cfg.get("step")
    if step and int(total // step) > int(old // step):
        cur = spend.get("currency", "US$")
        mark = int(total // step) * step
        budget = spend.get("budgetUsd")
        data["events"].append({"id": next_id(data["events"], "e", 3), "time": now, "lane": spend_cfg.get("lane", data["lanes"][0]["id"]),
                               "kind": "spend", "importance": 2, "title": f"Spend passes {cur}{mark:,}",
                               "summary": f"Booked spend is {cur}{total:,.2f}" + (f" of {cur}{budget:,}" if budget else "") + ".",
                               "chapter": data["chapters"][-1]["id"] if data.get("chapters") else None})
        if data["events"][-1]["chapter"] is None:
            data["events"][-1].pop("chapter")


def main():
    cfg = validate.config()
    data = json.loads(FEED.read_text())
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    patch = json.loads(raw) if raw.strip() else {}
    now = now_iso((data.get("run") or {}).get("tz"))
    refs = {}

    new_chapters = []
    for c in patch.get("chapters", []):
        cid = c.get("id") or next_id(data.setdefault("chapters", []), "c", 1)
        if c.get("ref"):
            refs[c.pop("ref")] = cid
        chapter = {**c, "id": cid}
        data["chapters"].append(chapter)
        new_chapters.append(chapter)
    data["lanes"].extend(patch.get("addLanes", []))
    pending = []
    for e in patch.get("events", []):
        eid = next_id(data["events"] + pending, "e", 3)
        own = {eid}
        if e.get("ref"):
            refs[e["ref"]] = eid
            own.add("@" + e.pop("ref"))
        e = {**e, "id": eid}
        e.setdefault("time", now)
        if e.get("kind") == "blocked":
            e.setdefault("state", "open")
        if isinstance(e.get("causedBy"), list):
            e["causedBy"] = [c for c in e["causedBy"] if c not in own] or None
            if e["causedBy"] is None:
                e.pop("causedBy")
        pending.append(e)
    pending = resolve(pending, refs)
    for chapter in new_chapters:
        times = [e["time"] for e in pending if e.get("chapter") == chapter["id"]]
        chapter.setdefault("start", min(times, key=validate.when) if times else now)
    for e in pending:
        if data.get("chapters") and not e.get("chapter"):
            e["chapter"] = chapter_at(data["chapters"], e["time"])
    data["events"].extend(pending)
    for eid, changes in resolve(patch.get("edit", {}), refs).items():
        event = next((e for e in data["events"] if e["id"] == eid), None)
        if not event:
            raise SystemExit(f"edit: no event {eid}")
        event.update(changes)
        event["updated"] = now
    for m in resolve(patch.get("metrics", []), refs):
        source = next((e for e in data["events"] if e["id"] == m.get("event")), None) if m.get("event") else None
        if m.get("event") and not source:
            raise SystemExit(f"metric: no event {m['event']}")
        m = {**m, "time": m.get("time") or (source["time"] if source else now)}
        if source:
            m.setdefault("lane", source["lane"])
        data.setdefault("metrics", []).append(m)
    unknown = set(patch.get("lanes", {})) - {lane["id"] for lane in data["lanes"]}
    if unknown:
        raise SystemExit(f"lanes: no lane {', '.join(sorted(unknown))}; add it with addLanes")
    for lane in data["lanes"]:
        if lane["id"] in patch.get("lanes", {}):
            lane["status"] = patch["lanes"][lane["id"]]
    merge(data.setdefault("headline", {}), resolve(patch.get("headline", {}), refs))
    if (patch.get("headline") or {}).get("status"):
        data["headline"]["status"]["asOf"] = now
    merge(data.setdefault("run", {}), patch.get("run", {}))
    refresh_spend(data, cfg, now)
    data["updated"] = now

    NEXT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    errors, warnings, _ = validate.check(NEXT, cfg)
    new_ids = {e["id"] for e in pending}
    for w in warnings:
        if not re.match(r"e\d+:", w) or w.split(":")[0] in new_ids:
            print("warn:", w)
    if errors:
        for e in errors:
            print("error:", e)
        print(f"FAIL: nothing installed; draft left at {NEXT}")
        sys.exit(1)
    validate.install(NEXT)
    NEXT.unlink()
    blockers = [e["id"] for e in data["events"] if e.get("kind") == "blocked" and e.get("state") != "cleared"]
    running = [e["id"] for e in data["events"] if e.get("kind") == "start" and e.get("state") == "running"]
    print(json.dumps({"installed": True, "events": len(data["events"]), "new": [e["id"] for e in pending], "refs": refs,
                      "running": running, "openBlockers": blockers, "spend": (data.get("headline") or {}).get("spend", {}).get("usd")}))


if __name__ == "__main__":
    main()
