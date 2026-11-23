#!/usr/bin/env python3
"""Turn new lead-log lines into a draft patch with no model: dates, lanes, kinds, tags, metrics, images, chapters.

  python3 live/ingest.py --dry-run          # compact draft for the lines collect.py would show next; writes nothing
  python3 live/ingest.py --dry-run --all    # replay the whole log against an empty story

collect.py calls parse() when config has "leadLog"; the keeper only adds titles and causedBy (patch.py {"draft": true, "fill": {...}}).
"""
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import validate  # noqa: E402

BEAT = re.compile(r"^-\s+(\d{1,2}):(\d\d)\s+\(([^)/]+?)(?:/([^)]+))?\)\s*(.*)$")
TAG = re.compile(r"\[([A-Za-z][\w-]*)(?::((?:[^\[\]]|\[[^\[\]]*\])*))?\](?!\()")
CODE = re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)")
KNOWN = {"start", "result", "fail", "breakthrough", "decision", "nudge", "review", "blocked", "blocker", "ask", "cleared", "done",
         "metric", "status", "progress", "best", "chapter", "end", "key", "img", "snap", "thread", "model", "date"}
NEEDS_ARG = {"blocker", "img", "snap", "done", "metric", "chapter", "status", "progress", "best", "date", "thread", "model", "ask"}
NO_EVENT = {"status", "progress", "best", "metric", "done", "cleared", "date"}
KIND_TAGS = [("blocked", "blocked"), ("blocker", "blocked"), ("ask", "blocked"), ("breakthrough", "breakthrough"), ("fail", "fail"),
             ("review", "review"), ("nudge", "nudge"), ("decision", "decision"), ("result", "success"), ("start", "start")]
TONES = ("good", "warn", "bad", "done")
NUM = r"-?[\d,]*\.?\d+"
PUNCT = ".,;:!?…—–-"


def bare(m):
    return m[1].lower() in NEEDS_ARG and not (m[2] or "").strip()


def tags_in(text):
    spans = [m.span() for m in CODE.finditer(text)]
    return [m for m in TAG.finditer(text) if not any(a <= m.start() < b for a, b in spans)]


def tag_iter(text):
    return (m for m in tags_in(text) if not bare(m))


def complete_lines(text):
    """Lines of a log, leaving out a last line that has no newline yet: it may still be mid-write."""
    lines = text.splitlines()
    return lines[:-1] if lines and not text.endswith(("\n", "\r")) else lines


def num(text):
    t = text.replace(",", "")
    return float(t) if "." in t else int(t)


def zone(header, run):
    m = re.search(r"UTC\s*([+-])(\d{1,2})(?::?(\d\d))?", header)
    if m:
        return timezone((1 if m[1] == "+" else -1) * timedelta(hours=int(m[2]), minutes=int(m[3] or 0)))
    tz = str(run.get("tz") or "")
    m = re.fullmatch(r"(?:UTC|GMT)?([+-])(\d{1,2}):?(\d\d)?", tz)
    if m:
        return timezone((1 if m[1] == "+" else -1) * timedelta(hours=int(m[2]), minutes=int(m[3] or 0)))
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz) if tz else datetime.now().astimezone().tzinfo
    except Exception:
        return datetime.now().astimezone().tzinfo


def parse_metric(text):
    if "=" not in text:
        return None
    name, raw = (x.strip() for x in text.split("=", 1))
    if not name or not raw:
        return None
    m = re.fullmatch(rf"([A-Za-z]{{0,3}}\$)\s*({NUM})", raw)
    if m:
        return {"name": name, "value": num(m[2]), "unit": m[1]}
    m = re.fullmatch(rf"({NUM})\s*(?:/|of)\s*({NUM})", raw)
    if m:
        return {"name": name, "value": num(m[1]), "of": num(m[2])}
    m = re.fullmatch(rf"({NUM})\s*/\s*(\d+)\s*", raw)
    if m:
        return {"name": name, "value": num(m[1]), "of": int(m[2])}
    m = re.fullmatch(rf"({NUM})\s*(\S.*)?", raw)
    if m:
        out = {"name": name, "value": num(m[1])}
        if m[2]:
            out["unit"] = m[2].strip()
        return out
    return {"name": name, "value": raw}


