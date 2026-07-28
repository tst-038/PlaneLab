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

was_running=0
if docker compose ps --status running --quiet | grep -q .; then
  was_running=1
fi

restart_stack() {
  if [[ "$was_running" -eq 1 ]]; then
    echo "Restarting PlaneLab..."
    docker compose start >/dev/null
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

cp compose.yml "$BACKUP_DIR/compose.yml"
if [[ -f .env ]]; then
  cp .env "$BACKUP_DIR/.env"
  chmod 600 "$BACKUP_DIR/.env"
fi

printf '%s\n' \
  "Created: $STAMP" \
  "Media and downloads are intentionally excluded." \
  "This backup contains secrets. Store it securely." \
  > "$BACKUP_DIR/README.txt"

echo
echo "Backup complete:"
echo "$BACKUP_DIR"
echo "This directory contains credentials and must not be committed."
