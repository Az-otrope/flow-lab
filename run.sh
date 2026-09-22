#!/usr/bin/env bash
# Start Flow Lab. Creates the venv on first run.
set -euo pipefail
cd "$(dirname "$0")"

# A venv bakes its own absolute path into the shebang of every console script,
# so moving or renaming this folder leaves those scripts in place but pointing
# at an interpreter that no longer exists. Note that .venv/bin/python survives
# a rename -- it re-derives its prefix -- so checking that would miss the case.
# Check the interpreter the script itself names.
venv_ok() {
  [ -x .venv/bin/streamlit ] || return 1
  local interp
  interp=$(head -1 .venv/bin/streamlit | sed 's|^#!||' | awk '{print $1}')
  [ -x "$interp" ] || return 1
  .venv/bin/python -c "import streamlit" >/dev/null 2>&1
}

if ! venv_ok; then
  if [ -d .venv ]; then
    echo "venv is stale (moved or renamed folder?) — rebuilding it"
    rm -rf .venv
  fi
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi

exec .venv/bin/streamlit run app.py
