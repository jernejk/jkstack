# Verification

The local assembly was checked on macOS. Original skill files were hashed before copying and checked again after implementation. The supplied newer page was also hashed. All matched their original bytes.

## Commands and results

| Check | Result |
| --- | --- |
| `python3 tests/smoke.py` | Eight tests passed. All installs use temporary homes. |
| `python3 tests/timeline-browser.py` in a Python environment with Playwright and Chromium | Four configurations passed: 1440 and 390 pixels, light and dark. |
| `python3 tests/helper-integration.py` | Local NuGet package resolution/provenance and frame extraction from generated media passed. |
| Skill-creator frontmatter validator on every included skill | Five valid entrypoints: four skills and one blueprint. Descriptions are below 1024 characters. |
| `bash -n skills/dep-investigate/scripts/dep-snapshot.sh` | Passed. |
| Python syntax parsing of setup, helpers, and tests | Passed. |
| Git email check inside the repository | The configured identity was checked and is not copied into this report. |

The timeline checks initialize a temporary run, validate it, append a sample event with image metadata, resolve its reference, read it back, reject unsafe image paths without changing the installed feed, reject a sealed image, and preserve data on upgrade. Collection excludes private sources and avoids reprinting unchanged sources. Browser checks intercept requests locally, without a server or external network. They exercise image loading in cards and popups, quiet-gap compression, update drafts, malformed-feed recovery, horizontal overflow, and JavaScript errors.

Setup checks cover a no-write dry run, both harnesses, a single harness, idempotence, existing folders/files/broken links, and parent symlinks. A conflict in either harness prevents all new links.

The dependency integration test uses a generated package and an explicitly local-only NuGet source with audit disabled. Inspection then uses `--no-restore`. This checks the actual .NET 10 CLI rather than a mock. The video test generates a one-second clip and extracts a frame. It does not fetch any video.

The demo-video blueprint check resolves every relative link in the blueprint and parses both brand profile templates. A deliberately broken link made it fail. The blueprint bundles no renderer, so no film was rendered from it. One independent review of the blueprint by a different model family found no privacy issues; its seven findings on review bounds, fake-clock capture, spec fields, template placeholders, renderer wording, portrait readability and encoding claims were applied.

## Privacy gate

A task-specific grep outside this repository scans every worktree file, hidden files, JSON, and filenames. Binary files would be searched as text too. No screenshot, source media, or demo data is bundled. The patterns cover the requested private paths, infrastructure and organization markers, personal email domains, email-like strings, phone numbers, common API-key formats and assignments, and UUIDs.

```text
private markers: 0 content hit(s); 0 filename hit(s)
email: 0 content hit(s); 0 filename hit(s)
phone: 0 content hit(s); 0 filename hit(s)
API-key-like: 0 content hit(s); 0 filename hit(s)
UUID: 0 content hit(s); 0 filename hit(s)
private hits: 0
```

No harmless content match needed an exception. The broad initial search briefly matched a URL-parser variable followed by a property name; that variable was renamed so even the literal infrastructure-marker search is clear. Copyright attribution and public source links remain intentionally. Standard Git author metadata is checked separately and retains the authorized personal identity; it is not skill content. Compressed Git objects are represented by their decoded committed contents, not treated as a meaningful raw-text privacy check.

Commit messages are checked for AI or model attribution trailers; history has none, and a local commit hook strips them. The gate runs before each local commit. Commit history contains only the sanitized assembly. The scan is a heuristic, not a guarantee that arbitrary future data is safe to share.

## Not verified

- Independent model reviews, design score convergence, model cost reporting, and long-running keeper operation were not exercised. No paid calls were made.
- Real T3 Code database collection was not run. Its optional adapter targets particular projection layouts and may need updating for another version. File-log collection was tested.
- Network video acquisition, site access, copyrighted-media redistribution, and full AI video verdict quality were not tested or certified.
- Real-home installation and live Claude Code/Codex skill discovery were not run. Temporary-home filesystem installation was verified.
- No screenshot from the supplied reference collection was used or privacy-certified. The README is text only.
- Cross-platform execution beyond macOS, large dependency graphs, concurrent writers, and long-duration browser behavior were not tested.
- The demo-video blueprint has not been followed end to end by a fresh agent, and its described extensions are not bundled or tested here.
- Nothing was published or deployed.
