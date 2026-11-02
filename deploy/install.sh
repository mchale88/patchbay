#!/usr/bin/env bash
# Install Patchbay as a systemd service.
#
#   sudo ./deploy/install.sh [--prefix DIR] [--user NAME] [--ndi-lib PATH] [--no-start]
#
# Defaults: --prefix /opt/patchbay, state in /var/lib/patchbay,
# config in /etc/patchbay.env.
# If you pass --prefix, state and config live inside the prefix as well
# (DIR/state, DIR/patchbay.env). That keeps everything on one dataset,
# which TrueNAS needs (see the README).
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX=/opt/patchbay
STATE_DIR=/var/lib/patchbay
ENV_FILE=/etc/patchbay.env
RUN_USER=patchbay
NDI_LIB=""
START=1
CUSTOM_PREFIX=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) PREFIX="$(realpath -m "$2")"; CUSTOM_PREFIX=1; shift 2 ;;
    --user) RUN_USER="$2"; shift 2 ;;
    --ndi-lib) NDI_LIB="$(realpath "$2")"; shift 2 ;;
    --no-start) START=0; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done
if [[ $CUSTOM_PREFIX == 1 ]]; then
  STATE_DIR="$PREFIX/state"
  ENV_FILE="$PREFIX/patchbay.env"
fi

[[ $EUID -eq 0 ]] || { echo "run as root (sudo)" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

echo "==> Installing to $PREFIX (state: $STATE_DIR, config: $ENV_FILE, user: $RUN_USER)"

if ! id "$RUN_USER" >/dev/null 2>&1; then
  echo "==> Creating system user $RUN_USER"
  useradd --system --no-create-home --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$RUN_USER"
fi

mkdir -p "$PREFIX" "$STATE_DIR"

# Copy the source so the install does not depend on this checkout.
echo "==> Copying application"
rm -rf "$PREFIX/src"
mkdir -p "$PREFIX/src"
cp -a "$SRC/pyproject.toml" "$SRC/README.md" "$SRC/patchbay" "$SRC/deploy" "$PREFIX/src/"
# License terms and notices must accompany every copy (PolyForm "Notices", NDI SDK §3d).
cp -a "$SRC/LICENSE" "$SRC/NDI-SDK-NOTICE.md" "$SRC/COMMERCIAL.md" "$PREFIX/src/"
cp -a "$SRC/README.md" "$SRC/LICENSE" "$SRC/NDI-SDK-NOTICE.md" "$PREFIX/"

echo "==> Creating virtualenv"
if python3 -c 'import ensurepip' 2>/dev/null; then
  python3 -m venv "$PREFIX/venv"
else
  # e.g. TrueNAS SCALE ships python3 without ensurepip/pip
  python3 -m venv --without-pip "$PREFIX/venv"
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$PREFIX/get-pip.py"
  "$PREFIX/venv/bin/python" "$PREFIX/get-pip.py" -q
  rm -f "$PREFIX/get-pip.py"
fi
"$PREFIX/venv/bin/pip" install -q --upgrade "$PREFIX/src"

if [[ -n "$NDI_LIB" ]]; then
  echo "==> Installing NDI runtime from $NDI_LIB"
  mkdir -p "$PREFIX/lib"
  if [[ -d "$NDI_LIB" ]]; then cp -a "$NDI_LIB"/libndi.so* "$PREFIX/lib/"; else cp -a "$(dirname "$NDI_LIB")"/libndi.so* "$PREFIX/lib/"; fi
fi

# libndi links against libavahi-client.so.3. Some hosts (minimal Ubuntu, TrueNAS)
# lack it; use the copies in vendor/lib if present (the unit adds $PREFIX/lib to
# LD_LIBRARY_PATH).
if [[ -d "$PREFIX/lib" ]] && ! ldconfig -p 2>/dev/null | grep -q 'libavahi-client.so.3 '; then
  if compgen -G "$SRC/vendor/lib/libavahi-*.so*" >/dev/null; then
    echo "==> libavahi-client not installed system-wide; using vendored copy"
    cp -a "$SRC"/vendor/lib/libavahi-*.so* "$PREFIX/lib/"
  else
    echo "!!  libavahi-client.so.3 is missing. Install it (e.g. apt install libavahi-client3)" >&2
    echo "    or place libavahi-client/common .so files in $SRC/vendor/lib and re-run." >&2
  fi
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "==> Writing $ENV_FILE"
  cp "$SRC/deploy/patchbay.env.example" "$ENV_FILE"
  if [[ -d "$PREFIX/lib" ]]; then sed -i "s|^NDI_LIB_PATH=.*|NDI_LIB_PATH=$PREFIX/lib|" "$ENV_FILE"; fi
  chmod 640 "$ENV_FILE"; chgrp "$RUN_USER" "$ENV_FILE"
else
  echo "==> Keeping existing $ENV_FILE"
fi

chown -R "$RUN_USER:$RUN_USER" "$STATE_DIR"

echo "==> Installing systemd unit"
sed -e "s|@PREFIX@|$PREFIX|g" -e "s|@STATE_DIR@|$STATE_DIR|g" \
    -e "s|@ENV_FILE@|$ENV_FILE|g" -e "s|@USER@|$RUN_USER|g" \
    "$SRC/deploy/patchbay.service" > "$PREFIX/patchbay.service"
systemctl link "$PREFIX/patchbay.service" >/dev/null
systemctl daemon-reload
systemctl enable patchbay.service >/dev/null 2>&1 || true

if [[ $START == 1 ]]; then
  systemctl restart patchbay.service
  sleep 2
  systemctl --no-pager --lines=10 status patchbay.service || true
fi

PORT="$(grep -E '^PORT=' "$ENV_FILE" | cut -d= -f2)"
echo
echo "Done. Web UI:  http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT:-8080}/"
echo "      API docs: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT:-8080}/docs"
if [[ ! -s "$STATE_DIR/auth.json" ]]; then
  echo
  echo "Open the web UI now and create the admin account (first visitor gets to set it)."
fi
