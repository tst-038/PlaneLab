#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CORE_SERVICES=(traefik jellyfin)
MANAGED_SERVICES=(
  traefik jellyfin seerr prowlarr usenet-proxy sonarr radarr sabnzbd
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

  home     Jellyfin/Gelato only; online libraries visible
  prepare  Full stack on the Pi; online and offline libraries visible
  travel   Jellyfin playback only; offline libraries visible
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
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required for Jellyfin mode switching." >&2
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

apply_jellyfin_mode() {
  local mode api_key jellyfin_url excluded_users
  mode="$1"
  api_key="$(env_value JELLYFIN_API_KEY)"
  jellyfin_url="$(env_value JELLYFIN_URL)"
  excluded_users="$(env_value JELLYFIN_EXCLUDED_USERS)"
  jellyfin_url="${jellyfin_url:-http://localhost:8096}"

  if [[ -z "$api_key" || "$api_key" == "replace-with-jellyfin-api-key" ]]; then
    echo "Error: configure JELLYFIN_API_KEY in .env first." >&2
    echo "Jellyfin: Dashboard -> Advanced -> API Keys -> create PlaneLab key." >&2
    return 1
  fi

  JELLYFIN_API_KEY="$api_key" \
    JELLYFIN_URL="$jellyfin_url" \
    JELLYFIN_EXCLUDED_USERS="$excluded_users" \
    python3 "$SCRIPT_DIR/jellyfin-library-mode.py" "$mode"
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
"$SCRIPT_DIR/prepare.sh" >/dev/null

case "$mode" in
  home)
    docker compose up -d "${CORE_SERVICES[@]}"
    apply_jellyfin_mode home
    set_restart_policy no "${BACKGROUND_SERVICES[@]}"
    docker compose stop "${BACKGROUND_SERVICES[@]}"
    set_restart_policy unless-stopped "${CORE_SERVICES[@]}"
    ;;
  prepare)
    docker compose up -d "${PREPARATION_SERVICES[@]}"
    set_restart_policy unless-stopped "${MANAGED_SERVICES[@]}"
    apply_jellyfin_mode prepare
    ;;
  travel)
    docker compose up -d "${CORE_SERVICES[@]}"
    apply_jellyfin_mode travel
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
