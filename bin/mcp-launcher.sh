#!/bin/bash
# Self-installing MCP server launcher for Claude Code.
# On first run, creates venv and installs dependencies automatically.
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

if [ ! -f "$VENV_DIR/bin/python3" ]; then
    echo "[video-extract2note] Creating virtual environment..." >&2
    python3 -m venv "$VENV_DIR"
fi

if [ ! -f "$VENV_DIR/.installed" ]; then
    echo "[video-extract2note] Installing dependencies..." >&2
    PIP_USER=false "$VENV_DIR/bin/pip" install --quiet --no-user -e "$PROJECT_DIR" 2>&1 | tail -3 >&2
    touch "$VENV_DIR/.installed"
fi

exec "$VENV_DIR/bin/python3" -m video_extract2note.mcp_server "$@"
