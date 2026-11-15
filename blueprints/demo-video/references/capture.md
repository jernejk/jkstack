# Capture

## Which technique

| Footage | Technique |
|---|---|
| An interactive flow with a visible pointer and clicks | Scripted browser recording with markers |
| A page's own animation (streaming answer, replay, chart build), sharp | Fake-clock frame capture at 2× density |
| Proof stills: dialogs, source pages, table rows | Element screenshots in a 2× device-scale context |

Browser video recording usually captures at CSS pixel size and ignores device scale, so footage is 1:1 with
the viewport. For close-ups, use stills or frame capture at 2× with a smaller viewport: 960×540 at 2× gives a
1920×1080-sharp picture of a 960 px-wide layout.

## Scripted recording

- Record done, walkthrough and repro footage at 1920×1080.
- Emit markers as you go, not afterwards: a point beat, a region box, a pointer position, trimmable dead
  time (login, loading), a dwell, a timestamped still. Each marker carries a kind (`bug`, `fix`, `before`,
  `after`, `state`, `step`) and an optional caption of 7 words or fewer.
- Draw a visible pointer that glides to each target and ripples on a real click. A synthetic
  `dispatchEvent('click')` shows no click, so drive real clicks.
- Finish the recording in a `finally` block so a selector miss still keeps the footage.
- Record the offset between the marker clock and video time; editors need it.
- Write a human shot list next to the machine-readable markers.

## Frame capture with a fake clock

Install the browser's fake clock before navigation, load the page, then pause the clock (in Playwright,
`clock.install()` → `goto` → `clock.pauseAt()`). Installing alone does not stop time. Once paused, the page's
timers and animation frames move only when you advance them. Screenshot, advance 1/30 s, repeat until the
page reaches its final state, then add a tail. Inject CSS that disables CSS animations and transitions,
which the clock does not drive. Network responses still arrive in real time, so replay saved responses
rather than capturing a live stream.

- Clip to the element's final size and pin it while capturing, or content below it leaks into the frame.
- Track the element's position per frame; layout above it can shift during the replay.
- Record any injected CSS in the capture notes: layout-only changes, never content.
- Encode the frames and hold the last one for the scene's reading time.

## Traps

- Start from a known data state so the before → action → after story is clean.
- Headers often show the signed-in user's name or initials. Frame below them or use a demo account.
- Native `title` tooltips don't render in headless browsers. Hover states must follow an element that moves.
- Screenshot animated counters only after they settle, or with the fake clock.
- Rebuilding an app while recording it can desync its assets. Freeze the build before capture.
