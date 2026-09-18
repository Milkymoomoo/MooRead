#!/usr/bin/env bash
# MooRead Linux launcher — works under Xorg and Wayland (Tk uses X11 / XWayland).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT:${PYTHONPATH:-}"

if [[ -n "${WAYLAND_DISPLAY:-}" && -z "${DISPLAY:-}" ]]; then
  # Tk speaks X11. On pure Wayland start XWayland if needed.
  export DISPLAY=":0"
fi
export GDK_BACKEND="${GDK_BACKEND:-x11}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

PY="${ROOT}/python/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi
if [[ -z "$PY" ]]; then
  echo "python3 is required (python3-tk python3-pip python3-venv)"
  exit 1
fi

exec "$PY" "$ROOT/run.py" "$@"
