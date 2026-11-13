#!/usr/bin/env bash
set -euo pipefail
server="https://team-contract.onrender.com"
args=("$@")
# Read the server address from "--server URL" or "--server=URL", so the files
# always come from the server the person named.
for ((i=0; i<${#args[@]}; i++)); do
  case "${args[$i]}" in
    --server=*) server="${args[$i]#--server=}" ;;
    --server) i=$((i+1)); server="${args[$i]:?Missing server address}" ;;
  esac
done
command -v python3 >/dev/null || { echo "Install Python 3 first: https://www.python.org/downloads/"; exit 1; }
command -v curl >/dev/null || { echo "curl is required to download Team Contract."; exit 1; }
folder=$(mktemp -d)
trap 'rm -rf "$folder"' EXIT
echo "Downloading Team Contract…"
curl -fsSL --retry 2 --connect-timeout 15 --max-time 120 "${server%/}/client.zip" -o "$folder/client.zip"
python3 -m zipfile -e "$folder/client.zip" "$folder"
# -r is true even where no terminal exists (CI, some ssh sessions), so try to open it.
if (exec </dev/tty) 2>/dev/null; then
  # ${args[@]+...} keeps the Mac's old bash 3.2 from failing on an empty list.
  python3 "$folder/install.py" . --guided ${args[@]+"${args[@]}"} </dev/tty
else
  echo "Open Terminal in your project folder and run this command again. Setup needs your answers."
  exit 1
fi
