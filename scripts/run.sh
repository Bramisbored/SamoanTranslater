#!/bin/bash
# Run the server in the foreground (Ctrl+C to stop). Open http://localhost:8000
cd "$(dirname "$0")/../server"
export PRELOAD_MODELS="${PRELOAD_MODELS:-1}"
export PATH="/opt/homebrew/bin:$PATH"
exec ../.venv/bin/uvicorn app:app --host 127.0.0.1 --port "${PORT:-8000}"
