#!/usr/bin/env python3
"""One cheap, read-only pass over the sources in keeper/config.json: print only what changed since the last pass.

  python3 live/collect.py             # new lines per source, T3 thread activity, pending approvals, quiet lanes
  python3 live/collect.py --wait 20m  # nothing new? block here (checks every 15 s) until something changes or 20 m pass
  python3 live/collect.py --reset     # forget the cursor (next pass prints each source's tail)
  python3 live/collect.py --mark      # read everything silently and commit, so the first pass starts after the seed

The cursor is staged: a pass writes keeper/draft.json then keeper/state.next.json, both stamped with one batch id, and patch.py
commits the cursor once the patch installs (a draft stays pending until a patch sends {"draft": true}), so running this
twice without a patch shows the same lines again. --mark and --reset write keeper/state.json directly.
Config "leadLog": "LEAD-LOG.md" hands that file to ingest.py: its new lines come back as a compact draft (keeper/draft.json)
for patch.py {"draft": true, "fill": {...}} instead of raw text, and it is left out of the raw sources.
--wait counts a changed source, a staged draft, a stale status, or (when "t3" is configured) a thread that updated or a new
approval request as something new; it prints `QUIET for N min: nothing new. NEXT send {}.` on timeout.
Output stays near `maxChars` (config, default 8000): a source that doesn't fit is held whole for the next pass, never dropped.
It ends with a NEXT line listing what this cycle's single patch must cover, and flags a stale headline status.
"""
import contextlib
import glob
import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import ingest  # noqa: E402
import validate  # noqa: E402

STATE = HERE / "keeper" / "state.json"
STAGED = HERE / "keeper" / "state.next.json"
DRAFT = HERE / "keeper" / "draft.json"
CONFIG = HERE / "keeper" / "config.json"
T3_DBS = [Path.home() / ".t3/userdata/statev2.sqlite", Path.home() / ".t3/userdata/state.sqlite"]


def load_config():
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else {}


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def lead_problem(path, key, cfg):
    user = [x.lower() for x in cfg.get("exclude", [])]
    real, base = path.resolve(), ROOT.resolve()
    rkey = str(real.relative_to(base)) if base in real.parents else str(real)
    if path.is_symlink():
        return "is a symlink"
    if validate.private_path(path, ROOT):
        return "resolves into a private folder"
    if any(x in "/" + key.lower() for x in user + ["/private/"]) or any(x in "/" + rkey.lower() for x in user):
        return "matches an exclude"
    return ""


def lead_log(cfg, say=False):
    spec = cfg.get("leadLog")
    if not spec:
        return None
    p = Path(spec).expanduser()
    path = p if p.is_absolute() else ROOT / spec
    if not path.is_file():
        return None
    key = str(path.relative_to(ROOT)) if ROOT in path.parents else str(path).replace(str(Path.home()), "~")
    why = lead_problem(path, key, cfg)
    if why:
        if say:
            print(f"SKIPPED lead log: {key} {why}")
        return None
    return key, path


def new_lines(lines, prev):
    seen = Counter(prev.get("h", []))
    new = []
    for i, l in enumerate(lines):
        h = hashlib.sha1(l.encode()).hexdigest()[:16]
        if seen[h]:
            seen[h] -= 1
        elif l.strip():
            new.append((l, i))
    return new


def sources(cfg):
    excl = [x.lower() for x in cfg.get("exclude", [])] + ["/private/"]
    lead = lead_log(cfg)
    found = []
    for pattern in cfg.get("sources", []):
        p = Path(pattern).expanduser()
        base = p if p.is_absolute() else ROOT / pattern
        for hit in sorted(glob.glob(str(base), recursive=True)):
            path = Path(hit)
            key = str(path.relative_to(ROOT)) if ROOT in path.parents else str(path).replace(str(Path.home()), "~")
            if path.is_file() and not path.is_symlink() and not any(x in "/" + key.lower() for x in excl) and HERE not in path.parents \
                    and not (lead and path.resolve() == lead[1].resolve()):
                found.append((key, path))
    return found


