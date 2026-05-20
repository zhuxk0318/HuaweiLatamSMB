#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SITE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="$SITE_ROOT/dist"
TARGET_DIR="/var/www/huawei-latam-smb-site"
NVM_SH="${NVM_DIR:-$HOME/.nvm}/nvm.sh"

if [[ -f "$NVM_SH" ]]; then
  # Load the user's Node toolchain when npm is managed by nvm.
  # shellcheck disable=SC1090
  source "$NVM_SH"
fi

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "publish-static-site: missing required command: $1" >&2
    exit 1
  fi
}

require_cmd npm
require_cmd rsync
require_cmd install

cd "$SITE_ROOT"
echo "Publishing static site from $SITE_ROOT to $TARGET_DIR"
npm run build

install -d "$TARGET_DIR"
rsync -a --delete "$DIST_DIR"/ "$TARGET_DIR"/
echo "Publish complete."
