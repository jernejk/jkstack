# Motion and sound

Motion explains or points; it is never decoration. Viewers reward energy in the music and tempo. They
notice crops that look like a bug and moves that cut an action off before it finishes.

## Motion

- Arrive slow, leave clean: entrances `expo.out` or `power3.out` over 0.5–0.9 s, exits 40–50% shorter,
  camera moves `power2.inOut` or `power3.inOut`. Overshoot eases only on small badges and numbers landing.
- Text: per-word blur-in (blur 8 → 0, opacity 0 → 1, 0.16 s, 60–90 ms apart). A landed title holds dead
  still. No breathing, floating or creeping scale on text or UI.
- Containers lead text: the card or window arrives, then its contents stagger in. Clear the old headline
  before the next one lands.
- One hero move per shot; secondary moves 100–200 ms later and smaller.
- Let the UI finish acting before cutting. Hold the proof still while it is read.
- Move a framed window as one object. A camera move inside a frame must look deliberate.
- Don't zoom content inside a still card, and don't repeat a layout or text treatment back to back.
- Transitions need a cause; use 3–5 kinds per film: a blur swap on one stage, an object that becomes the
  world (a citation chip grows into its source page), carry-across (cards shrink into graph nodes), a
  punch-in on the line that matters, a dip or cut between chapters.
- Deterministic: one paused timeline, explicit initial states, no wall-clock time, unseeded random, timers
  or network at render time. Measure layout once at initialisation.

## Sound

- A film over about 15 s gets a music bed and a few effects cued to visible events, unless silence is asked
  for. Always deliver a silent version too. Repro videos stay silent.
- Bring a track with a verified licence for the destination. Record its source, licence and version,
  required credit, and whether anyone listened to it. "Royalty-free" is not a licence.
- Cut scenes on bars and land key payoffs on downbeats.
- Effects, seeded or synthesised: a whoosh on scene cuts (vary the length), a soft pop when a card, badge
  or number lands, a click on a real pointer click. Peak one frame after the picture. Avoid dings and chimes.
- Mix starting point: high-pass the music around 70 Hz and low-pass around 9 kHz, duck it under the
  effects, and run two-pass loudness normalisation. Adjust for the track rather than dulling it.
  Targets: done videos about −20 LUFS; longer modes about −17 LUFS; true peak ≤ −1.5 dBTP.
- Credit the track beside the player or download, and wherever its licence and destination require.
  Not inside the video unless the licence asks for it.
