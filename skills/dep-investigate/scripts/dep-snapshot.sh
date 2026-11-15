#!/usr/bin/env bash
# dep-snapshot — zero-token declared+resolved+provenance digest for a .NET project.
# Runs the deterministic dependency-graph queries so an agent starts at the
# api-surface stage with the graph already in hand (0 model tokens spent getting here).
#
# Usage: dep-snapshot.sh <project.csproj> <framework> [pkg-for-provenance ...]
#   dep-snapshot.sh src/App/App.csproj net10.0
#   dep-snapshot.sh src/App/App.csproj net10.0 Azure.AI.OpenAI Azure.Identity
#
# Writes full JSON to a unique temporary directory and prints a compact summary.
set -euo pipefail

proj=${1:?usage: dep-snapshot.sh <project.csproj> <framework> [pkg ...]}
fw=${2:?usage: dep-snapshot.sh <project.csproj> <framework> [pkg ...]}
shift 2 || true

[ -f "$proj" ] || { echo "ERROR: project not found: $proj" >&2; exit 2; }
command -v dotnet >/dev/null || { echo "ERROR: dotnet not on PATH" >&2; exit 3; }

command -v jq >/dev/null || { echo "ERROR: jq not on PATH" >&2; exit 3; }
out_dir=$(mktemp -d "${TMPDIR:-/tmp}/dep-snapshot.XXXXXXXX")
out="$out_dir/packages.json"

echo "## dep-snapshot: $proj ($fw)"
echo

# --- declared + resolved (top-level + transitive) ---
if ! dotnet package list --project "$proj" --framework "$fw" --include-transitive \
      --format json --no-restore >"$out"; then
  echo "ERROR: 'dotnet package list' failed — run 'dotnet restore $proj' first." >&2
  exit 4
fi

echo "### Top-level packages"
jq -r '.projects[].frameworks[].topLevelPackages[]?
       | "  \(.id)  requested=\(.requestedVersion)  resolved=\(.resolvedVersion)"' "$out" \
  | sort -u | head -c 8000
echo

echo "### Transitive packages (resolved)"
jq -r '.projects[].frameworks[].transitivePackages[]? | "  \(.id)  \(.resolvedVersion)"' "$out" \
  | sort -u | head -c 8000
echo

# --- provenance for any packages named on the command line ---
for pkg in "$@"; do
  echo "### why: $pkg"
  dotnet nuget why "$proj" "$pkg" --framework "$fw" 2>/dev/null | head -c 4000 || echo "  (no path found)"
  echo
done

echo "Full graph JSON: $out"
echo "Next: inspect exact-version API surface (official docs or a pinned sparse clone) only for the package in question."
