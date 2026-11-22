# The lead log

A plain Markdown file the work writes as it goes, one line per beat. `collect.py` parses each new line into a draft event itself (time, lane, model, kind, state, chapter, metrics, images, status), so the keeper only writes short titles and links results to their starts. A cheap model keeps a good story for few tokens, and the facts never pass through it.

Set `"leadLog": "LEAD-LOG.md"` in `live/keeper/config.json` (`init.py --lead-log LEAD-LOG.md` does it).

The orchestrator writes it. Lanes can append their own lines too.

## Line format

```text
- HH:MM (lane) [tag] One line that already reads as the event's summary, with the number that matters.
- HH:MM (lane/model) [start] The same, naming the model that does the work.
```

- `HH:MM`: when it happened, in the run's timezone. Append; never rewrite a line. A time more than 6 h earlier than the line before means the next day, and one more than 18 h later is a late line from the day before; `[date: YYYY-MM-DD]` sets the day outright.
- `(lane)`: a lane id from the feed (an unknown id becomes a new lane). `(lane/model)` also records the model: write it on every `[start]`, so the page can show which models ran, where and for how long.
- `[tag]`: any number of them, anywhere on the line. Text in `` `code` `` is never a tag; an argument may hold one level of `[…]`.
- Indented lines under a beat belong to it: append a beat and its indented lines in one write. Anything else that isn't a beat is shown to the keeper as `UNPARSED`, and so is a bad time or date. End every line with a newline; an unfinished last line waits for the next pass.

| Tag | Becomes |
|---|---|
| `[start]` | a `start` event, `"state": "running"` |
| `[result]` | `success` |
| `[fail]` | `fail` |
| `[breakthrough]` | `breakthrough`, importance 3 |
| `[decision]` | `decision` |
| `[nudge]` | `nudge` on the owner's lane |
| `[review]` | `review`, with the reviewer's start set to `done` |
| `[blocked: what the owner must do]` | `blocked` with that `ask` (`[blocker: …]` too; a bare `[blocker]` stays text) |
| `[ask: question \| choice A \| choice B]` | `blocked`, with the question as `ask` and the options as `choices`: use it whenever the work waits on the owner's pick |
| `[cleared]` | the newest open blocker on that lane is cleared (on the owner's lane: the newest anywhere) |
| `[done: title or id]` | that start is set to `done` (an id, or words from its title; unmatched ones are listed for the keeper) |
| `[metric: Name = value unit]` | a point in `metrics` with `"event": "@ref"` for the line's event (or the line's `time`); keep the name identical every time |
| `[snap: target …]` | run the snapshot command from the header and attach the images; tagging a page vouches that it is safe to show |
| `[status: good\|warn\|bad\|done text]` | `headline.status` |
| `[progress: 3/6 label]` | `headline.progress` |
| `[best: text]` | `headline.best`, pointing at this event |
| `[chapter: Title — one-sentence summary]` | a new chapter that starts here: copy the title and summary as written, `start` = the line's time |
| `[key]` | importance 3: one of the few beats that belong in the run's summary |
| `[img: path \| caption]` | an image you have reviewed, relative to the work folder; `collect.py` makes the thumbnail (symlinks into `private/` are refused) |
| `[model: name]` | the model, when the lane slot doesn't carry it |
| `[thread: id]` | the T3 thread doing the work, so the page can link to it |
| `[end]` | the run is over |
| none | an `update`, importance 1 |

Tags add to the line's event; they never make an event of their own. A line whose only tags are `[status:]`, `[progress:]`, `[best:]`, `[metric:]` or `[done:]` changes the headline, metrics or that start, and adds no event.

## Header

The lines above the first beat are for the keeper. Use them for the date, the timezone, and the snapshot command with the meaning of any `[snap: …]` words:

```text
# Lead log: catalogue import (2026-11-16, UTC+10)
Snapshots: python3 live/snap.py --name HHMM-<target> --before <old URL> --after <new URL>
(use the Python that has Playwright, e.g. ~/.venvs/web/bin/python, if the default one doesn't).
`options` opens the menu first.
```

## Example

```text
- 00:31 (lead/opus) [start] Three read-only reviews start: visual polish, engine power use, copy.
- 00:41 (lead) [breakthrough] With the GPU on, a transform glide costs 4.6% of a core; the old repainting glow 15.8%.
- 00:46 (lead) [result] The glow drifts smoothly again, within 4/255 of the old frame. [metric: Idle CPU = 6.5 %]
- 00:50 (lead) [result] Options menu replaces four buttons; the corner badge is gone. [snap: cover options]
- 00:52 (owner) [nudge] Owner: keep tonight on a live timeline with a cheap keeper.
- 01:12 (lead) [ask: Which glow ships? | Soft | Sharp] Both glows pass; the owner picks one.
- 01:30 (lead) [status: good On track] [progress: 5/6 asks done]
```

## Why it works

- The facts, times and numbers come from the one agent that knows them, so the keeper can't invent them.
- Tags make each beat's kind explicit, which leaves the keeper only to reformat.
- One file and one cursor: `collect.py` shows only the new lines as a draft, so each cycle costs a few hundred tokens of input, and `collect.py --wait` returns only when something changed.
- Status gets its own trigger: write `[status: …]` when the headline should change, and `collect.py` flags a status older than 20 minutes.
