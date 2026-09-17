#!/usr/bin/env bash
# Start the Pomodoro clock. Creates the venv on first run.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/streamlit ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi

exec .venv/bin/streamlit run app.py
