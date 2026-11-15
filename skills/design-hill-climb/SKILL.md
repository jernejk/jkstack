---
name: design-hill-climb
description: >-
  Improve a real UI (dashboard, app screen, portal page) by hill-climbing on scores from cross-lab model
  reviewers: render with real data, screenshot, review, fix, repeat until every gating reviewer rates every
  rubric dimension at the bar and the candidate beats its references. Use for "hill-climb this UI",
  "iterate against these reference screens", "UI polish loop", "council review this design", `/design-hill-climb`.
  Not for UI with a programmatic done-check (use tests/evals) or one-off mockups.
metadata:
  version: "0.1.0"
  updated: "2026-11-05"
  category: design
---

# Design hill climb

Model scores for UI are noisy: the same screenshot can get three different numbers. They become usable when
the reviewer compares against references, never sees the target, and starts fresh each round, and when
several independent reviewers compare them. Scores guide iteration; they are not calibrated measurements of human preference. Use your harness's supported browser and review facilities in Claude Code, Codex, or T3 Code. Do not assume a particular provider or model name.

## 0. Set up (before round 1)

Work folder holds `PLAN.md`, `ROUNDS.md`, `before/`, `refs/`, `round-N/`, `after/`.

1. **Feedback in the owner's words.** Quote the owner's complaint; it decides the rubric.
2. **Rubric: 3 to 5 named dimensions** taken from that complaint (the dashboard used findability, insight
   surfacing, readability, usability). For anything that shows numbers, add **truthfulness**: every label,
   unit and denominator matches the data and code.
3. **References.** `before/` plus 1 to 3 best-in-class screens of the same kind of product in `refs/`
   (competitors, the owner's own best page). Without references, scores inflate and drift.
4. **Render command and screenshot matrix.** Authorized representative data, a supported browser capture tool, 1440 px and 390 px, top and full,
   every theme the page has. Keep the same matrix every round.
5. **Programmatic gates.** Tests, leak check, no horizontal scroll at 390 px, clipped or overlapping text,
   WCAG contrast. Run them before every review; a review never replaces them.
6. **Budget.** Round cap (default 4), bar (default 9), and a token or dollar ceiling. Log spend per round. No new metered calls or delegation until the owner authorizes a ceiling and the review lanes. Use a hard runner cap for unattended paid work; if costs cannot be bounded, stop before dispatch. Zero new paid API spend by default.

## 1. Each round

1. Build with the current implementation agent. Round 1 starts with an information-architecture plan in `PLAN.md`.
2. Render, screenshot into `round-N/`, run the gates. Fix gate failures before review.
3. Review with **fresh reviewers**: a new independent review task per round through the harness's supported task facility. Use T3 Code tasks when available there, native tasks in other harnesses. Never launch review CLIs to bypass harness restrictions. If delegation is unavailable or not authorized, stop at a documented local design pass and mark independent review unverified.
4. Write the round into `ROUNDS.md`: what changed, every reviewer's scores (candidate and references), the
   asks, and the round's spend.

### Reviewer brief: what to include and what to withhold

Include: the feedback quote, rubric, screenshot paths for candidate, `before/` and `refs/`, HTML and code paths,
and the previous round's asks as a **checklist to verify** (fixed / partly / not).

Withhold:
- the bar and any target score ("route to 9" counts);
- earlier scores ("you scored 7/6/7/6");
- "this is the final round";
- which label is the candidate, where practical: name screens A, B, C and ask for fixes for A.

Ask for: a score per dimension for **every** screen (candidate and references), ranked concrete fixes for the
candidate, and regressions or correctness bugs. Terse.

### Gating reviewers, staged by cost

1. One fresh reviewer from a different model family than the builder, using an owner-approved model and cost ceiling, until each dimension reaches the bar.
2. Then add a second fresh reviewer from another family when budget permits. Never the builder: builder self-scores are notes and never count toward the stop rule.
3. A third opinion is optional. Several reviewers from one family may share blind spots; do not call them fully independent.

Stage reviews to stay within the agreed budget. An unreturned review is pending; never count it as agreement. Keep round and wall-clock limits even if a reviewer stalls.

## 2. Stop rule

Stop when every gating reviewer rates every dimension at or above the bar **and** the candidate scores at or
above each reference, or at the round cap, or at the budget ceiling.

- Anything changed after the last review is **unreviewed**: run one more review, or mark it unreviewed in
  `ROUNDS.md` and the change summary.
- New scope mid-loop (a new feature, a theme) re-opens the loop for the dimensions it touches.
- Reviewers reward removal. If colour, density or personality keep dropping across rounds, ask the owner before
  climbing further.

## 3. Human checkpoint

The first time the bar is met, show the owner an **annotated change sheet**: before/after crops side by side with an
arrow and one line per change (PIL is enough). The owner sets direction (brand, mascots, colour, what is too loud);
the loop does the polish. Fold their feedback in as the next round's brief, in their words.

## 4. Deliver

`after/` screenshots, the change sheet, `ROUNDS.md` with a score table per round per reviewer (references
included), and a local change summary carrying that table and naming anything unreviewed. Create or publish a PR only when the owner requests it.
