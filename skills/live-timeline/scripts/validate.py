#!/usr/bin/env python3
"""Check a timeline feed; with --install, swap it into live/events.json atomically.

  python3 live/validate.py live/events.next.json --install
  python3 live/validate.py                      # checks live/events.json
"""
import contextlib
import json
import os
import re
import sys
from urllib.parse import urlsplit
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "events.json"
CONFIG = HERE / "keeper" / "config.json"
KINDS = {"start", "update", "success", "breakthrough", "fail", "blocked", "nudge", "decision", "review", "spend", "sealed",
         "orchestrator"}
STATES = {"start": {"running", "done", "failed"}, "blocked": {"open", "cleared"}}
BASE_BLOCKED = r"(^|/)private/|^/|^~|^file:|\.\./"
GENERIC = {"the", "and", "pty", "ltd", "inc", "group", "holdings", "trust", "family", "fund", "funds", "test", "data"}


def config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def deny_terms(cfg):
    deny = cfg.get("deny") or {}
    words, phrases = set(), {p.lower() for p in deny.get("phrases", [])}
    for d in deny.get("wordsFromDirs", []):
        try:
            names = [p.name for p in Path(d).expanduser().iterdir() if p.is_dir()]
        except OSError:
            continue
        for n in names:
            words |= {w.lower() for w in re.findall(r"[A-Za-z]{4,}", n) if w.lower() not in GENERIC}
    f = deny.get("wordsFile")
    if f:
        try:
            for line in Path(f).expanduser().read_text().splitlines():
                if line.strip() and not line.startswith("#"):
                    (phrases if " " in line.strip() else words).add(line.strip().lower())
        except OSError:
            pass
    return words, phrases


def when(value):
    t = datetime.fromisoformat(str(value))
    if t.tzinfo is None:
        raise ValueError("no UTC offset")
    return t


EVENT_KEYS = {"id", "time", "lane", "kind", "importance", "chapter", "title", "summary", "why", "ask", "detail", "numbers",
              "links", "images", "causedBy", "state", "supersedes", "updated", "model", "thread", "end", "choices"}
ID_RE = re.compile(r"[A-Za-z0-9_:%.-]{1,200}")


def safe_image_path(value):
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    if any(c in value for c in "\\%?#") or value.startswith(("/", "~")):
        return False
    parsed = urlsplit(value)
    return not parsed.scheme and not parsed.netloc and not any(p.lower() in ("..", "private") for p in value.split("/"))


