#!/usr/bin/env bash
# Fallback dependency install for environments without `uv`.
# Builds a venv in the resume-kit home directory and prints the python to use.
set -euo pipefail

KIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v uv >/dev/null 2>&1; then
  echo "uv is installed — no setup needed. Render with:"
  echo "  uv run $KIT_ROOT/scripts/render.py --tailored <json> --out-dir <dir>"
  exit 0
fi

HOME_DIR="$(python3 "$KIT_ROOT/scripts/kit.py" paths | python3 -c 'import json,sys; print(json.load(sys.stdin)["home"])')"
VENV="$HOME_DIR/.venv"

mkdir -p "$HOME_DIR"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet 'reportlab>=4.0' 'pypdfium2>=4.0'

echo "Done. Render with:"
echo "  $VENV/bin/python $KIT_ROOT/scripts/render.py --tailored <json> --out-dir <dir>"
