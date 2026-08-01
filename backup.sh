#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: Docker is not installed or not in PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Error: the Docker Compose plugin is unavailable." >&2
  exit 1
fi

"$SCRIPT_DIR/hardware-transcoding.sh" configure >/dev/null

VOLUMES=(
  planelab_jellyfin_config
  planelab_seerr_config
  planelab_prowlarr_config
  planelab_sonarr_config
  planelab_radarr_config
  planelab_sabnzbd_config
  planelab_rdtclient_data
  planelab_youtarr_database
  planelab_youtarr_config
  planelab_youtarr_images
  planelab_youtarr_jobs
)

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$SCRIPT_DIR/backups/$STAMP"
mkdir -p "$BACKUP_DIR"

running_services=()
while IFS= read -r service_name; do
  [[ -n "$service_name" ]] && running_services+=("$service_name")
done < <(docker compose ps --status running --services)

restart_stack() {
  if [[ "${#running_services[@]}" -gt 0 ]]; then
    echo "Restarting PlaneLab..."
    docker compose start "${running_services[@]}" >/dev/null
  fi
}
trap restart_stack EXIT INT TERM

echo "Stopping PlaneLab for a consistent backup..."
docker compose stop

for volume_name in "${VOLUMES[@]}"; do
  if ! docker volume inspect "$volume_name" >/dev/null 2>&1; then
    echo "Skipping missing volume: $volume_name"
    continue
  fi

  echo "Backing up $volume_name..."
  docker run --rm \
    -v "$volume_name:/source:ro" \
    -v "$BACKUP_DIR:/backup" \
    alpine:3.22 \
    tar -czf "/backup/$volume_name.tar.gz" -C /source .
done

cp compose.yml traefik.yml traefik-dynamic.yml library-modes.json "$BACKUP_DIR/"
if [[ -f .planelab-mode ]]; then
  cp .planelab-mode "$BACKUP_DIR/"
fi
if [[ -f .env ]]; then
  cp .env "$BACKUP_DIR/.env"
  chmod 600 "$BACKUP_DIR/.env"
fi

printf '%s\n' \
  "Created: $STAMP" \
  "PlaneLab mode: $([[ -f .planelab-mode ]] && cat .planelab-mode || echo 'not set')" \
  "Media and downloads are intentionally excluded." \
  "This backup contains secrets. Store it securely." \
  > "$BACKUP_DIR/README.txt"

echo
echo "Backup complete:"
echo "$BACKUP_DIR"
echo "This directory contains credentials and must not be committed."
