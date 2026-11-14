#!/bin/sh
# Start the shared contract server so teammates on the same Wi-Fi or hotspot can
# reach it. Run from anywhere:
#
#     sh start_server.sh          (port 8000)
#     PORT=9000 sh start_server.sh
#
# The first run creates the virtual environment and installs the libraries.
# Stop the server with Ctrl+C.

set -e
cd "$(dirname "$0")"
PORT="${PORT:-8000}"

if [ ! -x .venv/bin/uvicorn ]; then
    echo "First run: installing libraries..."
    python3 -m venv .venv
    .venv/bin/pip install --quiet -r server/requirements.txt
fi

# This computer's address on the local network. No data is sent: opening a UDP
# socket only asks the system which network interface it would use.
ADDRESS=$(.venv/bin/python -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(('10.255.255.255', 1))
    print(s.getsockname()[0])
except OSError:
    print('127.0.0.1')
")

if [ ! -f .env ]; then
    echo "Note: no .env file, so the conflict check is OFF. Copy .env.example to .env and add your key."
fi

echo ""
echo "CoopDev server"
echo "  On this computer:   http://127.0.0.1:$PORT/?room=demo"
echo "  For teammates:      http://$ADDRESS:$PORT"
echo "  (teammates must be on the same Wi-Fi or hotspot, and use that address"
echo "   as the server when they run install.py)"
echo ""

# 0.0.0.0 means: accept connections from other devices, not only this one.
exec .venv/bin/uvicorn server.server:app --host 0.0.0.0 --port "$PORT"
