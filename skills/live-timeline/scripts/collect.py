#!/usr/bin/env python3
"""One cheap, read-only pass over the sources in keeper/config.json: print only what changed since the last pass.

  python3 live/collect.py            # new lines per source, T3 thread activity, pending approvals, quiet lanes
  python3 live/collect.py --reset    # forget the cursor (next pass prints each source's tail)
  python3 live/collect.py --mark     # read everything silently, so the keeper's first pass starts after the seed

Output stays near `maxChars` (config, default 8000): a source that doesn't fit is held whole for the next pass, never dropped.
It ends with a NEXT line listing what this cycle's single patch must cover, and flags a stale headline status.
"""
import contextlib
import glob
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STATE = HERE / "keeper" / "state.json"
CONFIG = HERE / "keeper" / "config.json"
T3_DBS = [Path.home() / ".t3/userdata/statev2.sqlite", Path.home() / ".t3/userdata/state.sqlite"]


def sources(cfg):
    excl = [x.lower() for x in cfg.get("exclude", [])] + ["/private/"]
    found = []
    for pattern in cfg.get("sources", []):
        p = Path(pattern).expanduser()
        base = p if p.is_absolute() else ROOT / pattern
        for hit in sorted(glob.glob(str(base), recursive=True)):
            path = Path(hit)
            key = str(path.relative_to(ROOT)) if ROOT in path.parents else str(path).replace(str(Path.home()), "~")
            if path.is_file() and not path.is_symlink() and not any(x in "/" + key.lower() for x in excl) and HERE not in path.parents:
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


def t3(cfg, old):
    spec = cfg.get("t3") or {}
    if not (spec.get("root") or spec.get("titles")):
        return {}
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
        return {tid: u for tid, (_, u) in mine.items()}
    print("\nT3 THREADS unavailable (no readable state db)")
    return {}


def stale_status(cfg):
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
    said = f"{status.get('tone', '')}: {status.get('text', '')}" + (f" · {status['note']}" if status.get("note") else "")
    return (f"STATUS set {int(age)} min ago" if age is not None else "STATUS never dated") + \
        f" ({said}). Still true? Send headline.status again, corrected or as is."


def main():
    if "--mark" in sys.argv:
        with open(os.devnull, "w") as quiet, contextlib.redirect_stdout(quiet):
            collect()
        print("MARKED: the next pass shows only what changes from now on")
        return
    collect()


def collect():
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    old = {} if "--reset" in sys.argv or not STATE.exists() else json.loads(STATE.read_text())
    tail, cap = cfg.get("firstPassTail", 25), cfg.get("maxLinesPerSource", 80)
    budget = float("inf") if "--mark" in sys.argv else cfg.get("maxChars", 8000)
    drop = set(cfg.get("jsonlDropKeys", []))
    state = {"collected": datetime.now().astimezone().isoformat(timespec="seconds"), "files": {}, "threads": {}}
    print("COLLECTED", state["collected"], "· previous", old.get("collected", "never"))
    todo, held = [], []
    for key, path in sources(cfg):
        st = path.stat()
        prev = old.get("files", {}).get(key, {})
        if prev.get("mtime_ns") == st.st_mtime_ns and prev.get("size") == st.st_size:
            state["files"][key] = prev
            continue
        lines = path.read_text(errors="replace").splitlines()
        hashes = [hashlib.sha1(l.encode()).hexdigest()[:16] for l in lines]
        seen = set(prev.get("h", []))
        new = [(l, h) for l, h in zip(lines, hashes) if h not in seen and l.strip()]
        if not prev:
            new = new[-tail:]
        cut = len(new) - cap
        new = new[-cap:]
        name = key if not key.startswith(("~", "/")) else "…/" + "/".join(Path(key).parts[-2:])
        texts = [jsonl_line(l, drop) if path.suffix == ".jsonl" else l[:400] for l, _ in new]
        size = sum(len(t) + 3 for t in texts) + len(name) + 60
        if size > budget and todo:
            if prev:
                state["files"][key] = prev
            held.append(f"{name} ({len(new)} lines)")
            continue
        shown = []
        for text in texts:
            if budget < len(text) + 3 and shown:
                break
            budget -= len(text) + 3
            shown.append(text)
        budget -= len(name) + 60
        rest = {h for _, h in new[len(shown):]}
        state["files"][key] = {"mtime_ns": None if rest else st.st_mtime_ns, "size": st.st_size,
                               "h": [h for h in hashes if h not in rest]}
        if rest:
            held.append(f"the rest of {name} ({len(rest)} lines)")
        todo.append(f"{name} (+{len(shown)})")
        print(f"\nSOURCE {name}  +{len(shown)} lines" + (f" ({cut} older new lines skipped)" if cut > 0 else "")
              + ("  [first pass: tail only]" if not prev else "") + (f"  [{len(rest)} more next pass]" if rest else ""))
        for text in shown:
            print("  " + text)
    state["threads"] = t3(cfg, old.get("threads", {}))
    STATE.parent.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".next.json")
    tmp.write_text(json.dumps(state) + "\n")
    tmp.replace(STATE)
    if held:
        print("\nHELD for the next pass (output budget): " + ", ".join(held))
    stale = stale_status(cfg)
    if stale:
        print("\n" + stale)
    if todo:
        print("\nNEXT put all of this in one patch: " + ", ".join(todo) + (", and the status" if stale else "") + ".")
    elif stale:
        print("\nNEXT send headline.status in this cycle's patch.")


if __name__ == "__main__":
    main()
