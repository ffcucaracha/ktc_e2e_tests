#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

unset SELENIUM_REMOTE_URL

export E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:5173}"
export DEMO_PACE="${DEMO_PACE:-1.0}"
export DEMO_AI_WARNING_WAIT_SECONDS="${DEMO_AI_WARNING_WAIT_SECONDS:-35}"
export DEMO_RESULT_WAIT_SECONDS="${DEMO_RESULT_WAIT_SECONDS:-420}"

VIDEO_DIR="${VIDEO_DIR:-$ROOT_DIR/artifacts/video}"
mkdir -p "$VIDEO_DIR"
VIDEO_FILE="${VIDEO_FILE:-$VIDEO_DIR/championship-demo-$(date +%Y%m%d-%H%M%S).mkv}"
VIDEO_FPS="${VIDEO_FPS:-25}"
VIDEO_CRF="${VIDEO_CRF:-26}"
VIDEO_MAX_WIDTH="${VIDEO_MAX_WIDTH:-1920}"
VIDEO_RECORDER="${VIDEO_RECORDER:-auto}"
VIDEO_RECORDER_PID=""
VIDEO_RECORDER_LOG=""

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

check_python_dependencies() {
  "$PYTHON" - <<'PY'
import importlib.util
import sys

required = ("pytest", "selenium", "urllib3")
missing = [name for name in required if importlib.util.find_spec(name) is None]

print(sys.executable)
if missing:
    print("Missing Python dependencies: " + ", ".join(missing), file=sys.stderr)
    sys.exit(2)
PY
}

stop_recorder() {
  if [[ -n "$VIDEO_RECORDER_PID" ]] && kill -0 "$VIDEO_RECORDER_PID" 2>/dev/null; then
    echo
    echo "Stopping screen recorder..."
    kill -INT "$VIDEO_RECORDER_PID" 2>/dev/null || true
    for _ in {1..50}; do
      if ! kill -0 "$VIDEO_RECORDER_PID" 2>/dev/null; then
        break
      fi
      sleep 0.1
    done
    if kill -0 "$VIDEO_RECORDER_PID" 2>/dev/null; then
      kill -TERM "$VIDEO_RECORDER_PID" 2>/dev/null || true
    fi
    wait "$VIDEO_RECORDER_PID" 2>/dev/null || true
  fi
}
trap stop_recorder EXIT INT TERM

