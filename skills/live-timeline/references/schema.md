# Live timeline feed — guide for the keeper

The page (`live-timeline.html`) reads **`live/events.json`** on load and every 60 s. You never touch the page: it
handles layout, the Live, Detail and Story modes, chapters, arcs and the "Write update" text. You only change the feed, and
only through **`live/patch.py`**.

## Your rules

- **Change the feed only with `python3 live/patch.py`** (patch JSON on stdin). It assigns ids, stamps `updated`,
  refreshes spend from `keeper/config.json`, validates, and swaps the file in atomically. If validation fails nothing
  is installed and the draft stays at `live/events.next.json`: fix the patch and run it again.
- **Observe, don't steer.** Don't message lanes, edit their files or start model calls. The page must never distract
  the work it describes.
- **Read only the sources in `keeper/config.json`.** `python3 live/collect.py` prints what changed since your last
  pass. Never read anything the config excludes (`private/` always).
- **Privacy.** The page is served to whoever can open the URL. No secrets, no names the config's deny list covers, no
  sealed contents. Write counts or codes ("3 of 12 documents ready") when the source names things it shouldn't.
- **Only measured facts.** If a lane says "AI-judged" or "unmeasured", so do you. No estimates in `metrics`.

## Each cycle

```bash
python3 live/collect.py                 # what changed since the last pass
python3 live/patch.py <<'EOF'           # what it means, as story beats
{ "events": [ … ], "edit": { … }, "headline": { … } }
EOF
```

If nothing worth a beat happened, skip the patch — or send `{}` so `updated` moves and the page doesn't show "No
update for 40 min — keeper stopped?". Send `{}` at least every 20 minutes while the work is running.

## Patch keys