def thumb(path, hhmm, day, make):
    """Return an `images` entry for [img: path | caption], or (None, reason)."""
    src = ROOT / path
    if not validate.safe_image_path(path) or validate.private_path(src, ROOT):
        return None, f"refused image {path}"
    if not src.is_file():
        return None, f"missing image {path}"
    fp = hashlib.sha1(f"{path}|{day}".encode()).hexdigest()[:6]
    rel = f"live/thumbs/{hhmm}-{src.stem}-{fp}.jpg"
    out = ROOT / rel
    if out.exists() or not make:
        return {"path": rel, "full": path}, None
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        if shutil.which("sips") and sys.platform == "darwin":
            subprocess.run(["sips", "-Z", "640", "-s", "format", "jpeg", str(src), "--out", str(out)], check=True, capture_output=True, timeout=30)
        else:
            from PIL import Image
            with Image.open(src) as im:
                im = im.convert("RGB")
                im.thumbnail((640, 640))
                im.save(out, "JPEG", quality=85)
        return {"path": rel, "full": path}, None
    except Exception:
        out.unlink(missing_ok=True)
        return {"path": path}, None


def not_after(start, stamp):
    try:
        return validate.when(start["time"]) <= validate.when(stamp)
    except (KeyError, ValueError):
        return True


def title_of(summary):
    return " ".join(summary.split()[:8]).rstrip(PUNCT) or summary[:40]


