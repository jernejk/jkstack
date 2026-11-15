# Modes

Two lessons shaped every mode. Short demos land better when they are less flashy and more to the
point. Recaps fail when they dump information: the result gets lost. One clear result per beat,
shown rather than described.

## done

One merged change or bug fix, 15–30 s, for the team or the business.

- Intro card (2–6 word title, brand mark) → the change in real UI → end card with the issue or PR
  reference, its title and one outro line.
- Before/after segments only when the before state is the point.
- Business viewers want the visible benefit, not statistics. Show at most one number, and prefer none.
- Captions of 7 words or fewer, sentence case, no jargon. Ticket numbers go on the end card only.
- Push in on the change, then hold still while it is read.
- Deliver silent and music versions.

## sprint-demo

A sprint review for stakeholders, 2–4 minutes. Either one film or a playlist of done videos with a
shared opening and close.

1. **Sprint goal** in one line, with the evidence rail already on screen.
2. **3–5 done beats**, most valuable to the audience first. Each is a compressed done video:
   one caption, the change in real UI, one held proof frame.
3. **Not done.** What slipped or was cut, said plainly. Carried-over work is labelled carried over.
4. **Next sprint** in one line.

Label each item's state honestly: merged is not released, staging is not production. Leave out items
that only make sense to the team; they belong in the written review.

## previously-on

An episode of an ongoing project, 1–3 minutes. The viewer saw the last episode, or should be able to
pick up without it.

- **Cold open:** the open thread from the last episode, in one line ("Last time: the import failed
  on large files").
- **Parts (2–3):** each opens with its question, then shows the result first, then what changed.
  Each result states its environment: lab, local, staging or production.
- **Setbacks belong in the story.** A failed experiment and what it taught is often the best part.
- **Close:** the open thread for the next episode.
- Build each episode from the evidence since the last one, never from the previous brief. Make an
  episode only when there is enough new activity.

A [live-timeline](../../../skills/live-timeline/SKILL.md) feed is a natural source: its chapters, results,
dead ends and snapshots map onto parts. See [extensions](extensions.md).

### Worked example

Episode 4 of a sample import tool. Evidence window: everything after episode 3's cutoff, 8 Nov 18:00 UTC,
up to 15 Nov 12:00 UTC. Episode 3 ended on "large files still fail".

| Time | Hero line | Picture | Rail | Claim |
|---|---|---|---|---|
| 0–5 s | Last time: large files failed | episode 3's held failure frame | `Recorded · 8 Nov` | C1 |
| 5–20 s | Can it import 2 GB? | progress bar completes on a 2 GB sample file | `Local build · sample data` | C2 |
| 20–34 s | Streaming fixed it | the diff summary, then memory holding flat | `Local build` | C3 |
| 34–50 s | Resume after a crash: not yet | a killed run restarting from zero | `Local build · open issue` | C4 |
| 50–60 s | Next time: resume | the open issue title | `Planned` | C5 |

Claim C2's row cites the run log and file size; C3 cites the merged PR and the memory graph's source; C4
cites the failing test. The open thread for episode 5 is C4. Nothing from before 8 Nov 18:00 appears
except the cold open, which is labelled as a recording from the last episode.

## research

An experiment, spike, evaluation or research night, 1–2.5 minutes.

1. **Question** as the audience would ask it.
2. **Method in one picture:** what was compared, on what data, judged how. Name the judge (a person,
   a script, an AI scorer) on screen.
3. **Result first,** with its denominator and qualifier: `7 of 10 sample cases · AI-scored, human
   check pending`. A lab score never reads as production accuracy.
4. **Surprises and dead ends.** Retained failures build trust.
5. **Decision:** adopt, reject or run again, and what it costs to find out more.

## release

What shipped and what is coming, 1–2.5 minutes, in the previously-on shape. Keep these states separate
on screen and in the claim table: merged → in a release → staging → production, each with its time.
Upcoming work is labelled upcoming. A pending PR never reads as shipped.

## concept

A feature, mockup or proposal film, 45–95 s. One concrete worked example from start to finish,
not a feature tour.

1. **Hook (0–7 s):** the result in one line with its number.
2. **The thing working:** a real or saved, labelled answer, one framing held while the UI acts.
3. **One diagram that grows:** each piece of evidence enters when named.
4. **Proof:** a real click into a real source; punch in on the line that matters.
5. **Honest edge:** a conflict kept visible or a recorded miss.
6. **Payoff and end card:** the takeaway answers the hook; `Concept · not a released feature` when true.

## walkthrough

How to do one task, 30–90 s. Show the finished result for a second, then the steps in real UI with
a visible pointer, then the finished result again. One caption per step. Let every action finish
before cutting. No feature detours.

## repro

A bug report clip, 10–30 s. Environment and version on the rail, the steps at real speed with a visible
pointer, then the failure held still for at least two seconds. State the expected result in one line of
text. No music. Attach it where the bug is tracked only when asked.
