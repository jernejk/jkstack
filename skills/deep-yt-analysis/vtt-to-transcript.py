#!/usr/bin/env python3
"""VTT -> [MM:SS] text transcript.

Handles both YouTube caption shapes: the rolling window (each cue repeats the
previous line) and the two-distinct-lines-per-cue shape that vtt-dedupe.py's
last-line-only rule silently halves.
"""
import re
import sys
from collections import deque

TIME_RE = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})")


def ts_to_mmss(ts):
    h, m, s = ts.split(":")
    total = int(h) * 3600 + int(m) * 60 + float(s)
    return f"{int(total // 60):02d}:{int(total % 60):02d}"


def clean(line):
    return re.sub(r"<[^>]+>", "", line).strip()


def main(vtt_path, out_path):
    recent = deque(maxlen=6)
    entries = []
    for block in open(vtt_path, encoding="utf-8").read().split("\n\n"):
        start = None
        texts = []
        for l in block.strip("\n").split("\n"):
            m = TIME_RE.search(l)
            if m:
                start = m.group(1)
                continue
            if l.strip() in ("WEBVTT", "") or l.startswith(("Kind:", "Language:")):
                continue
            texts.append(clean(l))
        if not start:
            continue
        for t in texts:
            if not t or t in recent:
                continue
            recent.append(t)
            entries.append((ts_to_mmss(start), t))

    with open(out_path, "w", encoding="utf-8") as f:
        for mmss, text in entries:
            f.write(f"[{mmss}] {text}\n")
    print(f"Wrote {len(entries)} lines to {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