def parse(lines, header, feed, cfg, state, thumbs=True):
    """(patch, unparsed, notes, state) for new lead-log lines; meta (for the print) rides in patch["meta"]."""
    feed, state = feed or {}, state or {}
    run = feed.get("run") or {}
    head = "\n".join(header)
    tz = zone(head, run)
    m = re.search(r"\((\d{4}-\d\d-\d\d)", head)
    day0 = datetime.strptime(m[1] if m else str(run.get("start", ""))[:10] or datetime.now().date().isoformat(), "%Y-%m-%d").date()
    prev = datetime.fromisoformat(state["last"]) if state.get("last") else None
    lanes = {l["id"]: l for l in feed.get("lanes", []) if isinstance(l, dict) and l.get("id")}
    owner = next((i for i, l in lanes.items() if l.get("human")), None)
    notes, unparsed, added = [], [], []
    patch = {"events": [], "edit": {}, "metrics": [], "chapters": [], "addLanes": [], "headline": {}, "run": {}}
    meta = {"snaps": {}, "src": {}}
    skip_header = {h.strip() for h in header}
    replaced = {e["supersedes"] for e in feed.get("events", []) if e.get("supersedes")}
    live = [e for e in feed.get("events", []) if e.get("id") not in replaced]
    open_starts = [{"id": e["id"], "lane": e["lane"], "title": e.get("title", ""), "summary": e.get("summary", ""), "time": e.get("time", "")}
                   for e in live if e.get("kind") == "start" and e.get("state") == "running"]
    open_blocks = [{"id": e["id"], "lane": e["lane"], "time": e.get("time", "")}
                   for e in live if e.get("kind") == "blocked" and e.get("state", "open") != "cleared"]
    beats, seen_beat, grouping = [], False, False
    for line in lines:
        b = BEAT.match(line)
        if b:
            seen_beat = grouping = True
            beats.append([b, [b[5]], [line]])
        elif not line.strip():
            continue
        elif line[:1].isspace() and grouping:
            beats[-1][1].append(re.sub(r"^\s*[-*]\s+", "", line.strip()))
            beats[-1][2].append(line)
        elif not seen_beat and line.strip() in skip_header:
            continue
        else:
            unparsed.append(line)
            grouping = False
    n_ev = n_ch = 0
    day = prev.date() if prev else day0
    for b, parts, raws in beats:
        h, mi = int(b[1]), int(b[2])
        raw_text = " ".join(parts)
        tags = [(t[1].lower(), (t[2] or "").strip()) for t in tag_iter(raw_text)]
        new_day = None
        try:
            if h > 23 or mi > 59:
                raise ValueError(f"time {h:02d}:{mi:02d}")
            for name, val in tags:
                if name == "date":
                    try:
                        new_day = datetime.strptime(val, "%Y-%m-%d").date()
                    except ValueError:
                        raise ValueError(f"[date: {val}]") from None
        except ValueError as exc:
            unparsed.extend(raws)
            notes.append(f"invalid {exc} on beat \"{b[0][:40]}\"; left unparsed")
            continue
        if new_day:
            day, prev = new_day, None
        at = datetime(day.year, day.month, day.day, h, mi, tzinfo=tz)
        late = False
        if prev is not None:
            if at < prev - timedelta(hours=6):
                day += timedelta(days=1)
                at = at.replace(year=day.year, month=day.month, day=day.day)
            elif at > prev + timedelta(hours=18):
                at -= timedelta(days=1)
                late = True
        if not late:
            prev = at
        stamp = at.isoformat(timespec="seconds")
        hhmm = f"{h:02d}{mi:02d}"
        names = {n for n, _ in tags}
        arg = {}
        for n, v in tags:
            arg.setdefault(n, v)
        kept, end = [], 0
        for m in tag_iter(raw_text):
            if m[1].lower() in KNOWN:
                kept.append(raw_text[end:m.start()])
                end = m.end()
        text = "".join(kept) + raw_text[end:]
        for n, v in tags:
            if n not in KNOWN:
                notes.append(f"unknown tag [{n}] on {h:02d}:{mi:02d} line")
        text = " ".join(text.split())

        slot = b[3].strip()
        lane = next((i for i in lanes if i == slot), None) or next(
            (i for i, l in lanes.items() if slot.lower() in (i.lower(), str(l.get("name", "")).lower(), str(l.get("short", "")).lower())), None)
        if not lane and "nudge" in names and owner:
            lane = owner
        if not lane:
            lane = slot
            lanes[lane] = {"id": lane}
            patch["addLanes"].append({"id": lane, "name": lane.title(), "short": lane[:8], "status": "running"})
            notes.append(f"NEW LANE {lane}")
        model = (arg.get("model") or (b[4] or "")).strip()[:32] or None
        kind = next((k for t, k in KIND_TAGS if t in names), "update")
        if kind == "nudge" and owner and lane != owner:
            lane = owner
        makes_event = not tags or bool({m[1].lower() for m in tags_in(raw_text)} - NO_EVENT)
        ev = None
        ref = None
        if makes_event:
            n_ev += 1
            ref = f"d{n_ev}"
            ask = arg.get("blocked") or arg.get("blocker") or None
            choices = None
            if "ask" in names:
                q, *opts = [x.strip() for x in arg["ask"].split("|")]
                ask = q or None
                if 2 <= len(opts) <= 6 and all(opts):
                    choices = [o[:80] for o in opts]
                elif opts:
                    notes.append(f"ask on {h:02d}:{mi:02d} needs 2 to 6 choices; kept the question only")
            summary = text
            ch_title = ch_sum = None
            if "chapter" in names:
                ch_title, ch_sum = split_chapter(arg["chapter"])
            captions = [(m2[2] or "").partition("|")[2].strip() for m2 in tag_iter(raw_text) if m2[1].lower() == "img"]
            summary = summary or ch_sum or ch_title or ask or next((c for c in captions if c), "") or ("The run ends." if "end" in names else "No text.")
            importance = 3 if (kind in ("breakthrough", "blocked") or "key" in names) else (1 if kind == "update" else 2)
            ev = {"ref": ref, "time": stamp, "lane": lane, "kind": kind, "importance": importance,
                  "title": title_of(ch_title if ch_title and not text else summary), "summary": summary}
            if kind == "start":
                ev["state"] = "running"
            if ask:
                ev["ask"] = ask
            if choices:
                ev["choices"] = choices
            if model:
                ev["model"] = model
            if arg.get("thread") is not None:
                if validate.valid_id(arg["thread"]):
                    ev["thread"] = arg["thread"]
                else:
                    notes.append(f"bad [thread:] on {h:02d}:{mi:02d} line")
            images = []
            for m2 in tag_iter(raw_text):
                if m2[1].lower() != "img":
                    continue
                path, _, caption = (m2[2] or "").partition("|")
                if len(images) >= 8:
                    notes.append(f"more than 8 images on {h:02d}:{mi:02d} line; extra skipped")
                    break
                entry, why = thumb(path.strip(), hhmm, stamp[:10], thumbs)
                if why:
                    notes.append(f"{why} on {h:02d}:{mi:02d} line")
                    continue
                if caption.strip():
                    entry["caption"] = caption.strip()
                images.append(entry)
            if images:
                ev["images"] = images
            if "snap" in names:
                meta["snaps"][ref] = arg["snap"]
            patch["events"].append(ev)
            if kind == "start":
                open_starts.append({"id": "@" + ref, "lane": lane, "title": ev["title"], "summary": summary, "time": stamp})
            if kind == "blocked":
                open_blocks.append({"id": "@" + ref, "lane": lane, "time": stamp})
            if "chapter" in names:
                n_ch += 1
                cref = f"k{n_ch}"
                ch = {"ref": cref, "title": ch_title, "start": stamp}
                if ch_sum:
                    ch["summary"] = ch_sum
                patch["chapters"].append(ch)
                ev["chapter"] = "@" + cref
        elif "chapter" in names:
            n_ch += 1
            t, s = split_chapter(arg["chapter"])
            patch["chapters"].append({"ref": f"k{n_ch}", "title": t, **({"summary": s} if s else {}), "start": stamp})

        if "done" in names:
            target, tie = match_start(arg["done"], [x for x in open_starts if not (ev and x["id"] == "@" + ev["ref"]) and not_after(x, stamp)], lane)
            if target:
                patch["edit"].setdefault(target["id"], {}).update(state="done", end=stamp)
                meta["src"][target["id"]] = f"done: {arg['done']}"
                open_starts.remove(target)
            else:
                notes.append(f"{'AMBIGUOUS' if tie else 'UNMATCHED'} done: {arg['done']}")
        elif kind == "review":
            target = max((s for s in open_starts if s["lane"] == lane and not_after(s, stamp)), key=lambda s: s["time"], default=None)
            if target and not (ev and target["id"] == "@" + ev["ref"]):
                patch["edit"].setdefault(target["id"], {}).update(state="done", end=stamp)
                open_starts.remove(target)
        if "cleared" in names:
            pool = [x for x in open_blocks if not (ev and x["id"] == "@" + ev["ref"])]
            target = max((x for x in pool if x["lane"] == lane or lane == owner), key=lambda x: x["time"], default=None)
            if target:
                patch["edit"].setdefault(target["id"], {})["state"] = "cleared"
                open_blocks.remove(target)
            else:
                notes.append(f"UNMATCHED cleared on {h:02d}:{mi:02d} line")
        if "metric" in names:
            for m2 in tag_iter(raw_text):
                if m2[1].lower() != "metric":
                    continue
                metric = parse_metric((m2[2] or "").strip())
                if not metric:
                    notes.append(f"bad [metric:] on {h:02d}:{mi:02d} line")
                    continue
                if ev:
                    metric["event"] = "@" + ev["ref"]
                else:
                    metric.update(time=stamp, lane=lane)
                patch["metrics"].append(metric)
        if "status" in names:
            first, _, rest = arg["status"].partition(" ")
            if first.lower() in TONES:
                patch["headline"]["status"] = {"tone": first.lower(), "text": rest.strip() or first}
            else:
                patch["headline"]["status"] = {"tone": "good", "text": arg["status"]}
                notes.append(f"[status:] on {h:02d}:{mi:02d} has no tone; used good")
        if "progress" in names:
            pm = re.fullmatch(rf"({NUM})\s*(?:/|of)\s*({NUM})\s*(.*)", arg["progress"])
            if pm:
                patch["headline"]["progress"] = {"value": num(pm[1]), "of": num(pm[2]), "label": pm[3].strip()}
            else:
                notes.append(f"bad [progress:] on {h:02d}:{mi:02d} line")
        if "best" in names:
            patch["headline"]["best"] = {"text": arg["best"], **({"eventId": "@" + ev["ref"]} if ev else {})}
        if "end" in names:
            patch["run"]["done"] = True
            if "status" not in names:
                patch["headline"]["status"] = {"tone": "done", "text": "Finished"}
    for key in [k for k, v in patch.items() if not v]:
        del patch[key]
    patch["meta"] = meta
    return patch, unparsed, notes, {**state, "last": prev.isoformat(timespec="seconds") if prev else state.get("last")}


