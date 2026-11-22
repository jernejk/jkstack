#!/usr/bin/env python3
"""Apply a story patch (JSON on stdin) to live/events.json, refresh spend, validate, install atomically.

  python3 live/patch.py <<'EOF'
  {"events": [{"ref": "a", "time": "...", "lane": "sol", "kind": "start", ...}],
   "edit": {"e012": {"state": "done"}}, "headline": {"best": {"text": "...", "eventId": "@a"}}}
  EOF

Keys: events, edit, chapters, editChapters ({c4: {digest, keyBeats}}), metrics, lanes ({id: status}), addLanes,
headline (merged; null deletes), run (merged), draft + fill (apply keeper/draft.json from collect.py, then fill/skip its beats).
Sending headline.status stamps its asOf, which collect.py uses to flag a stale status.
New events and chapters get the next id; "@ref" resolves to the id given to that ref, but only where an id belongs: causedBy, supersedes,
chapter, a metric's event, headline.best.eventId, headline.latestBreakthroughId, edit and editChapters keys, keyBeats. A ref declared
twice in one patch is an error.
A start edited to done/failed gets an `end`: the latest event it caused in this patch, else now.
A successful install also commits the pass collect.py staged (keeper/state.next.json -> state.json), stamping the feed with that
pass's batch id. {"draft": true} needs draft.json and state.next.json from the same pass; a patch without it leaves a pending draft
(and the cursor) alone.
"""
import copy
import difflib
import json
import os
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
KEEPER = HERE / "keeper"
DRAFT = KEEPER / "draft.json"
STATE = KEEPER / "state.json"
STAGED = KEEPER / "state.next.json"
FILL_KEYS = {"title", "summary", "causedBy", "importance", "why", "images", "skip"}


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


def ref(value, refs):
    if isinstance(value, str) and value.startswith("@"):
        if value[1:] not in refs:
            raise SystemExit(f"unknown ref {value}")
        return refs[value[1:]]
    if isinstance(value, list):
        return [ref(v, refs) for v in value]
    return value


def fields(item, names, refs):
    return {k: ref(v, refs) if k in names else v for k, v in item.items()}


def declare(refs, name, eid):
    if name in refs:
        raise SystemExit(f"ref {name} is declared twice")
    refs[name] = eid


def batch_of(path):
    try:
        return json.loads(path.read_text()).get("batch")
    except (OSError, ValueError, AttributeError):
        return None


def merge(dst, src):
    for k, v in src.items():
        if v is None:
            dst.pop(k, None)
        elif isinstance(v, dict) and isinstance(dst.get(k), dict) and k not in ("best", "status", "progress"):
            merge(dst[k], v)
        else:
            dst[k] = v


def drop_skipped(draft, skipped):
    tags = {"@" + r for r in skipped}
    by_ref = {e["ref"]: e for e in draft.get("events", []) if e.get("ref") in skipped}
    draft["events"] = [e for e in draft.get("events", []) if e.get("ref") not in skipped]
    for e in draft["events"]:
        if isinstance(e.get("causedBy"), list):
            e["causedBy"] = [c for c in e["causedBy"] if c not in tags]
            if not e["causedBy"]:
                e.pop("causedBy")
    for m in draft.get("metrics", []):
        if m.get("event") in tags:
            src = by_ref[m.pop("event")[1:]]
            m.setdefault("time", src["time"])
            m.setdefault("lane", src["lane"])
    best = (draft.get("headline") or {}).get("best")
    if best and best.get("eventId") in tags:
        best.pop("eventId")
    draft["edit"] = {k: v for k, v in (draft.get("edit") or {}).items() if k not in tags}


