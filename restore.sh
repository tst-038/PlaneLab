#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

usage() {
  cat <<'EOF'
Usage:
  ./restore.sh <backup-directory>
  ./restore.sh --replace <backup-directory>

Without --replace, restore refuses to write into non-empty volumes.
With --replace, matching PlaneLab volumes are deleted and recreated first.
Media and downloads are never modified.
EOF
}

replace=0
if [[ "${1:-}" == "--replace" ]]; then
  replace=1
  shift
fi

if [[ "$#" -ne 1 ]]; then
  usage >&2
  exit 2
fi

BACKUP_DIR="$(cd -- "$1" && pwd)"
shopt -s nullglob
archives=("$BACKUP_DIR"/planelab_*.tar.gz)
shopt -u nullglob

if [[ "${#archives[@]}" -eq 0 ]]; then
  echo "Error: no planelab_*.tar.gz archives found in $BACKUP_DIR" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  if [[ -f "$BACKUP_DIR/.env" ]]; then
    cp "$BACKUP_DIR/.env" .env
    chmod 600 .env
    cat <<'EOF'
Created .env from the backup, but restore has NOT started.

Edit .env and set the Raspberry Pi storage paths:
  MEDIA_ROOT=/mnt/nvme/media
  DOWNLOAD_ROOT=/mnt/nvme/downloads

Verify that /mnt/nvme is mounted, then run the same restore command again.
EOF
    exit 2
  fi

  echo "Error: .env is missing. Create it from .env.example before restore." >&2
  exit 1
fi

media_root="$(sed -n 's/^MEDIA_ROOT=//p' .env | tail -n 1)"
download_root="$(sed -n 's/^DOWNLOAD_ROOT=//p' .env | tail -n 1)"
if [[ "$media_root" != /mnt/nvme/* || "$download_root" != /mnt/nvme/* ]]; then
  cat >&2 <<EOF
Error: restore on the Pi requires NVMe paths in .env.
Current MEDIA_ROOT: ${media_root:-missing}
Current DOWNLOAD_ROOT: ${download_root:-missing}

Expected paths below /mnt/nvme to avoid writing media to the SD card.
EOF
  exit 1
fi

if ! mountpoint -q /mnt/nvme; then
  echo "Error: /mnt/nvme is not a mounted filesystem." >&2
  exit 1
fi

sudo mkdir -p \
  "$media_root/offline/movies" "$media_root/offline/shows" \
  "$media_root/gelato/movies" "$media_root/gelato/shows" \
  "$media_root/YouTube" \
  "$download_root/incomplete" \
  "$download_root/complete/radarr" "$download_root/complete/sonarr"
sudo chown -R "$(id -u):$(id -g)" "$media_root" "$download_root"

echo "Stopping PlaneLab..."
docker compose down

for archive_path in "${archives[@]}"; do
  archive_name="$(basename -- "$archive_path")"
  volume_name="${archive_name%.tar.gz}"

  if [[ "$volume_name" != planelab_* ]]; then
    echo "Refusing unexpected volume name: $volume_name" >&2
    exit 1
  fi

  if docker volume inspect "$volume_name" >/dev/null 2>&1; then
    if [[ "$replace" -eq 1 ]]; then
      echo "Replacing $volume_name..."
      docker volume rm "$volume_name" >/dev/null
      docker volume create "$volume_name" >/dev/null
    else
      nonempty="$(
        docker run --rm \
          -v "$volume_name:/target:ro" \
          alpine:3.22 \
          sh -c 'find /target -mindepth 1 -maxdepth 1 -print -quit'
      )"
      if [[ -n "$nonempty" ]]; then
        echo "Error: $volume_name is not empty." >&2
        echo "Use --replace only if you intend to overwrite existing app data." >&2
        exit 1
      fi
    fi
  else
    docker volume create "$volume_name" >/dev/null
  fi

  echo "Restoring $volume_name..."
  docker run --rm \
    -v "$volume_name:/target" \
    -v "$BACKUP_DIR:/backup:ro" \
    alpine:3.22 \
    tar -xzf "/backup/$archive_name" -C /target
done

# External volumes must exist before Compose starts. This also creates volumes
# intentionally excluded from backup, such as the disposable Jellyfin cache.
"$SCRIPT_DIR/prepare.sh"

echo "Starting PlaneLab..."
docker compose up -d
docker compose ps

echo
echo "Restore complete."
echo "Verify the SSD mount and application health before downloading anything."