def split_chapter(text):
    for sep in (" — ", " – ", " - ", ":"):
        if sep in text:
            t, s = text.split(sep, 1)
            return t.strip(), s.strip()
    return text.strip(), ""


def match_start(arg, starts, lane):
    arg = arg.strip()
    exact = next((s for s in starts if s["id"] == arg), None)
    if exact:
        return exact, False
    low = arg.lower()

    words = set(re.findall(r"[a-z0-9][a-z0-9.-]*", low)) - {"lane", "the", "and", "of", "a"}

    def score(s):
        text = (s["title"] + " " + s["summary"]).lower()
        overlap = len(words & set(re.findall(r"[a-z0-9][a-z0-9.-]*", text))) / len(words) if words else 0
        return max(overlap, difflib.SequenceMatcher(None, low, s["title"].lower()).ratio(),
                   difflib.SequenceMatcher(None, low, s["summary"].lower()[:len(low) + 8]).ratio())
    good = [(r, s) for r, s in ((score(s), s) for s in starts) if r >= 0.6]
    same = [(r, s) for r, s in good if s["lane"] == lane]
    pool = sorted(same or good, key=lambda x: (round(x[0], 2), x[1]["time"]), reverse=True)
    if not pool:
        return None, False
    if not same and len(pool) > 1 and pool[0][0] - pool[1][0] <= 0.05:
        return None, True
    return pool[0][1], False