def jsonl_line(line, drop):
    try:
        row = json.loads(line)
    except ValueError:
        return line
    if isinstance(row, dict):
        row = {k: v for k, v in row.items() if k not in drop}
    return json.dumps(row, ensure_ascii=False)[:600]


def clip(line, limit=400):
    """Shorten a long line but keep every [tag] after the cut: tags carry images, metrics and status."""
    if len(line) <= limit:
        return line
    cut = limit
    opened = line.rfind("[", 0, cut)
    if opened != -1 and line.find("]", opened) >= cut:
        cut = opened
    tags = re.findall(r"\[[^\[\]]{1,300}\]", line[cut:])
    return line[:cut].rstrip() + " …" + "".join(" " + t for t in tags)


def t3_rows(cfg):
    """(watched {thread: (title, updated)}, pending [(thread, kind, created)]) or None when no state db is readable."""
    spec = cfg.get("t3") or {}
    if not (spec.get("root") or spec.get("titles")):
        return {}, []
    for db in ([Path(spec["db"]).expanduser()] if spec.get("db") else T3_DBS):
        if not db.exists():
            continue
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
            con.execute("PRAGMA query_only=ON")
            rows = con.execute("SELECT thread_id, title, updated_at, payload_json FROM orchestration_v2_projection_threads "
                               "WHERE deleted_at IS NULL AND archived_at IS NULL").fetchall()
        except sqlite3.Error:
            continue
        root, titles = spec.get("root"), [t.lower() for t in spec.get("titles", [])]
        mine = {}
        for tid, title, updated, payload in rows:
            try:
                lineage = (json.loads(payload or "{}").get("lineage") or {})
            except ValueError:
                lineage = {}
            if (root and (tid == root or lineage.get("rootThreadId") == root)) or any(t in (title or "").lower() for t in titles):
                mine[tid] = (title, updated)
        pending = []
        if mine:
            marks = ",".join("?" * len(mine))
            try:
                pending = con.execute(f"SELECT thread_id, kind, created_at FROM orchestration_v2_projection_runtime_requests "
                                      f"WHERE status='pending' AND thread_id IN ({marks})", list(mine)).fetchall()
            except sqlite3.Error:
                pending = []
        con.close()
        return mine, pending
    return None


def t3(cfg, old):
    spec = cfg.get("t3") or {}
    if not (spec.get("root") or spec.get("titles")):
        return {}, []
    found = t3_rows(cfg)
    if found is None:
        print("\nT3 THREADS unavailable (no readable state db)")
        return {}, []
    mine, pending = found
    now = datetime.now(timezone.utc)
    quiet_min = spec.get("quietAfterMin", 30)
    changed, quiet = [], []
    for tid, (title, updated) in mine.items():
        if old.get(tid) != updated:
            changed.append(f"{updated}  {title}")
        try:
            age = (now - datetime.fromisoformat(updated.replace("Z", "+00:00"))).total_seconds() / 60
        except (ValueError, AttributeError):
            continue
        if age > quiet_min:
            quiet.append(f"{int(age)} min  {title}")
    print(f"\nT3 THREADS {len(mine)} watched · {len(changed)} active since last pass")
    for line in sorted(changed):
        print("  active ", line)
    for tid, kind, created in pending:
        print(f"  WAITING ON APPROVAL since {created}  [{kind}]  {mine[tid][0]}")
    for line in sorted(quiet):
        print("  quiet  ", line)
    return {tid: u for tid, (_, u) in mine.items()}, [f"{t}|{c}" for t, _, c in pending]


def stale_status(cfg, newest):
    try:
        data = json.loads((HERE / "events.json").read_text())
    except (OSError, ValueError):
        return ""
    status = (data.get("headline") or {}).get("status") or {}
    if (data.get("run") or {}).get("done") or status.get("tone") == "done":
        return ""
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(status["asOf"])).total_seconds() / 60
    except (KeyError, TypeError, ValueError):
        age = None
    limit = cfg.get("statusStaleMin", 20)
    if age is not None and age < limit:
        return ""
    if age is not None and newest is not None and newest <= datetime.fromisoformat(status["asOf"]).timestamp():
        return ""
    said = f"{status.get('tone', '')}: {status.get('text', '')}" + (f" · {status['note']}" if status.get("note") else "")
    return (f"STATUS set {int(age)} min ago" if age is not None else "STATUS never dated") + \
        f" ({said}). Still true? Send headline.status again, corrected or as is."


