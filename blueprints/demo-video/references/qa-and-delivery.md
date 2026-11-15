# Review and delivery

Never trust "looks great" from anyone who has not inspected the render, yourself included.

## Stages, in order

| Stage | How | Evidence |
|---|---|---|
| Lint | the renderer's composition linter; stop on errors | lint summary |
| Storyboard frames | snapshots at each scene's first readable moment, midpoint, late hold, and ±0.2 s around each cut | the images you read |
| Claims | on-screen text inventory and claim table; independent fact-check for films with numbers | fact-check rounds |
| Render | render → encode → music and effects mix → web copy → poster | files on disk |
| Technical | codec, exact frame count, faststart, blank, flat or frozen frames, loudness and true peak, OCR scan for leaks | a checks report |
| Visual | scene grid, cut strips, 844 px and 390 px phone sheets; read all of them | sheets |
| Playback | play the delivered file at normal speed, with sound | say whether it was done |

Loudness checks measure sound; they don't hear it. Say "measured, not heard" unless someone listened.

## What to look for

- Text clipped at an edge, under the rail, or crossing another element; captions over the action.
- An entrance caught mid-flight that never completes before the cut; a label from the last scene surviving
  into the next.
- Blank or flat frames at cuts. A white flash on a pale scene fails a flat-frame check; use a wipe or blur swap.
- A capture showing content beyond its element, header bars, signed-in names, or costs and timings that read
  as performance claims. Mask them.
- Anything a stranger could not read at 844 px.

## Delivery

- `<id>.mp4` silent, `<id>-music.mp4`, `<id>-web.mp4` (CRF about 30, small enough for a web page) and a
  `.jpg` poster. Give absolute paths.
- Put the music credit beside the player.
- `REVIEW.md` in the film folder: creative calls, what was measured, looked at or not checked, the weakest
  shot, and warnings kept on purpose.
- Keep originals. A remake goes in a new dated folder; never overwrite a delivered film.

## Where it can go

Suggestions, each needing its own explicit authority:

- Attached to the PR or issue the change came from, as an upload rather than a committed file.
- Embedded in a sprint review deck or a release notes page.
- A team portal or internal video channel, with the music credit in the page footer.
- A hosted share page for a single film, set to private until the owner shares it.
- A public video platform, with the credit and licence links in the description.

Bound any upload or publish step with a timeout, and confirm the destination's visibility before sharing.
