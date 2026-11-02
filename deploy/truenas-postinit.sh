#!/usr/bin/env bash
# TrueNAS SCALE post-init script: re-registers the Patchbay service after
# boot/upgrade (system updates replace the root filesystem and drop the unit link).
# Add it in System → Advanced → Init/Shutdown Scripts → Type: Script, When: Post Init:
#   /mnt/<pool>/apps/patchbay/src/deploy/truenas-postinit.sh /mnt/<pool>/apps/patchbay
set -eu
PREFIX="${1:?usage: truenas-postinit.sh <prefix>}"
USER_NAME="$(sed -n 's/^User=//p' "$PREFIX/patchbay.service")"
if ! id "$USER_NAME" >/dev/null 2>&1; then
  echo "user $USER_NAME missing; create it in Credentials → Users" >&2
  exit 1
fi
systemctl link "$PREFIX/patchbay.service"
systemctl daemon-reload
systemctl start patchbay.service
