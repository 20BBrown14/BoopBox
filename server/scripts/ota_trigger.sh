#!/usr/bin/env bash
# Trigger the OTA version check. Usage: ota_trigger.sh [device_id]
# Reads BOOPBOX_AUTH_USERNAME/PASSWORD from .env; BASE overrides the server URL.
set -euo pipefail

cd "$(dirname "$0")/.."
env_get() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }

BASE="${BASE:-$(env_get BOOPBOX_PUBLIC_BASE_URL)}"
BASE="${BASE:-http://127.0.0.1:9685}"
USERNAME="$(env_get BOOPBOX_AUTH_USERNAME)"
PASSWORD="$(env_get BOOPBOX_AUTH_PASSWORD)"

TOKEN="$(python3 -c 'import json,sys; print(json.dumps({"username":sys.argv[1],"password":sys.argv[2]}))' "$USERNAME" "$PASSWORD" \
  | curl -fsS -X POST "$BASE/auth/token" -H 'Content-Type: application/json' -d @- \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"

if [[ $# -ge 1 ]]; then
  BODY="$(python3 -c 'import json,sys; print(json.dumps({"device_id":sys.argv[1]}))' "$1")"
else
  BODY='{}'
fi

curl -fsS -X POST "$BASE/ota/update" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "$BODY"
echo
