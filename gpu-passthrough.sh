#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

OVERRIDE_FILE="$SCRIPT_DIR/compose.gpu.yml"
STATE_FILE="$SCRIPT_DIR/.planelab-gpu"

usage() {
  cat <<'EOF'
Usage: ./gpu-passthrough.sh <configure|status>

  configure  Detect a supported Linux DRI device and expose it to Remux
  status     Show the detected GPU passthrough state
EOF
}

env_value() {
  sed -n "s/^$1=//p" .env | tail -n 1
}

set_env_value() {
  local key value temp_file
  key="$1"
  value="$2"
  temp_file="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    index($0, key "=") == 1 {
      if (!found) print key "=" value
      found = 1
      next
    }
    { print }
    END { if (!found) print key "=" value }
  ' .env > "$temp_file"
  mv "$temp_file" .env
  chmod 600 .env
}

is_raspberry_pi() {
  local model_file model
  for model_file in /proc/device-tree/model /sys/firmware/devicetree/base/model; do
    if [[ -r "$model_file" ]]; then
      model="$(tr -d '\000' < "$model_file")"
      [[ "$model" == *"Raspberry Pi"* ]] && return 0
    fi
  done
  return 1
}

write_disabled_override() {
  printf 'services: {}\n' > "$OVERRIDE_FILE"
  printf 'disabled\n' > "$STATE_FILE"
}

detect_backend() {
  local device vendor_file vendor
  device="$1"
  vendor_file="/sys/class/drm/$(basename -- "$device")/device/vendor"
  vendor=""
  [[ -r "$vendor_file" ]] && read -r vendor < "$vendor_file"
  case "$vendor" in
    0x8086) printf 'qsv' ;;
    0x1002) printf 'vaapi' ;;
    *) printf 'unsupported' ;;
  esac
}

configure_host() {
  local preference render_device render_gid video_gid backend compose_files
  if [[ ! -f .env ]]; then
    echo "Error: .env is missing." >&2
    return 1
  fi

  compose_files="compose.yml:compose.gpu.yml"
  if [[ "$(uname -s)" == "Linux" && -f "$SCRIPT_DIR/compose.tailscale.yml" ]]; then
    compose_files+=":compose.tailscale.yml"
  fi
  set_env_value COMPOSE_FILE "$compose_files"

  preference="$(env_value PLANELAB_GPU_PASSTHROUGH)"
  preference="${preference:-auto}"
  case "$preference" in
    auto|off) ;;
    *)
      echo "Error: PLANELAB_GPU_PASSTHROUGH must be auto or off." >&2
      return 1
      ;;
  esac

  if [[ "$preference" == "off" || "$(uname -s)" != "Linux" ]] ||
    is_raspberry_pi; then
    write_disabled_override
    echo "GPU passthrough disabled for this host."
    return
  fi

  render_device=""
  for candidate in /dev/dri/renderD*; do
    if [[ -c "$candidate" ]]; then
      render_device="$candidate"
      break
    fi
  done
  if [[ -z "$render_device" ]]; then
    write_disabled_override
    echo "GPU passthrough disabled: no DRI render device found."
    return
  fi

  render_gid="$(stat -c '%g' "$render_device")"
  backend="$(detect_backend "$render_device")"
  if [[ "$backend" == "unsupported" ]]; then
    write_disabled_override
    echo "GPU passthrough disabled: DRI GPU vendor is not Intel or AMD."
    return
  fi

  video_gid="$(getent group video 2>/dev/null | cut -d: -f3 || true)"
  {
    printf 'services:\n'
    printf '  remux:\n'
    printf '    group_add:\n'
    printf "      - '%s'\n" "$render_gid"
    if [[ -n "$video_gid" && "$video_gid" != "$render_gid" ]]; then
      printf "      - '%s'\n" "$video_gid"
    fi
    printf '    devices:\n'
    printf '      - %s:%s\n' "$render_device" "$render_device"
  } > "$OVERRIDE_FILE"
  printf 'enabled:%s:%s\n' "$backend" "$render_device" > "$STATE_FILE"
  echo "GPU passthrough detected: $backend via $render_device."
}

case "${1:-status}" in
  configure) configure_host ;;
  status)
    if [[ -f "$STATE_FILE" ]]; then cat "$STATE_FILE"; else echo "not configured"; fi
    ;;
  *) usage >&2; exit 2 ;;
esac
