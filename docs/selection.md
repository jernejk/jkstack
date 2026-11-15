# Selection and sharing notes

Four skills are included, the two required ones and two optional additions, plus one blueprint. Every included skill and blueprint is a modified copy adapted for general sharing, not the original working skill; the adaptations are listed below. Blueprints live in `blueprints/`: they keep the method of a larger workflow whose tooling is not bundled, and setup does not install them.

| Included | Why it earns a place | Size in bytes |
| --- | --- | ---: |
| live-timeline | A feed-driven story with causal arcs, owner asks, snapshots, and quiet-gap compression. | 127169 |
| deep-yt-analysis | Combines caption curation, visually checked frames, claim research, and an inspectable verdict. | 21238 |
| design-hill-climb | Uses references, fresh reviewers, hidden score targets, and bounded iteration. | 5758 |
| dep-investigate | Separates declared, resolved, provenance, API, and runtime evidence. | 7865 |
| demo-video (blueprint) | Evidence-first short films: claim tables, on-screen evidence labels, phone-readable pacing, and staged review. | 37749 |

All optional additions are below 60 KB. The required timeline is the exception: its self-contained HTML page alone is about 73 KB. It has no external JavaScript or CSS dependency.

## Inspection scope

Both source skill directories were inventoried. Each included skill's entrypoint and bundled helpers, templates, and references were read. The shorter dependency skill in the second directory was also compared. The complete four-file video skill was reviewed. For the demo-video blueprint, the source skill's entrypoint and all ten references were read, and the headers and interfaces of its recorder, frame capture, composer, marker derivation, checker, review-sheet and OCR scripts were inspected. Its reference films were not available on this machine and were not used. The supplied newer timeline page and both schema versions were inspected; the clean-room reference README and demo entrypoint, adapter, and feed were consulted. Its screenshots and demo were not copied. No image from those directories is used in the README, so no source screenshot is represented as privacy-cleared.

The following alternatives were screened through their entrypoints and inventory. Selected supporting files were inspected where needed to establish a concrete dependency or risk; these are deferrals, not complete code or privacy audits of the excluded trees.

| Deferred | Reason |
| --- | --- |
| skill-evals | The runner depends on an unbundled usage guard and sibling skills. Its guard returns zero on errors; Codex support is only an adapter seam. Repairing and proving a portable runner deserves a separate task. Its paired-baseline approach also overlaps a public skill-creator workflow. |
| ai-spike | A large toolkit with local account metering, overlays, model-call helpers, judge assets, and report tooling. It exceeds this pack's size and small-edit scope. |
| research-lane | Depends on the experiment toolkit, archive conventions, and model review routing; larger than the small-skill target. |
| gh-ci-watcher | Closely overlaps ordinary CI watchers and public packs. It also depends on external notification helpers and can report completion while another target has a read error. |
| disk-investigate | The history report assumes a particular Grafana/Influx setup, datasource, and storage-path inventory. The APFS helper is interesting but separating it would be a new extraction project. |
| demo-recorder tooling | The recorder, composer, checkers, brand art, and music stay private: they carry third-party brand assets, a private reference-film library, and machine-specific paths, and have not been run outside one setup. The written method ships as the demo-video blueprint; the tools are described there as extensions. |
| macos-startup-items | Kept in the owner's personal collection; it is personal Mac tooling rather than agent-work tooling. |
| orchestration-mode | Relies on personal model routing and harness assumptions. General orchestration also overlaps common public guidance. |
| Remaining inventory | Workflows tied to one organization, personal-life data, account integrations, specialized local infrastructure, thin wrappers, and common public skills were outside the selection filters. No claim of a full audit is made for them. |

## Video skill verdict

Include the edited copy. The original automatically downloads a video, subtitles, and thumbnail with `yt-dlp`, including an extractor-client override for thumbnails. These operations can conflict with a site's terms or trigger access/rate controls. A public URL does not establish authorization. Current [YouTube terms](https://www.youtube.com/static?template=terms) restrict downloading and automated access except in permitted circumstances; the workflow must check the applicable permission and access route.

