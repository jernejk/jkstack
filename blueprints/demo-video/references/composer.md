# Composer

Short modes (done, repro, walkthrough, and each beat of a sprint demo) repeat one structure, so a composer
driven by a spec file pays off. Longer modes are better hand-built on the same contract.

## Pipeline

```text
spec.json + brand profile + footage
  → HTML composition (cards, clips, captions, push-ins, rail)
  → lint → frame render → H.264 encode
  → music mix (silent and music copies) → poster
  → technical checks → review sheets
```

Output files: `<id>.mp4` (silent), `<id>-music.mp4`, `<id>.jpg` poster and `<id>.manifest.json`. The
manifest lists scenes, their times and the measurement targets, so the checks know what to expect.

## Done-video spec

```json
{
  "id": "1234-draft-survives-popout",
  "brand": "brand-contoso.json",
  "character": "helper",
  "reference": 1234,
  "referenceTitle": "A draft is lost when the chat is popped out",
  "title": "Pop out, keep your draft",
  "outroLine": "Bigger window, same draft.",
  "evidence": "Local build · sample data",
  "clips": [
    { "markers": "before/video-markers.json", "segment": "before", "evidence": "Production · before the fix" },
    { "src": "raw/take1.mp4", "in": 10.8, "out": 14.3, "speed": 1.2, "hold": 0.5,
      "caption": "Then pop the chat out", "captionPos": "bottom-left",
      "zoom": { "x": 900, "y": 380, "w": 1010, "h": 568 },
      "highlights": [{ "at": 11.1, "dur": 1.0, "rect": { "x": 1482, "y": 683, "w": 388, "h": 66 } }],
      "pointers": [{ "at": 13.4, "x": 1837, "y": 414 }] },
    { "src": "raw/take1-popout.mp4", "in": 0, "out": 3.8,
      "transition": { "type": "grow", "origin": { "x": 1837, "y": 414 } } }
  ]
}
```

- **Card fields:** `id`, `brand`, optional `character`, `title` (2–6 words), `outroLine`, optional
  `reference` and `referenceTitle` (verbatim from the tracker), `evidence` (the default rail text),
  `musicStart`, `maxMB`, `poster: {t}`.
- **Clip fields:** `src`, or `image` plus `duration`; `in`, `out`, `speed` (≥ 1), `hold`; `evidence` when
  this clip's evidence class differs from the default; a `zoom` rect in source pixels, grown to 16:9 and
  capped around 2.6×; `caption` and `captionPos`; `highlights` and `pointers`; `segment: before | now`;
  `transition` of `rise`, `grow`, `dip` or `dissolve`; `join: cut`.
- **Times:** `in`, `out` and every `at` are seconds in the source file, so they survive trims and speed
  changes. Durations such as a highlight's `dur` and `hold` are seconds of output.
- **Markers:** `{ "markers": "...json" }` expands a recording into a first assembly. Dead-time spans are
  trimmed, captions split clips, highlights become push-ins and focus pointers become pulses. Treat it as a
  draft edit and tune the clips by hand.
- Contiguous clips from one source share one camera. A source change rises in; a time jump within one source
  dips through the stage colour.

## Card templates

| | Personal | Contoso |
|---|---|---|
| Stage | dark stage, light text | off-white stage, white UI window, ink text |
| Intro | title left, name small | character left, product title right |
| End | `PR 42` with a one-line outro and a URL | `#1234`, the tracker title verbatim and the outro line |
| Rail | bottom, plain text | top-right pill |
| Music | optional | the brand's approved bed, once one is recorded in the profile |

Both templates read their colours, fonts and assets from the [brand profile](branding.md). Pick
`captionPos` after looking at the frame so captions never cover the action, and check every zoom against the
source frame so no header or signed-in name leaks.

## Composition contract

- Timed elements carry a start and a duration; the root carries the film length.
- One paused timeline per composition, registered where the renderer can seek it.
- No wall-clock time, unseeded random, network, timers or infinite repeats. Use explicit from-to tweens.
- Never tween `display` or `visibility` on a timed element; animate a child.
- Encode `<video>` clips with short keyframe intervals (about one second). Frame-by-frame seeking in
  browser renderers can show stale frames otherwise; check the render.
- Check that bundled fonts cover every glyph you use (arrows, ticks, ≥ and ≤).
- Format: 1920×1080, 30 fps, H.264 yuv420p with faststart, AAC. Set a size target from the destination;
  a 20–30 s done video of mostly static UI usually fits in about 10 MB at a quality-based setting.
