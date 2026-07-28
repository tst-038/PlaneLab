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

if [[ ! -f .env && -f "$BACKUP_DIR/.env" ]]; then
  cp "$BACKUP_DIR/.env" .env
  chmod 600 .env
  echo "Restored .env; verify MEDIA_ROOT and DOWNLOAD_ROOT for this machine."
fi

echo "Starting PlaneLab..."
docker compose up -d
docker compose ps

echo
echo "Restore complete."
echo "Verify the SSD mount and application health before downloading anything."
