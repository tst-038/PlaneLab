#!/usr/bin/env bash
set -Eeuo pipefail

VOLUMES=(
  planelab_jellyfin_config
  planelab_jellyfin_cache
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

for volume_name in "${VOLUMES[@]}"; do
  if docker volume inspect "$volume_name" >/dev/null 2>&1; then
    echo "Exists:  $volume_name"
  else
    docker volume create "$volume_name" >/dev/null
    echo "Created: $volume_name"
  fi
done

echo
echo "External PlaneLab volumes are ready."
