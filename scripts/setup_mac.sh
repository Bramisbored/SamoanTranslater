#!/bin/bash
# One-time setup on the Mac mini (Apple Silicon). Run from anywhere:
#   bash scripts/setup_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="$(pwd)"

if ! command -v brew >/dev/null; then
  echo "Homebrew is needed first: https://brew.sh" >&2
  exit 1
fi

echo "==> Installing ffmpeg, cloudflared and Python 3.12 (skips anything already installed)"
brew install ffmpeg cloudflared python@3.12

PY="$(brew --prefix python@3.12)/bin/python3.12"
echo "==> Creating virtual environment in $DIR/.venv"
"$PY" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r server/requirements.txt

echo "==> Downloading the models and testing each step (first time: ~4 GB, several minutes)"
.venv/bin/python scripts/check_models.py

echo
echo "Setup done. Next: bash scripts/run.sh   then open http://localhost:8000"
