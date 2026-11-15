# Branding

A film can carry personal branding or a company's branding. The method is the same;
only the brand profile changes. Keep one profile per brand and pick it in `BRIEF.md`.

## Brand profile

A small JSON file the composer reads. Two starting points ship with this skill:

- [brand-personal.json](../assets/brand-personal.json): an individual developer's channel or portfolio.
- [brand-contoso.json](../assets/brand-contoso.json): a company brand, using the fictional Contoso.

Template asset paths such as `brand/contoso-logo.svg` are placeholders. Before rendering, check that every
logo, character and music path exists and that each licence and credit field holds a real value.

| Field | Meaning |
|---|---|
| `name` | Shown on intro and end cards |
| `logo` | Path to the approved logo file, or `null` for a text mark |
| `colors` | `stage` (background), `surface` (UI window), `ink` (text), `accent`, `caption`, `rail` |
| `fonts` | Family names with their licence; the renderer must have them installed or bundled |
| `characters` | Optional approved mascot art: `{ id, file, accent, role }` |
| `cards` | `intro` and `end` card layouts; the end card's `reference` pattern, such as `#{number}` or `PR {number}` |
| `rail` | Evidence-rail position and style |
| `music` | Default track path, its licence and its credit line, or `null` |

## Rules

- **Use the real kit.** Logos, colours, fonts and characters come from the brand's own approved assets.
  Never redraw, recolour, crop or approximate them. If an essential asset is missing, ask for it; omit
  optional decoration.
- **Company brands need permission.** Confirm the film may use the brand and where it may be shown.
  One company's material stays in that company's films, and brands never mix in one film.
- **Characters stay on cards.** Mascots belong on intro and end cards or clear margins, never over proof,
  captions or the evidence rail. Give them actions, not idle bobbing.
- **Brand does not change evidence rules.** A branded concept film is still labelled a concept.
- **Fonts and music need licences too.** Record them in the profile, not from memory.
- **Keep private brand assets out of shared repositories.** Store each profile and its assets with the
  project that owns them. The templates here contain no real logos.
