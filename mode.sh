#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CORE_SERVICES=(traefik remux)
MANAGED_SERVICES=(
  traefik remux seerr prowlarr usenet-proxy sonarr radarr sabnzbd
  rdtclient mariadb youtarr
)
PREPARATION_SERVICES=("${MANAGED_SERVICES[@]}")
BACKGROUND_SERVICES=(
  seerr prowlarr usenet-proxy sonarr radarr sabnzbd rdtclient mariadb youtarr
)
MODE_FILE="$SCRIPT_DIR/.planelab-mode"

usage() {
  cat <<'EOF'
Usage: ./mode.sh <home|prepare|travel|status>

  home     Remux playback only on the home server
  prepare  Full stack on the Pi for downloading and Remux setup
  travel   Remux playback only with the travel hotspot
  status   Show the last successfully applied mode
EOF
}

env_value() {
  sed -n "s/^$1=//p" .env | tail -n 1
}

require_runtime() {
  if [[ ! -f .env ]]; then
    echo "Error: .env is missing. Run ./planelab setup first." >&2
    exit 1
  fi
  if ! command -v docker >/dev/null 2>&1 ||
    ! docker compose version >/dev/null 2>&1; then
    echo "Error: Docker Engine with Compose is required." >&2
    exit 1
  fi
}

set_restart_policy() {
  local policy service container_id
  policy="$1"
  shift
  for service in "$@"; do
    container_id="$(docker compose ps -aq "$service" 2>/dev/null || true)"
    if [[ -n "$container_id" ]]; then
      docker update --restart="$policy" "$container_id" >/dev/null
    fi
  done
}

activate_hotspot_for_travel() {
  local setting
  setting="$(env_value PLANELAB_TRAVEL_HOTSPOT)"
  setting="${setting:-auto}"
  [[ "$(uname -s)" == "Linux" ]] || return 0
  [[ "$setting" != "off" ]] || return 0

  if [[ "$setting" == "on" ]]; then
    "$SCRIPT_DIR/hotspot.sh" up
  elif [[ "$setting" == "auto" ]] &&
    command -v nmcli >/dev/null 2>&1 &&
    [[ -f "$SCRIPT_DIR/hotspot.env" ]]; then
    "$SCRIPT_DIR/hotspot.sh" up ||
      echo "Warning: travel mode is active but hotspot activation failed." >&2
  fi
}

remove_legacy_jellyfin() {
  if docker inspect jellyfin >/dev/null 2>&1; then
    echo "Removing the legacy Jellyfin container; its volumes are preserved."
    docker rm -f jellyfin >/dev/null
  fi
}

mode="${1:-status}"
if [[ "$#" -gt 1 ]]; then
  usage >&2
  exit 2
fi

if [[ "$mode" == "status" ]]; then
  if [[ -f "$MODE_FILE" ]]; then
    cat "$MODE_FILE"
  else
    echo "not set"
  fi
  exit 0
fi

case "$mode" in
  home|prepare|travel) ;;
  *)
    usage >&2
    exit 2
    ;;
esac

require_runtime
"$SCRIPT_DIR/gpu-passthrough.sh" configure
"$SCRIPT_DIR/prepare.sh" >/dev/null
remove_legacy_jellyfin

# Keep the optional Linux Tailscale node alive in every operating mode.
if docker compose config --services | grep -qx tailscale; then
  CORE_SERVICES+=(tailscale)
  MANAGED_SERVICES+=(tailscale)
  PREPARATION_SERVICES+=(tailscale)
fi

case "$mode" in
  home)
    docker compose up -d "${CORE_SERVICES[@]}"
    set_restart_policy no "${BACKGROUND_SERVICES[@]}"
    docker compose stop "${BACKGROUND_SERVICES[@]}"
    set_restart_policy unless-stopped "${CORE_SERVICES[@]}"
    ;;
  prepare)
    docker compose up -d "${PREPARATION_SERVICES[@]}"
    set_restart_policy unless-stopped "${MANAGED_SERVICES[@]}"
    ;;
  travel)
    docker compose up -d "${CORE_SERVICES[@]}"
    set_restart_policy no "${BACKGROUND_SERVICES[@]}"
    docker compose stop "${BACKGROUND_SERVICES[@]}"
    set_restart_policy unless-stopped "${CORE_SERVICES[@]}"
    activate_hotspot_for_travel
    ;;
esac

printf '%s\n' "$mode" > "$MODE_FILE"
echo
echo "PlaneLab mode '$mode' is active."
docker compose ps
