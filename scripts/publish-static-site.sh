#!/usr/bin/env bash
set -euo pipefail

SITE_ROOT="/root/huawei-latam-smb-site"
DIST_DIR="$SITE_ROOT/dist"
TARGET_DIR="/var/www/huawei-latam-smb-site"

cd "$SITE_ROOT"
npm run build

install -d "$TARGET_DIR"
rsync -a --delete "$DIST_DIR"/ "$TARGET_DIR"/
