#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x .venv/bin/python ]]; then
  echo "Python environment not found. Run: python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt" >&2
  exit 1
fi
if ! .venv/bin/python -c 'import fastapi, uvicorn, httpx, docx, reportlab, pypdf, multipart' 2>/dev/null; then
  echo "Python dependencies are missing. Run: .venv/bin/pip install -r backend/requirements.txt" >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1 || [[ ! -x node_modules/.bin/vite ]]; then
  echo "Node.js or frontend dependencies are missing. Install Node.js and run: npm install" >&2
  exit 1
fi
if ! curl -fsS --max-time 5 "${OLLAMA_URL:-http://127.0.0.1:11434}/api/tags" >/dev/null; then
  echo "Cannot connect to Ollama. Start Ollama and try again." >&2
  exit 1
fi
if ! .venv/bin/python -c '
import socket
import sys
for port in (8000, 5173):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            print(f"Cannot use port {port}: {exc}. Stop the existing service and retry.", file=sys.stderr)
            sys.exit(1)
'; then
  exit 1
fi

backend_pid=""
frontend_pid=""
cleanup() {
  trap - EXIT INT TERM
  for pid in "$backend_pid" "$frontend_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  for pid in "$backend_pid" "$frontend_pid"; do
    if [[ -n "$pid" ]]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 &
backend_pid=$!
./node_modules/.bin/vite --host 127.0.0.1 --port 5173 --strictPort &
frontend_pid=$!

ready=false
for ((attempt = 0; attempt < 30; attempt++)); do
  if ! kill -0 "$backend_pid" 2>/dev/null || ! kill -0 "$frontend_pid" 2>/dev/null; then
    echo "A server stopped during startup. Check the errors above." >&2
    exit 1
  fi
  if curl -fsS --max-time 1 http://127.0.0.1:8000/api/config >/dev/null 2>&1 &&
     curl -fsS --max-time 1 http://127.0.0.1:5173/ >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  echo "Servers did not become ready in time. Check the errors above." >&2
  exit 1
fi

echo
echo "Resume Genie is ready at http://127.0.0.1:5173"
echo "Keep this terminal open. Press Ctrl+C to stop both servers."
echo
while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 2
done
echo "A server stopped unexpectedly; stopping the other server." >&2
exit 1