def duration(text):
    m = re.fullmatch(r"(\d+)\s*([smh])", text.strip())
    if not m:
        raise SystemExit("--wait takes a duration like 90s, 20m or 1h")
    return int(m[1]) * {"s": 1, "m": 60, "h": 3600}[m[2]]


def said(seconds):
    return f"{seconds} s" if seconds < 120 else f"{seconds // 3600} h" if seconds % 3600 == 0 else f"{round(seconds / 60)} min"


def something_new(cfg, committed):
    if DRAFT.exists():
        return True
    files = [lead_log(cfg)] if lead_log(cfg) else []
    newest = None
    for key, path in files + sources(cfg):
        st = path.stat()
        newest = max(newest or 0, st.st_mtime)
        prev = committed.get("files", {}).get(key, {})
        if prev.get("mtime_ns") != st.st_mtime_ns or prev.get("size") != st.st_size:
            return True
    found = t3_rows(cfg)
    if found:
        mine, pending = found
        if any(committed.get("threads", {}).get(tid) != u for tid, (_, u) in mine.items()):
            return True
        if sorted(f"{t}|{c}" for t, _, c in pending) != sorted(committed.get("pending", [])):
            return True
    return bool(stale_status(cfg, newest))


def batch_of(path):
    try:
        return json.loads(path.read_text()).get("batch")
    except (OSError, ValueError, AttributeError):
        return None


def recover():
    """A patch that installed the feed but died before committing leaves its batch in the feed: finish the commit."""
    applied = batch_of(HERE / "events.json")
    if not applied:
        return
    if batch_of(STAGED) == applied:
        os.replace(STAGED, STATE)
    if batch_of(DRAFT) == applied:
        DRAFT.unlink(missing_ok=True)


def main():
    args = sys.argv[1:]
    recover()
    if "--mark" in args:
        with open(os.devnull, "w") as quiet, contextlib.redirect_stdout(quiet):
            collect(commit=True)
        print("MARKED: the next pass shows only what changes from now on")
        return
    if "--wait" in args:
        i = args.index("--wait")
        seconds = duration(args[i + 1] if i + 1 < len(args) else "")
        cfg, committed = load_config(), load_state()
        deadline = time.monotonic() + seconds
        while not something_new(cfg, committed):
            left = deadline - time.monotonic()
            if left <= 0:
                print(f"QUIET for {said(seconds)}: nothing new. NEXT send {{}}.")
                return
            time.sleep(min(15, left))
    if "--reset" in args:
        write_state({}, STATE)
        STAGED.unlink(missing_ok=True)
    collect()


def write_state(state, target):
    target.parent.mkdir(exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(state) + "\n")
    tmp.replace(target)


