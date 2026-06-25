#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_DIR="$ROOT_DIR/custom_components/trading212"
TMP_PYCACHE="$(mktemp -d)"

cleanup_pycache() {
  rm -rf "$TMP_PYCACHE"
  find "$PACKAGE_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} +
}

trap cleanup_pycache EXIT
cd "$ROOT_DIR"

printf 'Python compile\n'
PYTHONPYCACHEPREFIX="$TMP_PYCACHE" python3 -m compileall -q custom_components/trading212

printf '\nGit diff check\n'
git diff --check
