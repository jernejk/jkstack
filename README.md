# jkstack

jkstack is a small pack of agent skills for developers who want visible progress, evidence they can inspect, and bounded review loops. It works with Claude Code and Codex. The timeline also supports an optional T3 Code adapter. Keep the parts that fit your work.

These skills are modified versions of skills the author uses day to day, adapted for general sharing. Private paths, personal model routing, account integrations and machine-specific details were removed, and risky defaults such as downloads, delegation and paid calls were made opt-in. They behave differently from the originals; [selection notes](docs/selection.md) list what changed.

| Skill | What it does |
| --- | --- |
| [live-timeline](skills/live-timeline/SKILL.md) | Follow long tasks through chapters, causal arcs, blockers, image snapshots, and a ribbon that folds quiet gaps. |
| [deep-yt-analysis](skills/deep-yt-analysis/SKILL.md) | Study supplied video and captions, check frames and claims, and write a sourced HTML verdict. |
| [design-hill-climb](skills/design-hill-climb/SKILL.md) | Improve a real interface with blind reference comparisons and a fixed review budget. |
| [dep-investigate](skills/dep-investigate/SKILL.md) | Trace a dependency through its resolved graph and exact-version source. |

## Blueprints

Blueprints describe larger workflows whose tooling is too specific to bundle. Each one gives the method, formats and review steps, and describes the tools worth building. Setup does not install them: read one and adapt it, or link its folder into your skills directory yourself.

| Blueprint | What it covers |
| --- | --- |
| [demo-video](blueprints/demo-video/SKILL.md) | Evidence-first done videos, sprint demos, "Previously on" recaps, research, release, walkthrough and repro films. No renderer is bundled. |
| [babysit-pr](blueprints/babysit-pr/SKILL.md) | Watch a PR to ready: bot-comment triage, CI fixes, conflict and stale-approval rules, and the contract for a watcher that spends no model tokens while it waits. No watcher is bundled. |

## Install

Keep this checkout where it will stay. Setup creates links into it. It does not download tools, edit harness settings, or run any skill.

```sh
# Inspect first. A dry run writes nothing.
./setup --both --dry-run

# Claude Code: ~/.claude/skills
./setup --claude

# Codex: ~/.agents/skills
./setup --codex

# Or install for both harnesses.
./setup --both
```

Existing folders, files, and unrelated symlinks are refused before any links are created. Links already pointing here are left alone. Move an existing installation yourself before retrying. To uninstall, remove only the symlinks setup created. Removing the checkout breaks those links.

Use a skill by name, such as `/live-timeline` in Claude Code or `$live-timeline` in Codex, or describe the task. Resolve helper paths relative to the installed skill folder.

## Requirements

- Python 3.10 or later for setup and Python helpers.
- Claude Code or Codex for agent workflows. Model access is supplied by your harness.
- A modern browser and HTTP hosting for the timeline. Its helpers use the Python standard library. T3 Code database collection is optional and version dependent.
- FFmpeg for local video frames. `yt-dlp` is optional and requires explicit download authorization. No browser cookies or paid transcription API are used.
- Your ecosystem tools for dependency inspection; the .NET helper needs .NET SDK 10+ and `jq`.
- For demo videos: browser automation, FFmpeg and an HTML-to-video renderer of your choice, plus licensed music.
- For PR babysitting: the GitHub CLI, authenticated for the repository, and a harness that can wake on a background command.
- Browser capture and independent model reviewers for design review. Set a round limit and spend ceiling first. A single-agent run reports that it lacks independent review.

## Privacy

Skills run with your agent's permissions. Keep private logs, media, keys, and denied terms outside any served folder. The timeline stores a last good feed in browser local storage; clear site data after sensitive runs. Deny lists help catch mistakes but do not make an unsafe folder safe to publish. Downloaded media and generated reports are not automatically licensed for redistribution.

See [selection and sharing notes](docs/selection.md) and [verification](docs/verification.md). MIT licensed; copyright 2026 Jernej Kavka. The working name is jkstack.
