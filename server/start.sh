#!/bin/sh
# Start the AD scan server (macOS / Linux).
# Uses the faster-whisper venv if it can find one, otherwise falls back to
# the system python3 (which must then have faster-whisper installed).
# Set WHISP_VENV to point at your venv explicitly, e.g.:
#   WHISP_VENV="$HOME/.venvs/whisp" ./start.sh
# Provider keys (optional — only needed for drafted lines):
#   export ANTHROPIC_API_KEY=...   # for provider=claude
#   export OPENAI_API_KEY=...      # for provider=openai

cd "$(dirname "$0")"

# Prefer the venv that lives next to the server (self-contained: the server
# directory travels as one unit). Fall back to the shared venvs, then system.
if [ -x "$PWD/.venv/bin/python" ]; then
    VENV_PY="$PWD/.venv/bin/python"
elif [ -n "$WHISP_VENV" ]; then
    VENV_PY="$WHISP_VENV/bin/python"
elif [ -x "$HOME/workspace/.venvs/whisp/bin/python" ]; then
    VENV_PY="$HOME/workspace/.venvs/whisp/bin/python"
elif [ -x "$HOME/.venvs/whisp/bin/python" ]; then
    VENV_PY="$HOME/.venvs/whisp/bin/python"
else
    VENV_PY="python3"
fi

# Whisper model cache (base model, ~150 MB, downloaded on first use).
export HF_HOME="${HF_HOME:-$HOME/workspace/.venvs/hf}"
export PYTHONUNBUFFERED=1

echo "Starting AD scan server with: $VENV_PY"
exec "$VENV_PY" server.py
