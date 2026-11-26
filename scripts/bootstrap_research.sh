#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM="$ROOT/upstream/spektrafilm"
UPSTREAM_REPO="https://github.com/andreavolpato/spektrafilm.git"
UPSTREAM_SHA="3bb2c2d2801ff68b92019cf1dbcbb133d60832bc"
PYTHON_BIN="${PYTHON_BIN:-python3.13}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.13 is required; set PYTHON_BIN to its path." >&2
  exit 1
fi
if ! command -v git >/dev/null 2>&1; then
  echo "git is required." >&2
  exit 1
fi

if [[ ! -e "$UPSTREAM" ]]; then
  mkdir -p "$(dirname "$UPSTREAM")"
  git clone "$UPSTREAM_REPO" "$UPSTREAM"
  git -C "$UPSTREAM" checkout --detach "$UPSTREAM_SHA"
elif [[ ! -d "$UPSTREAM/.git" ]]; then
  echo "$UPSTREAM exists but is not a git checkout. Refusing to overwrite." >&2
  exit 1
fi

ACTUAL_SHA="$(git -C "$UPSTREAM" rev-parse HEAD)"
if [[ "$ACTUAL_SHA" != "$UPSTREAM_SHA" ]]; then
  echo "Expected upstream $UPSTREAM_SHA, found $ACTUAL_SHA. Refusing to alter it." >&2
  exit 1
fi
if [[ -n "$(git -C "$UPSTREAM" status --porcelain)" ]]; then
  echo "Upstream checkout has local changes; refusing to use it for this bootstrap." >&2
  exit 1
fi

if [[ ! -d "$ROOT/.venv" ]]; then
  "$PYTHON_BIN" -m venv "$ROOT/.venv"
fi

"$PYTHON_BIN" "$ROOT/scripts/fetch_kodak_references.py" --root "$ROOT"
"$ROOT/.venv/bin/python" -m pip install --requirement "$ROOT/requirements-research.txt"
"$ROOT/.venv/bin/python" -m pip install --no-deps --editable "$UPSTREAM"

echo "Research environment ready at $ROOT/.venv"
echo "Upstream pinned to $UPSTREAM_SHA"
echo "Official Kodak references downloaded locally and hash-verified (not redistributed)"
echo "To run the synthetic smoke gate:"
echo "  PYTHONPATH=src .venv/bin/python scripts/run_experiment.py --smoke-only"