| Key | Does |
|---|---|
| `events` | Appended. Leave out `id` (assigned `e###`), `time` (defaults to now) and `chapter` (defaults to the last chapter that had started by the event's `time`, or the first chapter when none had). Give a `"ref": "x"` to point at it elsewhere in the same patch as `"@x"`. |
| `edit` | `{ "e012": { "state": "done" } }` merges fields into an existing event and stamps its `updated`. Closing a start stamps its `end` (the latest new event that names it in `causedBy`, else now). |
| `editChapters` | `{ "c4": { "digest": "…", "outcome": "…", "keyBeats": ["e101"] } }` merges into a chapter. |
| `draft` | `true` applies `live/keeper/draft.json`, the patch `collect.py` drafted from the lead log; `fill` adds titles and links per draft beat (see the keeper brief). |
| `chapters` | Appended; `id` is assigned (`c#`). `start` defaults to the earliest event in the patch that points at it, else now: give the source line's time. |
| `metrics` | Appended. `"event": "@ref"` takes `time` and `lane` from that event; otherwise `time` defaults to now. |
| `lanes` | `{ "sol": "done" }` sets a lane's status. |
| `addLanes` | `[ { "id": "models", "name": "Model comparison", "short": "Models", "status": "running" } ]` |
| `headline` | Merged into the headline; a key set to `null` is removed. `best`, `status` and `progress` replace whole. |
| `run` | Merged into `run`. `{ "done": true }` marks the run finished (no "now" line, feed shows "Finished"). |

`patch.py` prints `{ "new": [...], "refs": {...}, "running": [...], "openBlockers": [...] }`: check that the
running starts and open blockers are the ones you expect.

## File shape

```json
{
  "schema": 2,
  "updated": "2026-11-04T21:10:00+10:00",
  "run":      { "title": "…", "owner": "Owner", "tz": "UTC", "start": "…", "staleAfterMin": 30,
                "t3": { "env": "…", "thread": "…" }, "digest": ["…"] },
  "headline": { "status": {…}, "progress": {…}, "best": {…}, "spend": {…} },
  "lanes":    [ … ], "chapters": [ … ], "events": [ … ], "metrics": [ … ]
}
```

### `headline` — status, progress, best result and spend

| Field | Meaning |
|---|---|
| `status` | `{ "tone": "good" \| "warn" \| "bad" \| "done", "text": "On track", "note": "Opus ETA 02:30" }`. Your one-line judgement: is this going well, drifting, or worth stopping? Change it when the answer changes. |
| `progress` | `{ "value": 7, "of": 12, "label": "documents analysed" }`, drawn as a bar under the status. |
| `best` | `{ "text": "numbers first, one line", "note": "the honest caveat", "eventId": "e081" }` |
| `spend` | Filled by `patch.py` from `keeper/config.json` → `spend.sources`. Don't hand-edit unless there is no source. |
| `latestBreakthroughId` | Optional; otherwise the newest `breakthrough`. |

The status sits in the header of every mode. Open blockers sit above everything else as "Needs you", with their choices and an "Answer in T3" link, so the owner sees them first.

### `lanes`

`{ "id": "sol", "name": "Sol lane", "short": "Sol", "status": "running" }`. `short` is 8 characters or fewer.
`status` is `running`, `done` or `paused`; the page decides what is active from open starts, open blockers and recent
beats, so `status` only matters as an override. The owner's lane has `"human": true` and is never counted. Array order
is track order. Optional `model` and `thread` (a T3 thread id) are defaults; the newest event's `model` and `thread` win.

### `run.t3`

`{ "env": "<environment id>", "thread": "<lead thread id>" }` turns on "Open in T3" links: the header, "Needs you"
(answer in the lead's thread) and lanes whose events carry a `thread`. `init.py` fills it when it runs inside T3 Code.
The links open the T3 desktop app (`t3code://threads/<env>/<thread>`); set `"base"` to an `https://…/threads/` URL
for a hosted T3 instead.

### `chapters`

`{ "id": "c4", "title": "Convergence", "start": "…", "summary": "One sentence: what this part is about." }`

The story layer is optional: `digest` (2–3 plain sentences: what happened and how it turned out), `outcome` (one line),
`keyBeats` (up to 4 distinct event ids from this chapter, shown in Story) and `end`. Without them the page picks the key
beats itself: open blockers, breakthroughs, dead ends, owner nudges, reviews, then successes. `run.digest` holds up
to three lines for the whole run. `digest.py` prints what a model needs to write them; see "Simplify the story".

A chapter is a turn in the story, not a clock slot: a new phase, a new question, a decisive steer. Expect one every
hour or two on a night run, one or two a day on a multi-day run. Titles are two to four plain words.

### `events`

| Field | Required | Meaning |
|---|---|---|
| `id` | assigned | Unique and permanent. |
| `time` | yes | When it happened, from the source's own stamp when it has one. ISO 8601 with offset. |
| `lane` | yes | A lane `id`. |
| `kind` | yes | One of the kinds below. |
| `importance` | yes | `1` quiet dot · `2` story beat · `3` milestone. |
| `title` | yes | 8 words or fewer. |
| `summary` | yes | One line: what happened, with the number that matters. |
| `why` | on 3s | One line: why it mattered, what it changed. |
| `ask` | on `blocked` | One line: exactly what the owner must do to unblock it. |
| `detail` | optional | Markdown for the beat's detail: paragraphs, `- ` bullets, `**bold**`, `` `code` ``, `[text](path)`. |
| `numbers` | optional | `[{ "label": "Recall", "value": "33/43" }, { "label": "Cost", "value": 0.41, "unit": "US$" }]`. The stream shows 2; the detail shows all. |
| `links` | optional | `[{ "label": "Findings", "path": "sol/FINDINGS.md" }]`, relative to the work folder. `private/`, absolute and `..` paths are refused. HTTPS evidence links are allowed; inspect their destination before sharing. |
| `causedBy` | optional | Ids this grew out of: drawn as arcs, listed as "Came from" / "Led to". |
| `state` | `start`, `blocked` | `start`: `running` draws a live bar to now; `done`/`failed` stops it. `blocked`: `open` (default) or `cleared`. |
| `end` | on `start` | When it finished; `patch.py` stamps it when the start closes. The run map draws the start as a bar. |
| `model` | optional | The model doing the work (`opus`, `gpt-6-luna`). Shown on the beat and totalled per model. Put it on starts. |
| `thread` | optional | The T3 thread doing the work; links the lane to it. |
| `choices` | on `blocked` | 2–6 short options when the owner must pick one: shown under "Needs you". Each is a label of 80 characters or fewer, or `{ "label": "Neon", "image": "live/thumbs/neon.jpg" }` to show a reviewed snapshot beside the option. The image path follows the rules under "Image snapshots"; text and the update use the label. |
| `supersedes` | optional | The id this corrects. The old one leaves the story and shows as "Replaces". |

**Importance.** `3` only for breakthroughs, blockers and beats the lead tags `[key]`: a few a day. `2` for anything that
changes what a lane does next. `1` for progress, repeats and housekeeping.

**`causedBy`** links an outcome to the start or nudge it came from. Don't chain each event to the one before it: an arc
that only says "this came next" is noise.

### Kinds

| `kind` | Shape | Use for |
|---|---|---|
| `start` | blue ring ▶ | An attempt, experiment or lane begins. Give it `state`. |
| `update` | grey dot | Progress with no verdict yet. Almost always importance 1. |
| `success` | green ✓ | An attempt met its bar, or a result landed. |
| `breakthrough` | gold star | A result that changes the answer. Rare; it gets a celebration. |
| `fail` | red ✕ | A dead end, a failed bar, a wrong assumption. Say what it taught. |
| `blocked` | orange octagon ! | Work is waiting on the owner: an approval prompt, an expired login, a decision, missing access. Give `ask`. |
| `nudge` | magenta diamond | The owner steered: a decision or instruction from them. On the owner's lane. |
| `decision` | violet hexagon | An orchestrator decision: budget move, new lane, an order to the lanes. |
| `review` | teal triangle | A reviewer or critic finding. |
| `spend` | bronze coin | Spend milestones. `patch.py` adds these itself when `spend.step` is set. |
| `sealed` | rosette with lock | A sealed commitment (a blind verdict, an embargoed result). Title and summary only. |

## How to…

**Append an event.** Put it in `events`. The page sorts by time; new events flash in the stream and nothing you are reading moves.

**Update a running event.** `edit` it, same id: change `summary`, `numbers` or `detail`. Don't append "still
running"; at most an importance-1 `update` when a real milestone passes ("6 of 12 done").

**Close an arc.**
```json
{ "events": [{ "lane": "sol", "kind": "success", "importance": 2, "title": "Blind run finishes on all 12",
               "summary": "Every document analysed with page checks; US$8.20 for the run.", "causedBy": ["e060"] }],
  "edit": { "e060": { "state": "done" } } }
```

**Raise a blocker** when `collect.py` shows `WAITING ON APPROVAL`, a lane says it is stuck on a login or a decision,
or a lane has been quiet far longer than its normal cycle:
```json
{ "events": [{ "ref": "b", "lane": "sol", "kind": "blocked", "importance": 3,
               "title": "Sol waits on a shell approval",
               "summary": "The Sol lane has been paused on an approval prompt since 02:10.",
               "ask": "Approve or deny the pending command in the Sol thread." }],
  "headline": { "status": { "tone": "warn", "text": "Blocked on approval", "note": "Sol paused since 02:10" } } }
```
**Clear it** when the work moves again: `"edit": { "e071": { "state": "cleared" } }`, plus a `nudge` (if the owner
acted) or `update` with `causedBy: ["e071"]`. Never leave a blocker open once the lane is moving.

**Correct a mistake.** Append a new event with `"supersedes": "<old id>"`. Don't delete history. Typos can be fixed
with `edit`.

**Finish.** Final beat, every lane `done` (the page already counts a lane as active only while it has an open start or blocker, or wrote in the last `staleAfterMin`), `"run": { "done": true }`, `status.tone` `done`. The page then opens in Story for anyone who has not picked a mode.

**Simplify the story** (after the run, or when a chapter closes). `python3 live/digest.py --missing` prints each
chapter's beats compactly; write `editChapters` with a `digest`, `outcome` and up to four `keyBeats` per chapter, plus
`run.digest`. Copy facts and numbers from the beats; don't add new ones. Finished runs open in Story, which lists each chapter
with its digest, outcome and key beats; Live and Detail show every beat.

## Metrics

The "Measures" tab appears once `metrics` has an entry. Add a point whenever a source reports a concrete value
worth tracking: recall, precision, pass rate, items done, cost per item, error count.

```json
{ "name": "Synthetic insights", "value": 33, "of": 43, "lane": "opus", "note": "V23" }
{ "name": "Cost per audit", "value": 0.55, "unit": "US$", "lane": "opus", "better": "lower", "note": "warm cache" }
```

When the value comes with an event, add `"event": "@ref"` so the point takes that event's time and lane.

`name` groups points into one card: keep it **exactly** the same each time (`patch.py` warns about near-duplicates).
A name with a single point shows as a single reading, not a card. `of` for fractions, `unit` for `%` or
`US$`, `better: "lower"` when down is good. Append; never edit old points.

## Style guide

- **Titles: plain words, one thought, 8 words or fewer.** "Detectors cry wolf on real documents", not "R01/R02
  over-flagging observed in canonical document batches".
- **Put the number in when it is the news:** "Page checks: 15 alarms down to 1".
- **Summary says what happened; `why` says why it mattered.** Someone should follow the run from titles and
  summaries alone — and be able to forward the "Write update" text to a stakeholder without editing much.
- **Codes (E15, V23, PR numbers) go in the summary or detail, not the title**, unless the code is the point.
- **No hype.** "Breakthrough" is the kind, not an adjective. Celebrate with the star, not with words.
- **Failures are part of the story.** Write what was learned: "Splitting the graph invents gaps".

## Worked examples

```json
{ "lane": "sol", "kind": "start", "importance": 2, "title": "Sol starts the all-12 blind run",
  "summary": "Frozen method E15 runs over every document batch, one fund at a time.", "state": "running", "causedBy": ["e055"] }

{ "lane": "sol", "kind": "update", "importance": 1, "title": "Blind run: 6 of 12 documents done",
  "summary": "No errors so far; US$4.10 spent on the run.", "causedBy": ["e060"] }

{ "lane": "opus", "kind": "fail", "importance": 2, "title": "Cold big-graph route costs too much",
  "summary": "From a cold cache the sectioned route costs US$2.90 on the largest graph, not US$0.55.",
  "why": "The cheap number needed a warm cache; the design needs bounded verification packets.",
  "numbers": [{ "label": "Cold cost", "value": 2.9, "unit": "US$" }], "causedBy": ["e053"] }

{ "lane": "opus", "kind": "breakthrough", "importance": 3, "title": "Both lanes agree on the blockers",
  "summary": "Independent methods flag the same three blocker types, each with cited pages.",
  "why": "Agreement between independent lanes is the strongest signal before an expert checks.",
  "detail": "- **Shared:** cross-document conflicts, count mismatches, missing source documents.\n- **Opus only:** table totals.\n\nAI-labelled; expert check pending.",
  "links": [{ "label": "Opus findings", "path": "opus/FINDINGS.md" }], "causedBy": ["e062", "e052"] }

{ "lane": "owner", "kind": "nudge", "importance": 3, "title": "Owner: start converging at 01:30",
  "summary": "Both lanes stop new experiments at 01:30 and the reserve pays for the cross-check.",
  "why": "Leaves time for the draft PR and the visual report before morning." }

{ "lane": "orch", "kind": "decision", "importance": 2, "title": "Model comparison lane gets US$150",
  "summary": "A new lane tests detector, verifier and writer substitutions under a US$150 cap." }

{ "lane": "astra", "kind": "review", "importance": 2, "title": "Review: query rate is AI-judged only",
  "summary": "The 83% sendable figure has no expert sample behind it yet.", "links": [{ "label": "Review", "path": "review/R2.md" }] }

{ "lane": "sol", "kind": "sealed", "importance": 3, "title": "Sol seals its blind verdict",
  "summary": "A ranked verdict for all 12 documents is committed before any outcome signal. Contents stay sealed." }
```

## What the page does with bad input

A file that won't parse → the page keeps its last good copy and says so. An event without `id`/`time` is skipped;
an unknown `kind` draws as `update`; an unknown `lane` gets its own track; a duplicate `id` → the later one wins.
`validate.py` (run by `patch.py`) catches all of these before install.

## Image snapshots

`images` is optional on any event except `sealed`:

```json
{"images":[{"path":"live/thumbs/check.jpg","caption":"Reviewed batch summary","full":"assets/check.png"}]}
```

`path` points to a small local snapshot, typically about 640 pixels wide. `caption` is optional plain text. `full` optionally opens the original. Paths are relative to the page and must stay inside its reviewed preview directory: no URL schemes, absolute paths, traversal, encoded path tricks, or `private/`. Up to three thumbnails appear on a beat in the stream; all appear in its detail, where each opens `full`. The validator checks path structure, not file existence or image contents. Inspect every image, caption, and original before including it, with one exception: a `snap.py` shot of a page the lead tagged with `[snap: …]`. The tag vouches for the page, and `snap.py` refuses error responses, blank pages and pages showing a denied term, so the keeper attaches those without opening them. Sealed events carry no images.
