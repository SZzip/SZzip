#!/usr/bin/env bash
# Install the bundled edoop CLI so the `edoop` command is available.
#
# Idempotent: if `edoop` already works, it does nothing. Otherwise it installs
# the copy bundled inside this skill (skill/cli). Prefers a repo-root checkout
# when this skill is used from within the SZzip repository.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
BUNDLED_CLI="$SKILL_DIR/cli"

if command -v edoop >/dev/null 2>&1; then
  echo "edoop bereits installiert: $(command -v edoop)"
  edoop --version || true
  exit 0
fi

# Pick a pip: prefer an active venv, fall back to --user.
PIP=(python3 -m pip install)
if [ -z "${VIRTUAL_ENV:-}" ]; then
  PIP+=(--user)
fi

# If we're inside the SZzip repo (root project present), install that; else the bundle.
REPO_ROOT=""
if git -C "$SKILL_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
  candidate="$(git -C "$SKILL_DIR" rev-parse --show-toplevel)"
  if [ -f "$candidate/pyproject.toml" ] && [ -d "$candidate/edoop" ]; then
    REPO_ROOT="$candidate"
  fi
fi

TARGET="${REPO_ROOT:-$BUNDLED_CLI}"
echo "Installiere edoop CLI aus: $TARGET"
"${PIP[@]}" "$TARGET"

echo
if command -v edoop >/dev/null 2>&1; then
  echo "OK: $(command -v edoop)"
  edoop --version
else
  echo "Hinweis: 'edoop' ist nicht im PATH. Nutze alternativ: python3 -m edoop --help"
  echo "(Bei --user-Installation ggf. ~/.local/bin zum PATH hinzufügen.)"
fi
