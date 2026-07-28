#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "Usage: ethernet-watch.sh <interface> <hotspot-connection> <hotspot-script>" >&2
  exit 2
fi

ETHERNET_INTERFACE="$1"
HOTSPOT_CONNECTION="$2"
HOTSPOT_SCRIPT="$3"
CARRIER_FILE="/sys/class/net/$ETHERNET_INTERFACE/carrier"
last_state=""

while true; do
  carrier="0"
  hotspot_active="0"

  if [[ -r "$CARRIER_FILE" ]]; then
    carrier="$(<"$CARRIER_FILE")"
  fi
  if nmcli -t -f NAME connection show --active 2>/dev/null |
    grep -Fxq "$HOTSPOT_CONNECTION"; then
    hotspot_active="1"
  fi

  current_state="$carrier:$hotspot_active"
  if [[ "$current_state" != "$last_state" ]]; then
    last_state="$current_state"
    if [[ "$current_state" == "1:1" ]]; then
      logger -t planelab \
        "Ethernet carrier detected while hotspot is active; running smart detection"
      if ! "$HOTSPOT_SCRIPT" ethernet smart; then
        logger -t planelab "Ethernet smart detection failed"
      fi
    fi
  fi

  sleep 2
done
