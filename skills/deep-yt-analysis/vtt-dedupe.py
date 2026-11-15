#!/usr/bin/env python3
"""Convert an auto-generated YouTube VTT (rolling/cumulative caption cues)
into a clean, deduplicated timestamped transcript: [MM:SS] text

YouTube auto-caption VTTs render captions as a rolling window: each cue
repeats the previous line of text plus a new line being built word-by-word
via inline <time><c>word</c> tags, followed by a zero-duration cue with the
completed line. We take the LAST non-blank line of each cue (the most
complete text at that point) and dedupe consecutive repeats, which yields
exactly one entry per new line of speech.
"""
import re
import sys

def ts_to_mmss(ts):
    h, m, s = ts.split(":")
    total_seconds = int(h) * 3600 + int(m) * 60 + float(s)
    mm = int(total_seconds // 60)
    ss = int(total_seconds % 60)
    return f"{mm:02d}:{ss:02d}"

def clean_line(line):
    line = re.sub(r"<[^>]+>", "", line)
    return line.strip()

def main(vtt_path, out_path):
    with open(vtt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.split("\n\n")
    entries = []
    last_text = None

    time_re = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})")

    for block in blocks:
        lines = block.strip("\n").split("\n")
        if not lines or not lines[0]:
            continue
        m = None
        text_lines = []
        for l in lines:
            tm = time_re.search(l)
            if tm:
                m = tm
                continue
            if l.strip() == "WEBVTT" or l.startswith("Kind:") or l.startswith("Language:"):
                continue
            text_lines.append(clean_line(l))
        if not m:
            continue
        start_ts = m.group(1)
        # take the last non-blank line = most complete text for this cue
        non_blank = [t for t in text_lines if t]
        if not non_blank:
            continue
        text = non_blank[-1]
        if text == last_text:
            continue
        last_text = text
        mmss = ts_to_mmss(start_ts)
        entries.append((mmss, text))

    with open(out_path, "w", encoding="utf-8") as f:
        for mmss, text in entries:
            f.write(f"[{mmss}] {text}\n")

    print(f"Wrote {len(entries)} lines to {out_path}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
