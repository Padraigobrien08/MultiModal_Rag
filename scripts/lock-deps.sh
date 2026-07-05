#!/usr/bin/env bash
# Regenerate constraints.txt: a fully-pinned snapshot of the runtime dependency
# tree used to make production Docker builds reproducible.
#
# The pins are resolved *inside* the same base image the Dockerfile uses
# (python:3.11-slim) so the versions match what production actually installs —
# resolving on a dev machine (e.g. macOS) can pick different platform wheels.
#
# Run this after changing runtime dependencies in pyproject.toml, or to pull in
# transitive security fixes. Requires Docker. Review the diff before committing.
#
#   ./scripts/lock-deps.sh   (or: make lock)
set -euo pipefail

cd "$(dirname "$0")/.."
out="constraints.txt"

echo "Resolving runtime dependencies in python:3.11-slim ..." >&2
body="$(
  docker run --rm \
    -v "$PWD/pyproject.toml":/build/pyproject.toml:ro \
    -v "$PWD/stepwise":/build/stepwise:ro \
    -v "$PWD/README.md":/build/README.md:ro \
    -v "$PWD/LICENSE":/build/LICENSE:ro \
    -w /build \
    python:3.11-slim \
    bash -c 'pip install --no-cache-dir . >/dev/null 2>&1 && pip freeze --exclude-editable' \
    | grep -viE '^stepwise[[:space:]@=]' \
    | LC_ALL=C sort -f
)"

{
  echo "# Fully-pinned runtime dependencies for reproducible production builds."
  echo "# GENERATED — do not edit by hand. Regenerate with: make lock"
  echo "# Resolved inside python:3.11-slim to match the production Docker image."
  echo "# Ranges live in pyproject.toml; this file pins the resolved transitive tree."
  echo "$body"
} > "$out"

echo "Wrote $out ($(grep -c '==' "$out") pinned packages)." >&2