The original four files contain no browser-cookie import, logged-in browser requirement, paid transcription API, or embedded API key. The downloader can inherit user configuration, however, and the original model pipeline has a substantial token cost without a portable hard cap. It also embeds personal storage, usage-monitor, model-routing, and owner-fit assumptions.

The copy defaults to supplied local material and supports transcript-only analysis. Network acquisition is opt-in per video after a terms and permission check. Optional downloader use must ignore inherited config, avoid playlists, and stop on denial or throttling. Cookie import, logged-in sessions, client spoofing, proxy rotation, and bypasses are forbidden. No automated download command is bundled. This lowers risk; it does not certify that any particular acquisition is allowed.

New metered spend defaults to zero. Delegation needs an explicit request. Authorized paid runs need an enforceable ceiling; otherwise unattended execution stops before dispatch. Private media needs explicit authorization before any external vision processing. Reports retain only necessary excerpts and do not grant redistribution rights.

## Adaptations

| Area | Changes |
| --- | --- |
| All copies | Removed owner names in instructions, private absolute paths, machine references, organization-specific examples, infrastructure URLs, personal model seats, and cross-skill assumptions where they affected portability. Helper locations are resolved from the installed skill. Original files were not edited. |
| Timeline instructions | Replaced portal routes with a loopback preview, separated reviewed served output from config/logs, made the keeper optional and harness-generic, bounded its lifetime and cost, and documented browser-local caching and the one-writer requirement. |
| Timeline page | Used the supplied newer page with image snapshots and quiet-gap compression. No run feed is embedded. Removed the personal legacy event-kind alias. Added a local-only image path gate, removed images from sealed events during normalization, and made image-only cards advertise their detail popup. Other rendering behavior is retained. |
| Timeline helpers/schema | Generic owner default and examples, configurable optional T3 Code database path, generic example domain, and documented `images.path`, `caption`, and `full`. The validator rejects unsafe image paths and image-bearing sealed events. Existing patch/install mechanics remain atomic. |
| Video analysis | Removed forced model routing and local usage scripts, automatic acquisition/install/open behavior, default delegation, extractor-client override, private project-fit examples, and personal report labels. Made frame count bounded. Selected the multi-line caption converter; kept the older converter with its known loss warning. |
| Design loop | Removed run provenance, fixed provider/model choices, and automatic PR delivery. Added explicit delegation authority, enforceable paid-run limits, pending-review honesty, and a documented single-agent fallback. Removed a Claude-only frontmatter field rejected by the Codex validator. |
| Dependency investigation | Workspace-local sparse-source directory, official versioned evidence first, explicit read-only scope, optional native delegation, unique temporary graph output, a prerequisite check, and no implicit restore. Fixed the .NET 10 command to use `--project`; preserved stderr diagnostics. |
| Demo video | Rewritten as a blueprint from the source skill's method. Added sprint-demo, research, walkthrough, and repro modes and a generic "Previously on" mode. Replaced third-party brand rules, mascots, and the default music bed with brand profiles, plus personal and fictional Contoso templates that contain no real logos. Removed personal viewing notes, named model routing, private reference films, machine paths, and app-specific capture notes. Delivery destinations became suggestions that each need authority. Tools and journey films are described as extensions, not bundled. |
| Packaging | Added a preflighted symlink setup, MIT license, ignore rules, requirements, privacy notes, and local regression checks. Setup does not edit harness configuration or run skills. |

## Inspiration and remaining decisions

[gstack](https://github.com/garrytan/gstack) was inspected for its README, skill table, setup entrypoint, and repository layout. [tstack by Theo Browne](https://github.com/t3dotgg/tstack) is the likely spoken second reference: it is an everyday Claude Code/Codex skill pack. This identification is an inference. Neither repository's prose or implementation was copied.

The name is jkstack, under the MIT license.
