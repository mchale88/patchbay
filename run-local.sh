#!/usr/bin/env bash
# Run Patchbay from this checkout without systemd.
#   ./run-local.sh            start in background (logs: state/router.log)
#   ./run-local.sh fg         run in foreground
#   ./run-local.sh stop|status
set -euo pipefail
cd "$(dirname "$0")"
PIDFILE=state/router.pid
running() { [[ -f $PIDFILE ]] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; }
case "${1:-start}" in
  stop) running && kill "$(cat $PIDFILE)" && echo stopped || echo "not running"; rm -f $PIDFILE; exit 0 ;;
  status) running && echo "running (pid $(cat $PIDFILE))" || echo "not running"; exit 0 ;;
esac
set -a; source ./local.env; set +a
# libndi needs the Avahi client libs; use vendored copies if not installed system-wide
export LD_LIBRARY_PATH="$PWD/vendor/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
mkdir -p state
if [[ "${1:-start}" == fg ]]; then exec .venv/bin/python -m patchbay; fi
running && { echo "already running (pid $(cat $PIDFILE))"; exit 0; }
setsid nohup .venv/bin/python -m patchbay >> state/router.log 2>&1 < /dev/null &
echo $! > $PIDFILE
echo "started (pid $!), logs: state/router.log"
