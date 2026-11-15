# Advanced extensions

These tools turn the blueprint into a repeatable pipeline. They are described, not bundled: each depends on
your renderer, browser automation and FFmpeg build. Build the ones you need and test them on your own footage.

## Recorder with markers

A wrapper around scripted browser recording that writes the video, `video-markers.json` and a human shot
list. Its calls mark trimmable dead time, point beats, region boxes (label and field together), pointer
positions with an intent (`idle`, `info`, `focus`), dwells and timestamped stills. A pointer overlay glides
to targets and ripples on real clicks. Marker boxes are in CSS pixels; when the video size equals the
viewport they map 1:1 to video pixels, otherwise scale by `min(videoW / viewportW, videoH / viewportH)` and
add the letterbox padding.

## Fake-clock frame capture

A helper that installs the browser clock, freezes CSS animation, then screenshots and advances one frame at a
time until a condition is true. It encodes the frames and holds the last one. Use it for sharp 2× footage of a
page's own animation.

## Markers to clips

A function that turns `video-markers.json` into composer clips: dead time trimmed, captions starting clips,
highlight markers becoming eased push-ins with a highlight frame, focus pointers becoming a pulse. It produces
a first assembly, not a final edit.

## Technical checker

A script that fails a render on the wrong codec, size or frame rate, a frame count that differs from the
manifest, a missing faststart atom, blank, black or white frames, music loudness or true peak out of range,
or a tool error. Long frozen runs and OCR hits are warnings: open the frame and judge it. It writes sampled
frames and a contact sheet for a person to read.

## Review sheets

A script that detects scene boundaries (or reads them from the manifest) and writes first, middle and late
frames per scene, a strip of three frames around every cut, and the scene midpoints scaled to 844 px and
390 px wide. A scene ends where the next starts, so a crossfade is not read as a scene's own late frame.

## OCR leak scan

OCR over sampled video frames and stills, matched against patterns you supply: hostnames, email addresses,
markup, customer names. It exits non-zero on a match so it can gate a build. OCR misreads, so a hit means
"look at this frame" and a clean run means "nothing obvious", not proof.

## Effects and mix

Seeded, synthesised effects (whoosh, pop, click) generated from the scene list, so a re-render produces the
same sound. A two-pass mix: duck the music under the effects with a sidechain, then normalise loudness to
the mode's target.

## Recaps from a live timeline

A previously-on or research episode can start from a [live-timeline](../../../skills/live-timeline/SKILL.md) feed. Take
the events since the last episode; chapters become parts; results, breakthroughs and dead ends become scenes;
image snapshots become stills; blockers become the open thread. Every scene still needs a claim-table row,
because a feed entry is a note about evidence, not the evidence.

## Journey films

A cinematic retrospective, anniversary, milestone or farewell, usually 3–4 minutes. It follows the same
evidence and privacy rules with different pacing: sparse text (around 50 added words), cause before effect,
holds measured from when the picture settles, and a story of change such as one question becoming a team's
capability, a pile becoming evidence, or a relay where what was learned passes on. Choose fresh licensed music
before fixing shot lengths, cut at matching musical phrases, keep the track's real ending, and put the biggest
earned payoff on its swell. End on achievements and gratitude unless a future result is properly established.
