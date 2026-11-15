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
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import validate  # noqa: E402

FEED = HERE / "events.json"
NEXT = HERE / "events.next.json"


def now_iso(tz):
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds") if tz else datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception:
        return datetime.now().astimezone().isoformat(timespec="seconds")


def next_id(items, prefix, width):
    nums = [int(m[1]) for i in items if (m := re.fullmatch(rf"{prefix}(\d+)", str(i.get("id", ""))))]
    return f"{prefix}{(max(nums) + 1 if nums else 1):0{width}d}"


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

    for c in patch.get("chapters", []):
        cid = c.get("id") or next_id(data.setdefault("chapters", []), "c", 1)
        if c.get("ref"):
            refs[c.pop("ref")] = cid
        data["chapters"].append({**c, "id": cid, "start": c.get("start", now)})
    data["lanes"].extend(patch.get("addLanes", []))
    pending = []
    for e in patch.get("events", []):
        eid = next_id(data["events"] + pending, "e", 3)
        if e.get("ref"):
            refs[e.pop("ref")] = eid
        e = {**e, "id": eid}
        e.setdefault("time", now)
        if data.get("chapters"):
            e.setdefault("chapter", data["chapters"][-1]["id"])
        if e.get("kind") == "blocked":
            e.setdefault("state", "open")
        pending.append(e)
    data["events"].extend(resolve(pending, refs))
    for eid, changes in resolve(patch.get("edit", {}), refs).items():
        event = next((e for e in data["events"] if e["id"] == eid), None)
        if not event:
            raise SystemExit(f"edit: no event {eid}")
        event.update(changes)
        event["updated"] = now
    for m in patch.get("metrics", []):
        data.setdefault("metrics", []).append({**m, "time": m.get("time", now)})
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
    for w in warnings:
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
