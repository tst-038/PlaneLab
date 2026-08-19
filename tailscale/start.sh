#!/bin/sh
set -eu

/usr/local/bin/containerboot &
boot_pid=$!

stop_containerboot() {
  kill -TERM "$boot_pid" 2>/dev/null || true
  wait "$boot_pid" 2>/dev/null || true
}
trap stop_containerboot INT TERM EXIT

# containerboot owns authentication and tailscaled. Wait until this node has a
# tailnet address before applying the newer Tailscale Services configuration.
attempt=0
while ! tailscale ip -4 2>/dev/null | grep -q .; do
  if ! kill -0 "$boot_pid" 2>/dev/null; then
    wait "$boot_pid"
    exit $?
  fi
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "Timed out waiting for Tailscale authentication" >&2
    exit 1
  fi
  sleep 1
done

tailscale serve set-config --all /config/serve.json
tailscale serve advertise svc:jellyfin

set +e
wait "$boot_pid"
status=$?
set -e
trap - INT TERM EXIT
exit "$status"
