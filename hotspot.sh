#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/hotspot.env"

usage() {
  cat <<'EOF'
Usage:
  ./hotspot.sh install [--force]  Create/update and activate the hotspot
  ./hotspot.sh up                 Activate the existing hotspot
  ./hotspot.sh down               Deactivate the hotspot
  ./hotspot.sh status             Show hotspot and Wi-Fi status
  ./hotspot.sh remove             Remove the NetworkManager profile

Warning: installing on the Wi-Fi interface currently carrying your SSH
connection will disconnect that session. The script refuses this unless
--force is supplied.
EOF
}

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Error: hotspot.env does not exist." >&2
  echo "Create it with: cp hotspot.env.example hotspot.env" >&2
  exit 1
fi

# hotspot.env is a private, administrator-controlled shell configuration file.
# shellcheck disable=SC1090
source "$CONFIG_FILE"

: "${HOTSPOT_SSID:?Set HOTSPOT_SSID in hotspot.env}"
: "${HOTSPOT_PASSWORD:?Set HOTSPOT_PASSWORD in hotspot.env}"
: "${HOTSPOT_INTERFACE:=wlan0}"
: "${HOTSPOT_CONNECTION:=planelab-hotspot}"
: "${HOTSPOT_ADDRESS:=10.42.0.1/24}"
: "${HOTSPOT_BAND:=a}"
: "${HOTSPOT_CHANNEL:=36}"
: "${HOTSPOT_HIDDEN:=yes}"
: "${WIFI_COUNTRY:=BE}"

if [[ "${#HOTSPOT_PASSWORD}" -lt 8 || "${#HOTSPOT_PASSWORD}" -gt 63 ]]; then
  echo "Error: HOTSPOT_PASSWORD must contain 8-63 characters." >&2
  exit 1
fi

if [[ "$HOTSPOT_BAND" != "bg" && "$HOTSPOT_BAND" != "a" ]]; then
  echo "Error: HOTSPOT_BAND must be 'bg' (2.4 GHz) or 'a' (5 GHz)." >&2
  exit 1
fi

if ! command -v nmcli >/dev/null 2>&1; then
  echo "Error: nmcli/NetworkManager is not installed." >&2
  exit 1
fi

as_root() {
  if [[ "$EUID" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

connection_exists() {
  nmcli -t -f NAME connection show | grep -Fxq "$HOTSPOT_CONNECTION"
}

show_urls() {
  local hotspot_ip="${HOTSPOT_ADDRESS%/*}"
  cat <<EOF

Connect to Wi-Fi: $HOTSPOT_SSID

PlaneLab:
  Jellyfin  http://$hotspot_ip:8096
  Seerr     http://$hotspot_ip:5055
  Youtarr   http://$hotspot_ip:3087
EOF
}

command_name="${1:-}"
shift || true

case "$command_name" in
  install)
    force=0
    if [[ "${1:-}" == "--force" ]]; then
      force=1
      shift
    fi
    if [[ "$#" -ne 0 ]]; then
      usage >&2
      exit 2
    fi

    if ! nmcli -t -f DEVICE,TYPE device status |
      grep -Fqx "$HOTSPOT_INTERFACE:wifi"; then
      echo "Error: $HOTSPOT_INTERFACE is not a NetworkManager Wi-Fi device." >&2
      nmcli device status >&2
      exit 1
    fi

    ap_support="$(
      nmcli -g WIFI-PROPERTIES.AP device show "$HOTSPOT_INTERFACE" 2>/dev/null ||
        true
    )"
    if [[ "$ap_support" != "yes" ]]; then
      echo "Error: $HOTSPOT_INTERFACE does not report Wi-Fi AP support." >&2
      exit 1
    fi

    current_connection="$(
      nmcli -g GENERAL.CONNECTION device show "$HOTSPOT_INTERFACE" 2>/dev/null ||
        true
    )"
    if [[ -n "$current_connection" &&
      "$current_connection" != "--" &&
      "$current_connection" != "$HOTSPOT_CONNECTION" &&
      "$force" -ne 1 ]]; then
      cat >&2 <<EOF
Refusing to replace active Wi-Fi connection '$current_connection' on
$HOTSPOT_INTERFACE. This may be carrying your SSH session.

Connect through Ethernet/local console, or deliberately run:
  ./hotspot.sh install --force
EOF
      exit 1
    fi

    if command -v raspi-config >/dev/null 2>&1; then
      as_root raspi-config nonint do_wifi_country "$WIFI_COUNTRY"
    fi

    as_root nmcli radio wifi on

    if ! connection_exists; then
      as_root nmcli connection add \
        type wifi \
        ifname "$HOTSPOT_INTERFACE" \
        con-name "$HOTSPOT_CONNECTION" \
        ssid "$HOTSPOT_SSID"
    fi

    # NetworkManager defines wpa-psk as WPA2 + WPA3 Personal transition mode.
    as_root nmcli connection modify "$HOTSPOT_CONNECTION" \
      connection.interface-name "$HOTSPOT_INTERFACE" \
      connection.autoconnect yes \
      connection.autoconnect-priority 100 \
      802-11-wireless.mode ap \
      802-11-wireless.ssid "$HOTSPOT_SSID" \
      802-11-wireless.band "$HOTSPOT_BAND" \
      802-11-wireless.channel "$HOTSPOT_CHANNEL" \
      802-11-wireless.hidden "$HOTSPOT_HIDDEN" \
      802-11-wireless.ap-isolation yes \
      802-11-wireless-security.key-mgmt wpa-psk \
      802-11-wireless-security.proto rsn \
      802-11-wireless-security.pairwise ccmp \
      802-11-wireless-security.group ccmp \
      802-11-wireless-security.pmf optional \
      802-11-wireless-security.wps-method disabled \
      802-11-wireless-security.psk "$HOTSPOT_PASSWORD" \
      ipv4.method shared \
      ipv4.addresses "$HOTSPOT_ADDRESS" \
      ipv6.method disabled

    as_root nmcli connection up "$HOTSPOT_CONNECTION"
    show_urls
    ;;

  up)
    if ! connection_exists; then
      echo "Error: hotspot is not installed. Run ./hotspot.sh install." >&2
      exit 1
    fi
    as_root nmcli connection up "$HOTSPOT_CONNECTION"
    show_urls
    ;;

  down)
    if connection_exists; then
      as_root nmcli connection down "$HOTSPOT_CONNECTION" || true
    fi
    ;;

  status)
    nmcli device status
    echo
    if connection_exists; then
      nmcli --show-secrets connection show "$HOTSPOT_CONNECTION" |
      grep -E '^(connection.id|connection.interface-name|connection.autoconnect|802-11-wireless.ssid|802-11-wireless.mode|802-11-wireless.band|802-11-wireless.channel|802-11-wireless.hidden|802-11-wireless-security.key-mgmt|802-11-wireless-security.proto|802-11-wireless-security.pairwise|802-11-wireless-security.group|802-11-wireless-security.pmf|802-11-wireless-security.wps-method|ipv4.method|ipv4.addresses)'
      show_urls
    else
      echo "Hotspot profile '$HOTSPOT_CONNECTION' is not installed."
    fi
    ;;

  remove)
    if connection_exists; then
      as_root nmcli connection delete "$HOTSPOT_CONNECTION"
      echo "Removed hotspot profile: $HOTSPOT_CONNECTION"
    else
      echo "Hotspot profile does not exist."
    fi
    ;;

  *)
    usage >&2
    exit 2
    ;;
esac
