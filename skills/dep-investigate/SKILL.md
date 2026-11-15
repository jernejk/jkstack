---
name: dep-investigate
description: Investigate package versions, provenance, or APIs from the resolved graph and exact source without dumping package caches. Use for dependency/SDK archaeology such as "which version won?", "why is this package here?", or "does this member exist?"
metadata:
  updated: "2026-07-28"
  version: 1.1.0
  category: investigation
---

# dep-investigate

Resolve helper paths relative to this installed skill folder in Claude Code or Codex. Use your ecosystem tools; do not install tools automatically.

Rule: a dependency is a **resolved graph + exact-version source**, never a
directory to grep. Grepping a package cache burns context without adding answer;
the graph-first path is cheaper and more precise.

## 1. Classify the question — cover ONE stage, then stop

| Stage | Question | Cheapest source |
|---|---|---|
| **declared** | What did we ask for? | manifest: `*.csproj`, `Directory.Packages.props`, `package.json`, `Cargo.toml` |
| **resolved** | What version/assets won? | lockfile/graph: `project.assets.json`, `package-lock.json`, `Cargo.lock` |
| **provenance** | Why is package X here? | `dotnet nuget why` / `npm explain` / `cargo tree -i` |
| **api-surface** | Does type/member X exist? Its shape? | official per-version API docs, exact-version `.xml`, or a pinned source clone |
| **runtime** | What actually ships / runs? | published `.deps.json` + a tiny harness |

Return the §5 coverage table. An api-surface review is NOT implementation
coverage — never present them as equal.

## 2. Recipe per ecosystem (in order; stop when answered)

**.NET / NuGet** — always scope by project AND framework:
```bash
dotnet package list --project src/App/App.csproj --framework net10.0 \
  --include-transitive --format json --no-restore > ./packages.json
jq '.projects[].frameworks[] | (.topLevelPackages[]?, .transitivePackages[]?)
    | {id,resolvedVersion}' ./packages.json
dotnet nuget why src/App/App.csproj Azure.AI.OpenAI --framework net10.0   # provenance
```
`project.assets.json` (from restore) is the resolved graph — use it over the cache.

**npm** → `npm ls --json <pkg>` · `npm explain <pkg>` · `package-lock.json`.
**pip** → `pip show <pkg>` · `pipdeptree -p <pkg>`.
**cargo** → `cargo tree -i <pkg>` · `Cargo.lock`.

**api-surface:** start with official per-version documentation or exact-version source. For NuGet, a per-version API browser may help locate symbols; confirm important claims against the package or upstream source. For .NET, decompile one member
with `ilspycmd -t Namespace.Type path/to.dll` if you need the body. Never open a
package folder wholesale.

**runtime:** read published `.deps.json`; confirm behaviour (e.g. token scope /
MI 401) with a minimal harness, not doc name-matching.

## 3. Real SDK source (auth, pipeline, client internals)

Only when metadata can't answer. Clone **exact-version, shallow, sparse** — never
`main`, never the whole monorepo:
```bash
mkdir -p ./dependency-sources
cd ./dependency-sources                                    # workspace-local clone parking spot
git ls-remote --tags https://github.com/openai/openai-dotnet | grep 2.11   # confirm tag format first
git clone --depth 1 --branch OpenAI_2.11.0 --filter=blob:none --sparse \
  https://github.com/openai/openai-dotnet openai-dotnet-2.11.0   # versioned dir
git -C openai-dotnet-2.11.0 sparse-checkout set src/Custom/Chat  # only the area that matters
```
Tag must match the **resolved** version. Prefer a single-package repo over a
monorepo; skip repos the evidence doesn't require.

## 4. Hard rules — token-burn guards

A long turn re-sends all prior tool output as input on every later step, so a big
or early dump is paid again on every step that follows. So:

- Never recursively search a package cache/store (`~/.nuget/packages`,
  `node_modules`, `~/.cargo/registry`, `site-packages`) or dump whole XML/README.
  On generated doc XML, match ONE symbol with no `-C` window, then `| head`.
- Read each file once; keep a digest. Re-reading a file — or a `for f in …; do
  sed` multi-file dump — re-sends every byte on every later step.
- After a sparse clone, search only inside the checked-out sparse paths.
- One question per command; exact version paths; JSON + `jq`. Cap output: `| head -c 8000`.
- Set an action/input budget before you start; when you hit it, stop and report
  partial coverage. Stop the moment the question has evidence — no adjacent
  packages "for completeness".

## 5. Coverage table (return this)

```
| stage        | covered | evidence (path:line or command)        | actions |
|--------------|---------|----------------------------------------|---------|
| resolved     | yes     | project.assets.json                    | 1       |
| api-surface  | yes     | openai-dotnet-2.11.0/.../ChatClient.cs | 6       |
```

## 6. If code changes are authorized

An investigation is read-only. Do not edit application code or restore packages unless the request authorizes it. For an authorized implementation, restore once then `--no-restore`; build/test the affected project before
solution-wide commands; phase `inspect → plan → edit → build → test →
runtime-proof`, summarize each. Mark this as implementation coverage, not review.

## Optional delegation

Only delegate when the owner requests it, using the harness's supported task facility. Inline §1–§4 and the budget into the child's prompt, keep it read-only (`observe`)
unless it must edit, require the §5 table back, point it at durable files
(`pkgs.json`, clone paths). Deterministic starter:
`scripts/dep-snapshot.sh <csproj> <framework>` runs declared+resolved+provenance
so the child begins at api-surface.