def apply_draft(patch):
    try:
        draft = json.loads(DRAFT.read_text())
    except (OSError, ValueError):
        raise SystemExit("draft: no readable live/keeper/draft.json; run collect.py first")
    draft.pop("meta", None)
    if batch_of(DRAFT) != batch_of(STAGED):
        raise SystemExit("draft and cursor are from different passes; run collect.py again")
    draft.pop("batch", None)
    refs = {e["ref"]: e for e in draft.get("events", []) if e.get("ref")}
    skipped = set()
    for ref, fields in (patch.get("fill") or {}).items():
        if ref not in refs:
            raise SystemExit(f"fill: no draft beat {ref}")
        if not isinstance(fields, dict) or set(fields) - FILL_KEYS:
            raise SystemExit(f"fill {ref}: unknown key(s) {', '.join(sorted(set(fields) - FILL_KEYS)) if isinstance(fields, dict) else fields!r}; allowed: {', '.join(sorted(FILL_KEYS))}")
        if fields.get("skip"):
            skipped.add(ref)
            continue
        for k, v in fields.items():
            if k == "images":
                refs[ref]["images"] = (refs[ref].get("images") or []) + list(v)
            elif k != "skip":
                refs[ref][k] = v
    drop_skipped(draft, skipped)
    rest = {k: v for k, v in patch.items() if k not in ("draft", "fill")}
    out = {k: draft.get(k, []) + rest.get(k, []) for k in ("chapters", "addLanes", "events", "metrics")}
    out["edit"] = {k: dict(v) for k, v in (draft.get("edit") or {}).items()}
    for k, v in (rest.get("edit") or {}).items():
        out["edit"].setdefault(k, {}).update(v)
    for k in ("lanes", "headline", "run", "editChapters"):
        out[k] = {}
        for part in (draft.get(k) or {}, rest.get(k) or {}):
            merge(out[k], part)
    return out


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
    used_draft = bool(patch.get("draft"))
    if used_draft:
        patch = apply_draft(patch)
    elif patch.get("fill"):
        raise SystemExit('fill needs {"draft": true}')
    now = now_iso((data.get("run") or {}).get("tz"))
    refs = {}

    new_chapters = []
    for c in patch.get("chapters", []):
        cid = c.get("id") or next_id(data.setdefault("chapters", []), "c", 1)
        if c.get("ref"):
            declare(refs, c.pop("ref"), cid)
        chapter = {**c, "id": cid}
        data["chapters"].append(chapter)
        new_chapters.append(chapter)
    data["lanes"].extend(patch.get("addLanes", []))
    pending = []
    for e in patch.get("events", []):
        eid = next_id(data["events"] + pending, "e", 3)
        own = {eid}
        if e.get("ref"):
            declare(refs, e["ref"], eid)
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
    pending = [fields(e, ("causedBy", "supersedes", "chapter"), refs) for e in pending]
    for chapter in new_chapters:
        if "keyBeats" in chapter:
            chapter["keyBeats"] = ref(chapter["keyBeats"], refs)
    for chapter in new_chapters:
        times = [e["time"] for e in pending if e.get("chapter") == chapter["id"]]
        chapter.setdefault("start", min(times, key=validate.when) if times else now)
    for e in pending:
        if data.get("chapters") and not e.get("chapter"):
            e["chapter"] = chapter_at(data["chapters"], e["time"])
    data["events"].extend(pending)
    for eid, changes in patch.get("edit", {}).items():
        eid, changes = ref(eid, refs), fields(changes, ("causedBy", "supersedes", "chapter"), refs)
        event = next((e for e in data["events"] if e["id"] == eid), None)
        if not event:
            raise SystemExit(f"edit: no event {eid}")
        if event.get("kind") == "start" and event.get("state") == "running" and changes.get("state") in ("done", "failed") \
                and "end" not in changes and "end" not in event:
            caused = [e["time"] for e in pending if eid in (e.get("causedBy") or [])]
            changes = {**changes, "end": max(caused, key=validate.when) if caused else now}
        event.update(changes)
        event["updated"] = now
    for cid, changes in patch.get("editChapters", {}).items():
        cid, changes = ref(cid, refs), fields(changes, ("keyBeats",), refs)
        chapter = next((c for c in data.get("chapters", []) if c["id"] == cid), None)
        if not chapter:
            raise SystemExit(f"editChapters: no chapter {cid}")
        merge(chapter, changes)
    names = {m.get("name") for m in data.get("metrics", [])}
    for m in patch.get("metrics", []):
        name = m.get("name")
        if name and name not in names:
            near = next((n for n in sorted(names, key=str) if n and difflib.SequenceMatcher(None, name, n).ratio() >= 0.8), None)
            if near:
                print(f'warn: metric "{name}" looks like existing "{near}"; keep names identical')
            names.add(name)
    for m in (fields(m, ("event",), refs) for m in patch.get("metrics", [])):
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
    headline = copy.deepcopy(patch.get("headline") or {})
    if isinstance(headline.get("best"), dict):
        headline["best"] = fields(headline["best"], ("eventId",), refs)
    headline = fields(headline, ("latestBreakthroughId",), refs)
    merge(data.setdefault("headline", {}), headline)
    if (patch.get("headline") or {}).get("status"):
        data["headline"]["status"]["asOf"] = now
    merge(data.setdefault("run", {}), patch.get("run", {}))
    refresh_spend(data, cfg, now)
    data["updated"] = now
    pending_draft = DRAFT.exists() and not used_draft
    batch = None if pending_draft else batch_of(STAGED)
    if batch:
        data["batch"] = batch

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
    committed = STAGED.exists() and not pending_draft
    if committed:
        os.replace(STAGED, STATE)
    if used_draft or committed:
        DRAFT.unlink(missing_ok=True)
    if pending_draft:
        print('warn: a lead-log draft is pending; send {"draft": true, …} to apply it')
    blockers = [e["id"] for e in data["events"] if e.get("kind") == "blocked" and e.get("state") != "cleared"]
    running = [e["id"] for e in data["events"] if e.get("kind") == "start" and e.get("state") == "running"]
    print(json.dumps({"installed": True, "events": len(data["events"]), "new": [e["id"] for e in pending], "refs": refs,
                      "running": running, "openBlockers": blockers, "committed": committed, "spend": (data.get("headline") or {}).get("spend", {}).get("usd")}))


if __name__ == "__main__":
    main()
