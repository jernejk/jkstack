---
name: demo-video
description: >-
  Plan and build short, evidence-first videos about software work: done videos for one change, sprint
  demos, "Previously on" recaps, research results, releases, concept films, walkthroughs and bug repros.
  A blueprint: brief, claim table, storyboard, pacing, branding and review, for any HTML-to-video
  renderer. Use for "make a done video", "sprint demo video", "previously on", "recap video",
  "research video", "release video", "repro video". Not for CI assertions. Publishing needs explicit authority.
metadata:
  version: "0.1.0"
  updated: "2026-11-15"
  category: evidence
---

# Demo video

A video here is evidence first and a film second. Every frame shows something real, labelled for what
it is, readable on a phone, and timed so the result lands before the detail.

This is a blueprint, not an installed skill. It describes a method that has produced real films, but it
bundles no renderer, recorder or checker. Use the tools you have; [extensions](references/extensions.md) describes the ones
worth building. Resolve reference paths relative to this skill folder.

## 1. Pick the mode, then write the brief

| Mode | Use for | Length | Shape |
|---|---|---|---|
| **done** | one merged change or bug fix | 15–30 s | intro card → the change in real UI → end card with the issue or PR |
| **sprint-demo** | a sprint review for stakeholders | 2–4 min | sprint goal → 3–5 done beats, most valuable first → not done → next |
| **previously-on** | an episode of an ongoing project | 1–3 min | last open thread → parts: question → result → what changed → next thread |
| **research** | an experiment, spike or research night | 1–2.5 min | question → method in one picture → result with its denominator → surprises → decision |
| **release** | what shipped and what is next | 1–2.5 min | recap shape with merged → released → staging → production states |
| **concept** | a feature film, mockup or proposal | 45–95 s | result hook → one worked example → proof → honest limit → payoff |
| **walkthrough** | how to do one task | 30–90 s | finished result → steps in real UI → finished result again |
| **repro** | a bug report | 10–30 s | environment → steps → the failure, held → expected result in text |

Per-mode detail: [modes](references/modes.md). Retrospectives, anniversaries and farewells are the
journey extension in [extensions](references/extensions.md).

Before any capture, write `BRIEF.md` in the film folder: mode, audience, the **one takeaway**, viewing
width (default: a phone, 844 px landscape and 390 px portrait player), brand profile, the evidence class
of every scene, deadline and outputs. Ask only for what you cannot infer from the request or sources.

## 2. Non-negotiables

- **Evidence before art.** Show real UI, real saved output and real source pages. Never paint a state
  that did not happen, invent a number, or imply speed, release or production use. Every fact on screen
  has a row in the claim table before its scene is built ([evidence](references/evidence.md)).
- **Label what it is, on screen, all the time.** A rail outside the camera states the evidence class:
  `Local build`, `Concept demo · sample data`, `Recorded answer · replayed`, `Staging`, `Production`.
  Concepts and mockups never pass for shipped features.
- **Result first.** The takeaway and one hero number or visible result land within about 1.5 s of a
  scene starting and stay until the cut. Scene length ≥ 1 s + words ÷ 3 + 1.5 s hold
  ([pacing](references/pacing-and-phone.md)).
- **Readable on a phone.** Hero text ≥ 80 px at 1080p; anything a viewer must read ≥ 36 px. Too many
  words: cut words or recompose, never shrink.
- **Sharp UI.** Capture proof at 2× density and show it at ≥ 1.0 scale or punch in. Never upscale a dense
  1080p screen and call it a close-up.
- **Approved brand only.** Personal or company branding comes from a brand profile and that brand's
  approved assets ([branding](references/branding.md)). Never redraw, recolour or approximate a logo.
- **Licensed sound.** Music and effects need a verified licence and the credit it requires.
- **Done means verified.** Report technical checks, inspected frames, playback at speed and listening
  separately. The requester's acceptance is its own state ([review](references/qa-and-delivery.md)).

## 3. Work loop

1. **Brief and claims.** `BRIEF.md` and the claim table. For films with numbers, have an independent
   reviewer, ideally a different model family or a person, check the final on-screen text, including text
   inside screenshots, before the full render.
2. **Storyboard in words.** One line per scene: time window, hero line, picture, evidence label, sound
   cue, how it hands off. Pick the 3–5 transition kinds the film uses and what causes each.
3. **Capture** ([capture](references/capture.md)). Scripted browser flows for interactive footage,
   fake-clock frame capture for a page's own animation, 2× element screenshots for stills.
4. **Compose** ([composer](references/composer.md)). Short modes suit a spec-driven composer; longer
   modes suit a hand-built composition on one paused timeline with scenes on a bar grid.
5. **Look before rendering.** Snapshot every scene's first readable moment, midpoint, late hold and both
   sides of each cut. Fix collisions, clipped text, empty frames and anything a stranger could not read.
6. **Render, mix, verify.** Render, encode, mix music and effects, run the technical checks, then read
   the contact sheet, cut strips and phone sheets yourself ([motion and sound](references/motion-and-sound.md)).
7. **Deliver.** Silent, music and web copies plus a poster, the music credit beside the player, and a
   `REVIEW.md`: what was measured, what was only looked at, and the weakest shot.

## 4. Toolchain

Any renderer that produces frames deterministically will do. HyperFrames (Apache-2.0) and a frame-capture
script piped to FFmpeg render HTML compositions directly. Remotion (React; check its company licence terms
first) and Motion Canvas (TypeScript scenes) have their own scene models; the composition contract in
[composer](references/composer.md) translates to them. Browser automation such as Playwright drives
capture. FFmpeg encodes, mixes and measures. Pin renderer versions and turn off telemetry where offered.

## 5. Authority

Making a film authorises local capture, composition and verification. It does not authorise uploads,
messages, PR or issue comments, product changes or publication. Use sample or approved fictional data;
never show client, customer or staff names without approval, and never zoom into a signed-in identity.

## References

| Need | Read |
|---|---|
| Mode profiles and story shapes | [modes](references/modes.md) |
| Claims, labels, status states, fact-check | [evidence](references/evidence.md) |
| Reading time, text sizes, phone widths | [pacing and phone](references/pacing-and-phone.md) |
| Motion, transitions, music and effects | [motion and sound](references/motion-and-sound.md) |
| Personal and company brand profiles | [branding](references/branding.md) |
| Capture techniques and traps | [capture](references/capture.md) |
| Done-video spec and composition contract | [composer](references/composer.md) |
| Review stages and delivery suggestions | [review and delivery](references/qa-and-delivery.md) |
| Recorder, checkers, recaps from a timeline, journey films | [extensions](references/extensions.md) |