def check(path, cfg=None):
    cfg = config() if cfg is None else cfg
    errors, warnings = [], []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"not valid JSON: {exc}"], warnings, None
    if not isinstance(data.get("events"), list):
        return ["top-level 'events' must be a list"], warnings, data

    blocked = re.compile(BASE_BLOCKED + ("|" + cfg["blockedLinks"] if cfg.get("blockedLinks") else ""), re.I)
    lanes = {l.get("id") for l in data.get("lanes", []) if isinstance(l, dict)}
    chapters = {c.get("id") for c in data.get("chapters", []) if isinstance(c, dict)}
    ids, times = set(), {}
    for e in data["events"]:
        if isinstance(e, dict) and e.get("id"):
            with contextlib.suppress(Exception):
                times[e["id"]] = when(e.get("time"))
            if e["id"] in ids:
                errors.append(f"duplicate id {e['id']}")
            ids.add(e["id"])

    for e in data["events"]:
        if not isinstance(e, dict):
            errors.append("an event is not an object")
            continue
        eid, kind = e.get("id", "?"), e.get("kind")
        for field in ("id", "time", "lane", "kind", "importance", "title", "summary"):
            if e.get(field) in (None, ""):
                errors.append(f"{eid}: missing {field}")
        try:
            when(e.get("time"))
        except Exception:
            errors.append(f"{eid}: time must be ISO 8601 with a UTC offset")
        if kind not in KINDS:
            errors.append(f"{eid}: unknown kind {kind!r}")
        if e.get("importance") not in (1, 2, 3):
            errors.append(f"{eid}: importance must be 1, 2 or 3")
        if e.get("lane") not in lanes:
            errors.append(f"{eid}: lane {e.get('lane')!r} is not in 'lanes'")
        if e.get("chapter") and e["chapter"] not in chapters:
            errors.append(f"{eid}: chapter {e['chapter']!r} is not in 'chapters'")
        if len(str(e.get("title", "")).split()) > 8:
            errors.append(f"{eid}: title is over 8 words")
        if "\n" in str(e.get("summary", "")):
            errors.append(f"{eid}: summary must be one line")
        for c in e.get("causedBy", []) or []:
            if c not in ids:
                errors.append(f"{eid}: causedBy {c!r} does not exist")
            elif c == eid:
                warnings.append(f"{eid}: causedBy cites itself")
            elif c in times and eid in times and times[c] > times[eid]:
                warnings.append(f"{eid}: causedBy {c} happened later")
        for key in set(e) - EVENT_KEYS:
            warnings.append(f"{eid}: unknown field {key!r}")
        if e.get("supersedes") and e["supersedes"] not in ids:
            errors.append(f"{eid}: supersedes {e['supersedes']!r} does not exist")
        if e.get("state"):
            allowed = STATES.get(kind)
            if not allowed or e["state"] not in allowed:
                errors.append(f"{eid}: state is only for start (running/done/failed) or blocked (open/cleared)")
        if kind == "blocked" and not e.get("ask"):
            warnings.append(f"{eid}: blocked without 'ask' — say what the owner must do")
        if "model" in e and not (isinstance(e["model"], str) and 0 < len(e["model"]) <= 32):
            errors.append(f"{eid}: model must be text of 32 characters or fewer")
        if "thread" in e and not (isinstance(e["thread"], str) and ID_RE.fullmatch(e["thread"])):
            errors.append(f"{eid}: thread must be a T3 thread id (letters, digits, _ : % . -; up to 200)")
        if "end" in e:
            if kind != "start":
                errors.append(f"{eid}: end is only for start events")
            try:
                if when(e["end"]) < when(e.get("time")):
                    warnings.append(f"{eid}: end is before time")
            except Exception:
                errors.append(f"{eid}: end must be ISO 8601 with a UTC offset")
        if "choices" in e:
            c = e["choices"]
            if kind != "blocked":
                errors.append(f"{eid}: choices are only for blocked events")
            if not (isinstance(c, list) and 2 <= len(c) <= 6 and all(isinstance(x, str) and 0 < len(x) <= 80 for x in c)):
                errors.append(f"{eid}: choices must be 2 to 6 strings of 80 characters or fewer")
        for link in e.get("links", []) or []:
            if blocked.search(str(link.get("path", ""))):
                errors.append(f"{eid}: link {link.get('path')!r} points somewhere the page must not show")
        images = e.get("images", [])
        if not isinstance(images, list):
            errors.append(f"{eid}: images must be a list")
            images = []
        for image in images:
            if not isinstance(image, dict):
                errors.append(f"{eid}: image must be an object")
                continue
            if not safe_image_path(image.get("path")) or (image.get("full") is not None and not safe_image_path(image["full"])):
                errors.append(f"{eid}: image paths must stay in the reviewed preview directory")
            if "caption" in image and not isinstance(image["caption"], str):
                errors.append(f"{eid}: image caption must be text")
        if kind == "sealed" and (e.get("detail") or e.get("numbers") or e.get("links") or e.get("images")):
            errors.append(f"{eid}: a sealed event carries no detail, numbers, links or images")

    chapter_of = {e["id"]: e.get("chapter") for e in data["events"] if isinstance(e, dict) and e.get("id")}
    for c in data.get("chapters", []) or []:
        if not isinstance(c, dict):
            continue
        cid = c.get("id", "?")
        for key, limit in (("digest", 700), ("outcome", 200)):
            if key in c and not (isinstance(c[key], str) and len(c[key]) <= limit):
                errors.append(f"chapter {cid}: {key} must be text of {limit} characters or fewer")
        if "end" in c:
            try:
                when(c["end"])
            except Exception:
                errors.append(f"chapter {cid}: end must be ISO 8601 with a UTC offset")
        if "keyBeats" in c:
            kb = c["keyBeats"]
            if not (isinstance(kb, list) and len(kb) <= 6 and all(isinstance(x, str) for x in kb)):
                errors.append(f"chapter {cid}: keyBeats must be a list of at most 6 event ids")
                continue
            for x in kb:
                if x not in ids:
                    errors.append(f"chapter {cid}: keyBeats {x!r} does not exist")
                elif chapter_of.get(x) != cid:
                    warnings.append(f"chapter {cid}: keyBeats {x} belongs to another chapter")

    run = data.get("run") or {}
    if "digest" in run and not (isinstance(run["digest"], list) and len(run["digest"]) <= 4 and all(isinstance(x, str) for x in run["digest"])):
        errors.append("run.digest must be a list of at most 4 strings")
    if "t3" in run:
        t = run["t3"]
        if not (isinstance(t, dict) and all(isinstance(t.get(k), str) and ID_RE.fullmatch(t[k]) for k in ("env", "thread"))
                and ("base" not in t or isinstance(t["base"], str))):
            errors.append("run.t3 must be {env, thread, base?} with ids of letters, digits, _ : % . -")
    for lane in data.get("lanes", []) or []:
        if isinstance(lane, dict):
            if "thread" in lane and not (isinstance(lane["thread"], str) and ID_RE.fullmatch(lane["thread"])):
                errors.append(f"lane {lane.get('id')}: thread must be a T3 thread id")
            if "model" in lane and not (isinstance(lane["model"], str) and len(lane["model"]) <= 32):
                errors.append(f"lane {lane.get('id')}: model must be text of 32 characters or fewer")

    best = (data.get("headline") or {}).get("best") or {}
    if best.get("eventId") and best["eventId"] not in ids:
        errors.append(f"headline.best.eventId {best['eventId']!r} does not exist")
    tone = ((data.get("headline") or {}).get("status") or {}).get("tone")
    if tone and tone not in ("good", "warn", "bad", "done"):
        errors.append("headline.status.tone must be good, warn, bad or done")

    for m in data.get("metrics", []) or []:
        if not isinstance(m, dict) or not m.get("name") or m.get("value") is None:
            errors.append(f"metric without name or value: {m!r}")
            continue
        try:
            when(m.get("time"))
        except Exception:
            errors.append(f"metric {m['name']!r}: time must be ISO 8601 with a UTC offset")

    text = json.dumps(data, ensure_ascii=False).lower()
    words, phrases = deny_terms(cfg)
    hits = sorted(w for w in words if re.search(rf"\b{re.escape(w)}\b", text))
    hits += sorted(p for p in phrases if p in text)
    if hits:
        errors.append(f"{len(hits)} denied term(s) appear in the feed (deny list in keeper/config.json); rewrite with codes or counts")
    return errors, warnings, data


def install(src):
    tmp = TARGET.with_suffix(".json.tmp")
    tmp.write_bytes(Path(src).read_bytes())
    os.replace(tmp, TARGET)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = Path(args[0]) if args else TARGET
    errors, warnings, _ = check(src)
    for w in warnings:
        print("warn:", w)
    if errors:
        for e in errors:
            print("error:", e)
        print(f"FAIL {src} ({len(errors)} errors)")
        sys.exit(1)
    print(f"OK {src}")
    if "--install" in sys.argv and src.resolve() != TARGET:
        install(src)
        print(f"installed -> {TARGET}")


if __name__ == "__main__":
    main()
