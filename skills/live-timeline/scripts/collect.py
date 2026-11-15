#!/usr/bin/env python3
"""One cheap, read-only pass over the sources in keeper/config.json: print only what changed since the last pass.

  python3 live/collect.py            # new lines per source, T3 thread activity, pending approvals, quiet lanes
  python3 live/collect.py --reset    # forget the cursor (next pass prints each source's tail)
"""
import glob
import hashlib
import json
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


def main():
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    old = {} if "--reset" in sys.argv or not STATE.exists() else json.loads(STATE.read_text())
    tail, cap = cfg.get("firstPassTail", 25), cfg.get("maxLinesPerSource", 80)
    drop = set(cfg.get("jsonlDropKeys", []))
    state = {"collected": datetime.now().astimezone().isoformat(timespec="seconds"), "files": {}, "threads": {}}
    print("COLLECTED", state["collected"], "· previous", old.get("collected", "never"))
    for key, path in sources(cfg):
        st = path.stat()
        prev = old.get("files", {}).get(key, {})
        if prev.get("mtime_ns") == st.st_mtime_ns and prev.get("size") == st.st_size:
            state["files"][key] = prev
            continue
        lines = path.read_text(errors="replace").splitlines()
        hashes = [hashlib.sha1(l.encode()).hexdigest()[:16] for l in lines]
        seen = set(prev.get("h", []))
        new = [l for l, h in zip(lines, hashes) if h not in seen and l.strip()]
        state["files"][key] = {"mtime_ns": st.st_mtime_ns, "size": st.st_size, "h": hashes}
        if not prev:
            new = new[-tail:]
        cut = len(new) - cap
        new = new[-cap:]
        print(f"\nSOURCE {key}  +{len(new)} lines" + (f" ({cut} older new lines skipped)" if cut > 0 else "") + ("  [first pass: tail only]" if not prev else ""))
        for line in new:
            print("  " + (jsonl_line(line, drop) if path.suffix == ".jsonl" else line[:400]))
    state["threads"] = t3(cfg, old.get("threads", {}))
    STATE.parent.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".next.json")
    tmp.write_text(json.dumps(state) + "\n")
    tmp.replace(STATE)


if __name__ == "__main__":
    main()