start_recorder() {
  if [[ -n "${VIDEO_RECORDER_COMMAND:-}" ]]; then
    echo "Recorder: custom VIDEO_RECORDER_COMMAND"
    local command="${VIDEO_RECORDER_COMMAND//\{output\}/$VIDEO_FILE}"
    bash -lc "$command" &
    VIDEO_RECORDER_PID=$!
    sleep 1
    if ! kill -0 "$VIDEO_RECORDER_PID" 2>/dev/null; then
      wait "$VIDEO_RECORDER_PID" 2>/dev/null || true
      VIDEO_RECORDER_PID=""
      echo "Custom screen recorder exited before the demo started." >&2
      exit 2
    fi
    return
  fi

  local session_type="${XDG_SESSION_TYPE:-}"

  if [[ "$VIDEO_RECORDER" == "ffmpeg" || ( "$VIDEO_RECORDER" == "auto" && "$session_type" != "wayland" ) ]]; then
    if ! command -v ffmpeg >/dev/null 2>&1; then
      echo "ffmpeg is required for automatic X11 recording." >&2
      echo "Install it with: sudo apt install ffmpeg" >&2
      exit 2
    fi
    if [[ -z "${DISPLAY:-}" ]]; then
      echo "DISPLAY is not set; cannot record an X11 desktop." >&2
      exit 2
    fi

    local screen_size="${VIDEO_SCREEN_SIZE:-}"
    if [[ -z "$screen_size" ]] && command -v xdpyinfo >/dev/null 2>&1; then
      echo "Detecting X11 screen size..."
      if command -v timeout >/dev/null 2>&1; then
        screen_size="$(timeout 3s xdpyinfo 2>"$VIDEO_DIR/xdpyinfo.log" | awk '/dimensions:/{print $2; exit}' || true)"
      else
        screen_size="$(xdpyinfo 2>"$VIDEO_DIR/xdpyinfo.log" | awk '/dimensions:/{print $2; exit}' || true)"
      fi
      if [[ -z "$screen_size" ]]; then
        echo "Could not detect X11 screen size; using 1920x1080." >&2
        echo "xdpyinfo log: $VIDEO_DIR/xdpyinfo.log" >&2
      fi
    fi
    screen_size="${screen_size:-1920x1080}"

    echo "Recorder: ffmpeg/x11grab (${screen_size}, ${VIDEO_FPS} fps, CRF ${VIDEO_CRF}, max width ${VIDEO_MAX_WIDTH})"
    VIDEO_RECORDER_LOG="$VIDEO_DIR/ffmpeg.log"
    ffmpeg -y \
      -f x11grab \
      -framerate "$VIDEO_FPS" \
      -video_size "$screen_size" \
      -i "${DISPLAY}.0" \
      -vf "scale='min(${VIDEO_MAX_WIDTH},iw)':-2" \
      -c:v libx264 \
      -preset veryfast \
      -crf "$VIDEO_CRF" \
      -pix_fmt yuv420p \
      "$VIDEO_FILE" \
      >"$VIDEO_RECORDER_LOG" 2>&1 &
    VIDEO_RECORDER_PID=$!
    sleep 1
    if ! kill -0 "$VIDEO_RECORDER_PID" 2>/dev/null; then
      wait "$VIDEO_RECORDER_PID" 2>/dev/null || true
      VIDEO_RECORDER_PID=""
      echo "ffmpeg screen recorder exited before the demo started." >&2
      echo "Log: $VIDEO_RECORDER_LOG" >&2
      tail -80 "$VIDEO_RECORDER_LOG" >&2 || true
      exit 2
    fi
    return
  fi

  if [[ "$VIDEO_RECORDER" == "wf-recorder" || "$VIDEO_RECORDER" == "auto" ]]; then
    if command -v wf-recorder >/dev/null 2>&1; then
      echo "Recorder: wf-recorder (${VIDEO_FPS} fps)"
      VIDEO_RECORDER_LOG="$VIDEO_DIR/wf-recorder.log"
      wf-recorder -f "$VIDEO_FILE" -r "$VIDEO_FPS" \
        >"$VIDEO_RECORDER_LOG" 2>&1 &
      VIDEO_RECORDER_PID=$!
      sleep 1
      if ! kill -0 "$VIDEO_RECORDER_PID" 2>/dev/null; then
        wait "$VIDEO_RECORDER_PID" 2>/dev/null || true
        VIDEO_RECORDER_PID=""
        echo "wf-recorder could not start on this Wayland compositor." >&2
        echo "Log: $VIDEO_RECORDER_LOG" >&2
        tail -80 "$VIDEO_RECORDER_LOG" >&2 || true
        echo "On KDE Wayland, either log in to an X11 session for fully automatic recording" >&2
        echo "or set VIDEO_RECORDER_COMMAND to your preferred recorder command." >&2
        exit 2
      fi
      return
    fi
  fi

  echo "No automatic screen recorder is available for this session." >&2
  echo "X11: install ffmpeg (sudo apt install ffmpeg)." >&2
  echo "Wayland: install/use a compatible recorder or provide VIDEO_RECORDER_COMMAND." >&2
  exit 2
}

echo "Championship video demo"
echo "  app:             $E2E_BASE_URL"
echo "  pace:            $DEMO_PACE"
echo "  ML warning wait: ${DEMO_AI_WARNING_WAIT_SECONDS}s"
echo "  result/LLM wait: ${DEMO_RESULT_WAIT_SECONDS}s"
echo "  video fps:       $VIDEO_FPS"
echo "  video CRF:       $VIDEO_CRF"
echo "  video max width: $VIDEO_MAX_WIDTH"
echo "  session type:    ${XDG_SESSION_TYPE:-unknown}"
echo "  output:           $VIDEO_FILE"
printf "  python:           "
if ! check_python_dependencies; then
  echo
  echo "Install e2e dependencies with:" >&2
  echo "  cd $ROOT_DIR" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  .venv/bin/python -m pip install -r requirements.txt" >&2
  echo
  echo "Or run the demo with an existing prepared interpreter:" >&2
  echo "  PYTHON=/path/to/venv/bin/python $0" >&2
  exit 2
fi
echo

start_recorder
sleep 2

echo "Screen recording started. Selenium demo begins in 3 seconds..."
sleep 3

set +e
"$PYTHON" -m pytest -s -q -m video_demo tests/test_video_demo.py
TEST_STATUS=$?
set -e

stop_recorder
VIDEO_RECORDER_PID=""
trap - EXIT INT TERM

echo
if [[ -s "$VIDEO_FILE" ]]; then
  echo "Video saved: $VIDEO_FILE"
else
  echo "Warning: video file was not created or is empty: $VIDEO_FILE" >&2
fi

exit "$TEST_STATUS"