def shown(m):
    v, u = m["value"], m.get("unit", "")
    return f"{u}{v}" if u.endswith("$") else f"{v}{'/' + str(m['of']) if 'of' in m else ''}{u}"


def clip(text, n):
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def render(label, patch, unparsed, notes):
    """Compact draft for the keeper model."""
    meta = patch.get("meta") or {}
    events = patch.get("events", [])
    out = [f'DRAFT from {label}: {len(events)} beat{"" if len(events) == 1 else "s"} (patch.py applies it with {{"draft": true}}; you add titles and causedBy)']
    last_day = None
    for e in events:
        t = datetime.fromisoformat(e["time"])
        stamp = t.strftime("%a %H:%M") if last_day not in (None, t.date()) else t.strftime("%H:%M")
        last_day = t.date()
        kind = e["kind"] + (f" {e['state']}" if e.get("state") else "")
        imp = f" imp{e['importance']}" if not (e["kind"] == "start" and e["importance"] == 2) else ""
        tail = ""
        for m in patch.get("metrics", []):
            if m.get("event") == "@" + e["ref"]:
                tail += f" [metric {m['name']}={shown(m)}]"
        if e.get("images"):
            tail += f" [img {len(e['images'])}]"
        if e.get("choices"):
            tail += " choices: " + " | ".join(e["choices"])
        if e["ref"] in meta.get("snaps", {}):
            tail += f"  [snap: {clip(meta['snaps'][e['ref']], 90)}]  ← run the snapshot command, add its images via fill"
        who = e["lane"] + (f"/{e['model']}" if e.get("model") else "")
        out.append(f"  {e['ref']} {stamp} {who} {kind}{imp} · {clip(e['summary'], 160)}{tail}")
    edits = []
    for key, ch in (patch.get("edit") or {}).items():
        src = (meta.get("src") or {}).get(key)
        edits.append(f"{key.lstrip('@')} → {ch.get('state')}" + (f" (from [{src}])" if src else ""))
    if edits:
        out.append("  edits: " + " · ".join(edits))
    for c in patch.get("chapters", []):
        out.append(f'  chapter: "{c["title"]}{" — " + c["summary"] if c.get("summary") else ""}" starts {c["start"][11:16]}')
    h = patch.get("headline") or {}
    bits = []
    if h.get("status"):
        bits.append(f'status {h["status"]["tone"]} "{h["status"]["text"]}"')
    if h.get("progress"):
        bits.append(f'progress {h["progress"]["value"]}/{h["progress"]["of"]} {h["progress"].get("label", "")}'.rstrip())
    if h.get("best"):
        bits.append(f'best "{clip(h["best"]["text"], 80)}"')
    if (patch.get("run") or {}).get("done"):
        bits.append("run ends")
    if bits:
        out.append("  headline: " + " · ".join(bits))
    orphan = [m for m in patch.get("metrics", []) if "event" not in m]
    if orphan:
        out.append("  metrics: " + " · ".join(f"{m['name']}={shown(m)}" for m in orphan))
    if patch.get("addLanes"):
        out.append("  new lanes: " + ", ".join(l["id"] for l in patch["addLanes"]))
    for n in notes:
        out.append("  note: " + n)
    if unparsed:
        out += ["UNPARSED (handle by hand):"] + ["  " + clip(l, 300) for l in unparsed]
    if events:
        refs = ", ".join(f'"{e["ref"]}": {{"title": "…", "causedBy": ["e…"]}}' for e in events[:2])
        out.append('NEXT send {"draft": true, "fill": {' + refs + ', …}}. Titles ≤ 8 words. causedBy: results → their start or nudge only. '
                   'Skip a beat with {"skip": true}.')
    return "\n".join(out)


def split_header(lines):
    for i, l in enumerate(lines):
        if BEAT.match(l):
            return lines[:i]
    return list(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Compact draft of the lead log's new lines; writes nothing.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true", help="the whole log, against an empty story")
    a = ap.parse_args()
    import collect
    cfg = collect.load_config()
    lead = collect.lead_log(cfg, say=True)
    if not lead:
        sys.exit('no usable "leadLog" in keeper/config.json')
    key, path = lead
    lines = complete_lines(path.read_text(errors="replace"))
    try:
        feed = json.loads((HERE / "events.json").read_text())
    except (OSError, ValueError):
        feed = {}
    state = {}
    if a.all:
        feed = {**feed, "events": []}
        new = lines
    else:
        old = collect.load_state()
        state = old.get("ingest", {})
        new = [l for l, _ in collect.new_lines(lines, old.get("files", {}).get(key, {}))]
    patch, unparsed, notes, _ = parse(new, split_header(lines), feed, cfg, state, thumbs=False)
    print(render(key, patch, unparsed, notes))
    print(f"\n{len([l for l in new if BEAT.match(l)])} beat lines read, {len(patch.get('events', []))} events, {len(unparsed)} unparsed")


if __name__ == "__main__":
    main()
