#!/usr/bin/env bash
set -euo pipefail
server="https://team-contract.onrender.com"
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  if [[ "${args[$i]}" == "--server" ]]; then
    i=$((i+1))
    server="${args[$i]:?Missing server address}"
  fi
done
command -v python3 >/dev/null || { echo "Install Python 3 first: https://www.python.org/downloads/"; exit 1; }
command -v curl >/dev/null || { echo "curl is required to download Team Contract."; exit 1; }
folder=$(mktemp -d)
trap 'rm -rf "$folder"' EXIT
echo "Downloading Team Contract…"
curl -fsSL --retry 2 --connect-timeout 15 --max-time 120 "${server%/}/client.zip" -o "$folder/client.zip"
python3 -m zipfile -e "$folder/client.zip" "$folder"
if [[ -r /dev/tty ]]; then
  python3 "$folder/install.py" . --guided "${args[@]}" </dev/tty
else
  echo "Open Terminal in your project folder and run this command again. Setup needs your answers."
  exit 1
fi
