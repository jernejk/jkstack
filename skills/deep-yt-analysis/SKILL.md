---
name: deep-yt-analysis
description: Deep-analyze YouTube videos with transcripts, vision-checked frames, claim research, and a self-contained HTML verdict. Use for "deep dive/analyze this video", an important YouTube URL, or `/deep-yt-analysis`; not for simple downloads or watch statistics.
metadata:
  version: "1.0.0"
  updated: "2026-07-28"
  category: research
---

# Deep YT Analysis

Study a video through its transcript, visually checked frames, and sourced claim research. Use the owner’s stated goals when deciding what is worth adopting. Resolve `SKILL_DIR` to this installed skill folder in Claude Code or Codex; T3 Code uses the same files.

## Access, privacy, and cost

- Default to media, captions, thumbnails, and metadata supplied by the owner. A public URL alone is not permission to download. Start transcript-only when media is unavailable, and say which visual claims could not be checked.
- Network acquisition is opt-in, per video. The owner is responsible for complying with the site's current terms and having the necessary permission. Check the applicable terms and authorized acquisition method first. Ownership or creator permission alone may not override the platform's access rules. [YouTube's terms](https://www.youtube.com/static?template=terms) restrict downloading and automated access except in permitted circumstances.
- Never import browser cookies, use logged-in sessions, evade bot checks, rotate proxies, spoof extractor clients, or bypass paywalls or access controls. Stop on authentication challenges, access denial, or rate limits; ask for an authorized local copy. Do not retry aggressively. A downloader being technically able to fetch something does not establish permission.
- Do not install tools automatically. List missing prerequisites. No paid transcription service or other API is required. Default new metered API spend is zero. Before any paid call or delegation, agree a total spend ceiling, frame limit, time limit, and allowed models with the owner. Use the harness's available budget enforcement; if it cannot enforce a hard ceiling, do not start unattended paid work. Stop when the cap is reached or usage cannot be determined.
- Run stages inline by default. Delegation is optional only when the owner requests it and the harness supports it. Do not spawn a second CLI to bypass harness restrictions. No recursive delegation.
- Store output in an owner-selected folder. Keep media and raw metadata out of source control. Never upload private media to an external vision model without authorization. Review frames for people, account names, private screens, and credentials before analysis or sharing. A report may retain copyrighted excerpts; keep them minimal and do not redistribute full videos or transcripts by default.

## Inputs

- One or more YouTube URLs. Multiple videos: run Stages 1–4 per video
  (keep acquisition bounded to the agreed videos), then ONE combined
  report with a section per video plus a cross-video verdict table.
- Optional user focus (e.g. "which projects should I build?", "is the claim
  true?"). Default lens: *understand each thing shown/claimed; judge what's
  worth adopting for you*.

## Stage 1 — Gather authorized material

1. Choose an output folder and record the supplied URL, title, channel, date, duration, and chapters when available. Keep only needed metadata fields; full extractor JSON can expose private or signed URLs. Do not print raw extractor output.
2. Prefer the owner’s local video, VTT captions, and optional thumbnail. Preserve originals and record provenance. State whether captions are manual or automatic. Use the player or another authorized export when that is the permitted route.
3. Only after explicit acquisition authorization and a terms check, an optional `yt-dlp` command may be used for the permitted resource. Use `--ignore-config` so local downloader settings cannot silently load cookies or credentials, `--no-playlist`, a bounded format and output directory, and one supplied URL. Do not use extractor-client overrides. Stop on denial or throttling. Do not fetch metadata, captions, or thumbnails automatically just because video download was declined.
4. Convert supplied VTT with the bundled `python3 "$SKILL_DIR/vtt-to-transcript.py" input.vtt transcript.txt`. This retains distinct lines in multi-line cues; `vtt-dedupe.py` is a legacy last-line converter and can lose content. Keep the raw VTT and spot-check both repeated captions and genuine repeated speech. The converters use a simple dedupe heuristic, not a verbatim transcription guarantee.
5. Return the folder path, selected metadata, available files, caption provenance, and any gaps. No video is required for a useful transcript-only result.

## Stage 2 — Timestamp curation

Read `transcript.txt` (and `chapters.txt`) fully. Build the segment map: every
distinct project/demo/claim/topic with its time range. Then pick frame targets
as `name → seconds → what should be visible`. Start with up to 12 high-value frames. Increase only within the agreed frame and spend limits; never exceed 50 targets. A transcript-only run records the missing visual checks instead.

- Bias toward moments where screen content is likely on display ("here's...",
  "looking at...", demos, dashboards, benchmarks) — not pure narration.
- 2–3 frames for major segments, 1 for minor ones; kebab-case numbered names
  (`04-lakebed-intro`).
- Aim ~2s after the introduction of a visual so it's actually on screen.
- Write the target list to `frame-targets.md` in the video folder for Stage 3.

## Stage 3 — Frame extraction and vision QA

Use the supplied video path, a `frames/` output directory, and the target list. Work inline unless delegation was authorized. Use an available vision-capable model only with the owner's data-sharing permission.

- Extract: `ffmpeg -loglevel error -ss <sec> -i video.mp4 -frames:v 1 -q:v 2 frames/<name>.jpg`
  (batch several per Bash call).
- **QA every frame visually** (Read the image). Talking-head-only (no screen
  content) → re-shoot at +3s, +6s, −3s, +10s and keep the first good variant;
  keep only reviewed candidates in the report; preserve source media.
- Return per frame: final filename, timestamp used, one-line description of
  what's visible — *be specific: app names, readable headings, numbers, costs*
  (this vision pass recovers on-screen data the transcript never mentions).
- Also return: frames that MISSED their intended subject (kept but off-topic),
  with the window where the right shot likely lives — so the main model can
  cheaply re-aim 1–3 frames itself afterwards (extract candidates, Read them,
  keep the best, exclude the rest). Re-aim caveats: if all candidates show the
  same static scene, the target is *verbal-only* — keep one scene frame or
  delete it, stop hunting; if a frame duplicates another kept frame, omit it
  (numbering gaps in `frames/` are fine); a re-aim may also *add* a companion
  frame (`NNb-name`) when both shots carry distinct evidence; if more than 3
  targets missed, re-aim only the 3 most report-critical. Note: `-ss` fast-seek
  is approximate and brief UI popups live in ~1s windows — trust the visual QA
  loop, not the timestamp.

## Stage 4 — Claim research

Write `research.md` in the output folder and summarize its findings. If a researcher was explicitly delegated, give it the transcript, reviewed frame paths, recovered numbers, and the owner's focus in a self-contained brief. Confirm the file exists before relying on its return. No further delegation.

Per project/claim/topic:

1. What it actually is (transcript + public info: creator's site, GitHub, X,
   HN, Reddit — WebSearch/WebFetch).
2. Does it already exist publicly? Name closest existing tools/products.
3. Rough build complexity for a solo dev with strong agent leverage.
4. **Owner fit**: compare against only the goals, constraints, and existing tools the owner supplied. Do not read unrelated personal files to invent this context.

Plus: coverage/reactions to the video itself (often none if fresh — say so),
whether featured repos are public, and verification of the video's biggest
claims. If a source denies access, stop fetching it and note the gap. Use accessible primary sources; secondary reactions are context, not proof.
When a spoken number and an on-screen number conflict, report both.
Multi-topic news videos: don't research every topic at equal depth — triage
deep/medium/light by the user-focus lens and record the triage in research.md.
Only rely on frames once Stage 3 has verified them — then Read 5–10 relevant ones to enrich with on-screen
facts; otherwise skip. Scale research depth to the distinct-claim/item count,
not the video's runtime. End with a scored shortlist (1–10 "worth building/adopting for your stated goals", one-line justification, opinionated). No further delegation.

## Stage 5 — Report

Write `{video-folder}/report.html` (multi-video: `report.html` in a shared
parent folder with relative paths into each video folder). Return its path; open it only when requested.
Judgment is YOURS — use research.md as evidence, adjust scores where you
disagree, and say so. Scale report length to the distinct-item count, not the
video's runtime (a 5-min dense video earns a short report).

Start from the bundled template
`report-template.html` beside this file (dark GitHub-ish
theme, self-contained inline CSS, no external requests) — keep its CSS as-is
for cross-run consistency. **Score rubric (consistent across videos):**
8–10 = act this week · 6–7 = plan/bounded trial · 4–5 = maybe/watch ·
1–3 = skip or adopt-only. Structure:

1. **Header** — `hero.jpg` banner (`<figure class="hero">`), title, channel,
   date, duration, video link, pipeline note.
2. **TL;DR verdict box** — build 🟢 / buy-or-configure 🔵 / adopt 🟣 / skip 🔴.
3. **Scoreboard table** — every item: cost/effort seen in video, verdict, score,
   anchor links. Shape rows to the video type: project showcases → projects;
   news/opinion videos → claims (status: verified / exaggerated / unverifiable /
   obsolete — news can be retracted between recording and analysis) and
   concrete actions for you.
4. **Per-item cards** — score badge · YouTube `?t=<sec>` timestamp link · stat
   chips (real numbers read off frames) · what it is · frame image(s)
   (`<img loading="lazy" src="frames/...">`, relative paths, captioned) ·
   prior art · Owner fit · verdict line.
5. **Cross-cutting techniques** worth adopting regardless of item.
6. **Appendix** — folder file index, context links, pipeline credits.

## Wrap-up

- List what actually exists: supplied video or transcript, caption source, selected metadata, frame targets, research, reviewed frames, and report. Name skipped stages and unverified visual claims. Do not imply absent media was acquired.
- Final message: the main verdicts, evidence limits, and report path.
- Saving follow-ups, publishing, or redistributing source material requires a separate request. A generated report is not automatically cleared for sharing.
