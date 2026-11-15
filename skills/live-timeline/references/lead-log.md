# The lead log

A plain Markdown file the work writes as it goes, one line per beat. The keeper turns each line into a timeline event. Because the writer already knows what happened, the keeper only has to translate, so a cheap model keeps a good story for few tokens.

The orchestrator writes it. Lanes can append their own lines too.

## Line format

```text
- HH:MM (lane) [tag] One line that already reads as the event's summary, with the number that matters.
```

- `HH:MM`: when it happened, in the run's timezone. Oldest first. Append; never rewrite a line.
- `(lane)`: a lane id from the feed.
- `[tag]`: any number of them, anywhere on the line.

| Tag | Becomes |
|---|---|
| `[start]` | a `start` event, `"state": "running"` |
| `[result]` | `success` |
| `[fail]` | `fail` |
| `[breakthrough]` | `breakthrough`, importance 3 |
| `[decision]` | `decision` |
| `[nudge]` | `nudge` on the owner's lane |
| `[review]` | `review`, with the reviewer's start set to `done` |
| `[blocked: what the owner must do]` | `blocked` with that `ask` |
| `[cleared]` | the open blocker on that lane is cleared |
| `[done: title or id]` | that start is set to `done` |
| `[metric: Name = value unit]` | a point in `metrics`; keep the name identical every time |
| `[snap: target …]` | run the snapshot command from the header and attach the images; tagging a page vouches that it is safe to show |
| `[status: good\|warn\|bad\|done text]` | `headline.status` |
| `[progress: 3/6 label]` | `headline.progress` |
| `[best: text]` | `headline.best`, pointing at this event |
| `[chapter: Title — one-sentence summary]` | a new chapter that starts here |
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
- 00:31 (lead) [start] Three read-only reviews start: visual polish, engine power use, copy.
- 00:41 (lead) [breakthrough] With the GPU on, a transform glide costs 4.6% of a core; the old repainting glow 15.8%.
- 00:46 (lead) [result] The glow drifts smoothly again, within 4/255 of the old frame. [metric: Idle CPU = 6.5 %]
- 00:50 (lead) [result] Options menu replaces four buttons; the corner badge is gone. [snap: cover options]
- 00:52 (owner) [nudge] Owner: keep tonight on a live timeline with a cheap keeper.
- 01:30 (lead) [status: good On track] [progress: 5/6 asks done]
```

## Why it works

- The facts, times and numbers come from the one agent that knows them, so the keeper can't invent them.
- Tags make each beat's kind explicit, which leaves the keeper only to reformat.
- One file and one cursor: `collect.py` shows only the new lines, so each cycle costs a few hundred tokens of input.
- Status gets its own trigger: write `[status: …]` when the headline should change, and `collect.py` flags a status older than 20 minutes.
