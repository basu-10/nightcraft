#!/bin/bash

# Resolve the absolute path of the source code directory (where this script lives)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

cd "$SOURCE_DIR" || { echo "ERROR: Cannot change to source directory $SOURCE_DIR"; exit 1; }

# Find a free port, starting from 7100.
PORT=7100
while ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${PORT}$"; do
    echo "Port $PORT is in use, trying next..."
    PORT=$((PORT + 1))
done

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Python3 not found. Please install Python 3."
    exit 1
fi

# Create virtual environment if not exists
if [ ! -d "$SOURCE_DIR/venv" ]; then
    echo "Creating virtual environment at $SOURCE_DIR/venv..."
    python3 -m venv "$SOURCE_DIR/venv"
fi

# Activate virtual environment
source "$SOURCE_DIR/venv/bin/activate"

# Harden: confirm venv is active before proceeding
if [ -z "$VIRTUAL_ENV" ]; then
    echo "ERROR: Virtual environment failed to activate. Exiting."
    exit 1
fi
if [ "$VIRTUAL_ENV" != "$SOURCE_DIR/venv" ]; then
    echo "ERROR: Wrong virtual environment active ($VIRTUAL_ENV). Expected $SOURCE_DIR/venv. Exiting."
    exit 1
fi

# Install dependencies
if [ -f "$SOURCE_DIR/requirements.txt" ]; then
    echo "Installing dependencies..."
    pip install --upgrade pip
    pip install -r "$SOURCE_DIR/requirements.txt"
else
    echo "requirements.txt not found. Skipping dependency installation."
fi

# Start the webapp in the background
echo "==============================="
echo "Starting webapp on port $PORT..."
python "$SOURCE_DIR/tinyXL.py" --port "$PORT" &
SERVER_PID=$!

# Wait briefly then open browser.
sleep 3
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:$PORT" >/dev/null 2>&1 || true
fi

echo
echo "Server running at http://localhost:$PORT"
echo "Landing page: http://localhost:$PORT"
echo "Press Enter to stop the server."
read -r _

kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true