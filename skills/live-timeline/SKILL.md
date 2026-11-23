---
name: live-timeline
description: Follow a long-running task with a live story of chapters, causal arcs, results, blockers, image snapshots, spend, and measures. Use when you want to watch a build, research run, migration, or overnight task unfold. Not a retrospective report or a Gantt plan.
---

# Live timeline

A fixed HTML page renders `live/events.json`. A keeper reads selected logs and writes story beats. It observes the work without steering it. The page has no run data embedded in it. It refreshes every minute and keeps its last good feed if a read fails.

Works with Claude Code, Codex, and T3 Code. Resolve `SKILL_DIR` to this installed skill folder; do not assume a harness-specific path.

## Scaffold

```sh
python3 "$SKILL_DIR/scripts/init.py" ./work \
  --title "Catalogue import" --owner Owner \
  --lanes "main:Main lane,check:Check lane" --budget 50 --tz UTC
```

The work folder receives `live-timeline.html` and `live/`: feed, schema, helpers, and `keeper/config.json`. They work independently of this installation. `--upgrade` refreshes the page, helpers, and schema while preserving the feed and config. `--force` resets an existing run; use it only when requested. `--empty` leaves out the starter chapter and event, for seeding a story that began before the scaffold. An owner listed again in `--lanes` is not duplicated. `--lead-log LEAD-LOG.md` switches the keeper to lead-log drafts.

Inside T3 Code (`T3CODE_THREAD_ID` is set), `init.py` records the lead's thread in `run.t3`, so the page links "Needs you" and the header to that thread, and watches its subagent threads. `--no-t3` turns this off. Put `[thread: <id>]` on a lane's `[start]` line to link that lane to its own thread.

## Configure and seed

Read [the schema](references/schema.md) for fields, style, and patch examples.

- `sources`: allowlisted log globs relative to the work folder, or explicit absolute paths. `exclude` filters sources; `private/` is always excluded. Do not use globs over your home directory. Source content remains visible to the keeper model, so choose it carefully.
- `jsonlDropKeys`: fields removed from collected JSON lines. This is a convenience filter, not a secrets scanner.
- `spend.sources`: local text files and regular expressions with a numeric capture group. Patches sum these into the headline. The budget display does not enforce spending limits; the work's runner must enforce them.
- `deny`: optional phrases, a word file, or directory names to catch in the feed. Keep deny lists, source logs, config, and private material outside the served directory. Review captions, images, and link targets separately; the validator cannot see pixels or determine whether a file is private.
- `t3`: optional `root` or title filters, `quietAfterMin`, and `db` for a read-only local state database. Empty filters disable database access. The adapter supports specific projection layouts and reports unavailable on others; logs alone work in every harness. Discover your own thread ids through your harness. Never ship them in a skill.

Read existing logs once and seed chapters, starts, outcomes, and owner nudges with `patch.py`. Titles use at most eight words; summaries are one line. Results link to starts with `causedBy`. Give new chapters a `ref` and point events at `"chapter": "@ref"` rather than guessing ids. After seeding, run `python3 work/live/collect.py --mark` so the keeper's first pass doesn't narrate the seed again.

```sh
python3 work/live/patch.py <<'JSON'
{"events":[{"lane":"main","kind":"start","importance":2,"state":"running","title":"Import begins","summary":"The first batch is being checked."}]}
JSON
python3 work/live/validate.py
```

`images` adds reviewed snapshots to an event. Use relative local image paths and optional captions and full-size paths. Sealed events cannot contain images, details, numbers, or links.

## Serve only reviewed output

`fetch` needs HTTP. Create a separate preview directory containing only the page, `live/events.json`, and reviewed image/evidence files at their feed-relative paths. Do not serve the working directory: it contains keeper config and logs.

```sh
python3 -m http.server 8470 --bind 127.0.0.1 --directory ./preview
```

This is a local preview. Remote access needs the owner's chosen authenticated hosting and explicit publication authority. Check desktop and phone widths, each theme, and an image popup before sharing a URL. Browser storage caches the feed; clear site data after sensitive runs.

## Keep the story current

Use [the keeper brief](references/keeper-brief.md). The cheapest reliable setup is a **lead log** ([format](references/lead-log.md)): the orchestrator appends `- HH:MM (lane/model) [tag] summary` lines as it works. `collect.py` parses them into a draft patch itself, and the keeper only adds titles and `causedBy` links, so even a small model such as GPT-6 Luna keeps an accurate story: times, numbers, kinds, chapters and images never pass through it. `collect.py --wait 20m` blocks until a source changes (on a quiet timeout it prints `QUIET` and collects nothing: send `{}` as the heartbeat), and its cursor advances only when `patch.py` installs, so a failed or truncated cycle repeats instead of losing lines. `live/recent.py` gives the keeper a one-screen view of the feed instead of the whole file, and `live/snap.py` takes before/after screenshots, checks them itself and prints the `images` JSON (needs Python Playwright). `collect.py` keeps its output under `maxChars`, holding the rest for the next pass, and ends with a NEXT line listing what the cycle's one patch must cover. In Claude Code or Codex, run a keeper only through supported task/background facilities and only when delegation is authorized. In T3 Code, use its task facility when available. Otherwise update the feed inline at milestones; a separate agent is optional. No new paid calls or recurring schedules without authorization and a cap.

A cycle reads `collect.py`, selects meaningful changes, and patches the feed. An empty patch is a heartbeat. Use a bounded cadence, normally ten minutes, and stop at the agreed deadline, budget, or completed run. A quiet lane is evidence of silence, not proof of a blocker. A keeper restart resumes from the feed and `keeper/state.json`.

The headline shows status, best result, open asks with their choices, spend, and active lanes with their models. "Lanes and models" lists each lane's state and each model's starts, busy time and work. The ribbon folds quiet gaps and draws closed starts as bars; cards and popups show reviewed snapshots. Busy and finished runs open in **Story** view: one card per chapter with its digest, outcome, hero image and key beats. **Highlights** shows the key beats in full and **Full** shows everything. The **Write update** button and `brief.py --since today` draft text; they never send it. Review text before sharing.

At the end, close running starts and blockers accurately, mark completed lanes `done`, set `run.done: true`, and set `headline.status.tone: done`. Then **simplify the story**: `python3 work/live/digest.py --missing` prints each chapter's beats in about 1.5k tokens; one model pass writes `editChapters` digests, outcomes and key beats plus a three-line `run.digest`, which Story view and **Write update** use. Without digests the page still picks key beats itself. Stop the keeper. Do not mark incomplete work as successful to make the page look finished.

## Boundaries

Change the feed only through `patch.py` or `validate.py --install`, which validate before atomic replacement. Use one writer per feed; concurrent patches are not supported. Use source timestamps, not observation time. Metrics must be measured. Keep private evidence outside the preview; a deny list is only a backstop.