def collect(commit=False):
    cfg = load_config()
    old = load_state()
    tail, cap = cfg.get("firstPassTail", 25), None if commit else cfg.get("maxLinesPerSource", 80)
    budget = float("inf") if commit else cfg.get("maxChars", 8000)
    drop = set(cfg.get("jsonlDropKeys", []))
    state = {"collected": datetime.now().astimezone().isoformat(timespec="seconds"), "files": {}, "threads": {}}
    if old.get("ingest"):
        state["ingest"] = old["ingest"]
    print("COLLECTED", state["collected"], "· previous", old.get("collected", "never"))
    todo, held = [], []
    newest = None
    lead = lead_log(cfg, say=True)
    draft_status = False
    draft_out = None
    for key, path in ([(lead[0], lead[1])] if lead else []) + sources(cfg):
        is_lead = bool(lead) and path == lead[1]
        st = path.stat()
        newest = max(newest or 0, st.st_mtime)
        prev = old.get("files", {}).get(key, {})
        if prev.get("mtime_ns") == st.st_mtime_ns and prev.get("size") == st.st_size:
            state["files"][key] = prev
            continue
        text = path.read_text(errors="replace")
        lines = ingest.complete_lines(text) if is_lead else text.splitlines()
        hashes = [hashlib.sha1(l.encode()).hexdigest()[:16] for l in lines]
        new = new_lines(lines, prev)
        dropped = []
        if not prev:
            dropped, new = new[:-tail] if tail else [], new[-tail:]
        cut = len(new) if cap is None else cap
        while is_lead and cut < len(new) and new[cut][0][:1].isspace():
            cut += 1
        overflow = {i for _, i in new[cut:]}
        new = new[:cut]
        name = key if not key.startswith(("~", "/")) else "…/" + "/".join(Path(key).parts[-2:])
        cost = (lambda l: 0 if l[:1].isspace() else min(len(l), 200)) if is_lead else (lambda l: len(l))
        texts = [l if is_lead else jsonl_line(l, drop) if path.suffix == ".jsonl" else clip(l) for l, _ in new]
        size = sum(cost(t) + 3 for t in texts) + len(name) + 60
        if size > budget and todo:
            if prev:
                state["files"][key] = prev
            held.append(f"{name} ({len(new)} lines)")
            continue
        shown = []
        for text in texts:
            if budget < cost(text) + 3 and shown and not (is_lead and text[:1].isspace()):
                break
            budget -= cost(text) + 3
            shown.append(text)
        budget -= len(name) + 60
        rest = {i for _, i in new[len(shown):]} | overflow
        state["files"][key] = {"mtime_ns": None if rest else st.st_mtime_ns, "size": st.st_size,
                               "h": [h for i, h in enumerate(hashes) if i not in rest]}
        if rest:
            held.append(f"the rest of {name} ({len(rest)} lines)")
        if is_lead:
            header = ingest.split_header(lines)
            try:
                feed = json.loads((HERE / "events.json").read_text())
            except (OSError, ValueError):
                feed = {}
            ist = old.get("ingest", {})
            if dropped:
                _, _, _, ist = ingest.parse([l for l, _ in dropped], header, feed, cfg, ist, thumbs=False)
            patch, unparsed, notes, ist = ingest.parse(shown, header, feed, cfg, ist, thumbs=not commit)
            state["ingest"] = ist
            beats = len(patch.get("events", []))
            if beats or any(patch.get(k) for k in ("edit", "metrics", "chapters", "headline", "run", "addLanes")):
                draft_out = patch
                draft_status = bool((patch.get("headline") or {}).get("status"))
            todo.append(f"{name} (+{beats} beats)")
            print(f"\nSOURCE {name}  +{len(shown)} lines" + ("  [first pass: tail only]" if not prev else "")
                  + (f"  [{len(rest)} more next pass]" if rest else ""))
            print(ingest.render(name, patch, unparsed, notes))
            continue
        todo.append(f"{name} (+{len(shown)})")
        print(f"\nSOURCE {name}  +{len(shown)} lines"
              + ("  [first pass: tail only]" if not prev else "") + (f"  [{len(rest)} more next pass]" if rest else ""))
        for text in shown:
            print("  " + text)
    state["threads"], state["pending"] = t3(cfg, old.get("threads", {}))
    if commit:
        write_state(state, STATE)
        STAGED.unlink(missing_ok=True)
        DRAFT.unlink(missing_ok=True)
    else:
        batch = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)
        if draft_out:
            write_state({**draft_out, "batch": batch}, DRAFT)
        else:
            DRAFT.unlink(missing_ok=True)
        write_state({**state, "batch": batch}, STAGED)
    if held:
        print("\nHELD for the next pass (output budget): " + ", ".join(held))
    stale = "" if draft_status else stale_status(cfg, newest)
    if stale:
        print("\n" + stale)
    if todo:
        print("\nNEXT put all of this in one patch: " + ", ".join(todo) + (", and the status" if stale else "") + ". patch.py commits this pass.")
    elif stale:
        print("\nNEXT send headline.status in this cycle's patch.")


if __name__ == "__main__":
    main()
