# PlaneLab

Offline-first Jellyfin provisioning stack for a Raspberry Pi or a macOS test
machine. Use it only with media and sources you are authorized to access.

## PlaneLab control center

The easiest way to manage the appliance is the dependency-free terminal UI:

```bash
./planelab
```

It provides first-time setup, service control and updates, backup/restore,
hotspot and temporary uplink management, Ethernet modes, logs, status, and all
local service addresses. Navigate with the arrow keys and Enter (`j`/`k` also
work), and press Escape to return to the previous screen. Numbered input
remains available when no interactive terminal is attached. The same entry
point also works without the menu:

```bash
./planelab setup
./planelab backup
./planelab update
./planelab network uplink "WorkshopWiFi"
./planelab network ethernet shared
```

## Services

| Service | URL | Purpose |
|---|---:|---|
| Jellyfin | `http://jellyfin.planelab` | Offline playback |
| Seerr | `http://seerr.planelab` | Requests |
| Sonarr | `http://sonarr.planelab` | TV management |
| Radarr | `http://radarr.planelab` | Movie management |
| Prowlarr | `http://prowlarr.planelab` | Indexer management |
| SABnzbd | `http://sabnzbd.planelab` | TorBox News/Usenet client |
| RDTClient | `http://rdtclient.planelab` | TorBox torrent adapter |
| Youtarr | `http://youtarr.planelab` | YouTube library provisioning |

Traefik listens on port 80 and routes each local hostname to its service.
NetworkManager's shared DNS advertises the names to hotspot and shared-Ethernet
clients. The original IP-and-port URLs remain available for troubleshooting.

## First start on macOS

```bash
cp .env.example .env
mkdir -p data/media/{movies,shows,YouTube}
mkdir -p data/downloads/{incomplete,complete/{radarr,sonarr}}
./prepare.sh
docker compose config
docker compose pull
docker compose up -d
```

## Raspberry Pi

Use Raspberry Pi OS 64-bit. Ensure `uname -m` reports `aarch64`, install Docker
Engine and the Compose plugin, and mount the media SSD at `/mnt/nvme`.

Create the storage directories:

```bash
sudo mkdir -p /mnt/nvme/media/{movies,shows,YouTube}
sudo mkdir -p /mnt/nvme/downloads/{incomplete,complete/{radarr,sonarr}}
sudo chown -R 1000:1000 /mnt/nvme
```

Copy `.env.example` to `.env` and use:

```dotenv
MEDIA_ROOT=/mnt/nvme/media
DOWNLOAD_ROOT=/mnt/nvme/downloads
```

Never start the stack until `/mnt/nvme` is mounted. Otherwise Docker may create
the directories on the Pi's SD card.

Create the external application volumes before the first start:

```bash
./prepare.sh
docker compose up -d
```

## PlaneLab Wi-Fi hotspot

Raspberry Pi OS Bookworm and newer use NetworkManager. Configure a persistent
hotspot with:

```bash
cp hotspot.env.example hotspot.env
nano hotspot.env
./hotspot.sh install
```

Run this from a local console or an Ethernet SSH session. If `wlan0` currently
carries SSH, the script refuses to disconnect it unless you explicitly use
`./hotspot.sh install --force`.

The default hotspot is:

```text
SSID: PlaneLab
Pi address: 10.42.0.1
Band: 5 GHz, channel 36
SSID broadcast: hidden
Security: WPA2/WPA3 Personal transition mode, AES/CCMP, WPS disabled
```

NetworkManager's shared IPv4 mode supplies DHCP and DNS to passengers and
shares an Ethernet/second-adapter uplink when one exists. No uplink is required
to use Jellyfin offline. Client isolation, hidden SSID, and connection autostart
are enabled. Passengers must manually enter the exact SSID and password.

NetworkManager calls WPA2/WPA3 Personal transition mode `wpa-psk`. Recent
clients can negotiate WPA3 while older clients retain WPA2 compatibility.
WPA3-only (`sae`) is deliberately not the default because Raspberry Pi AP
drivers and older passenger devices can fail to connect to it.

Useful commands:

```bash
./hotspot.sh status
./hotspot.sh down
./hotspot.sh up
./hotspot.sh ethernet smart
./hotspot.sh ethernet auto
./hotspot.sh ethernet shared
./hotspot.sh remove
```

The connection profile autostarts after reboot. PlaneLab is always reached
directly through the fixed address `10.42.0.1`. Installing the hotspot also
enables automatic Ethernet smart detection as a systemd service and installs
the local `.planelab` DNS records.

After `./hotspot.sh install` and `docker compose up -d`, clients using PlaneLab
DHCP can open services without remembering IP addresses or ports:

```text
http://jellyfin.planelab
http://seerr.planelab
http://youtarr.planelab
```

Clients connected through an unrelated router in Ethernet `auto` mode use that
router's DNS and may not know the private names. In that case use the Pi's
assigned address and original service port. Private/secure DNS settings on some
phones can also bypass the DNS server supplied by PlaneLab.

### Temporarily connect to uplink Wi-Fi

Switch the built-in adapter from hotspot to Wi-Fi client mode. Supplying only
the SSID makes the script ask for the password without displaying it:

```bash
./hotspot.sh uplink "WorkshopWiFi"
```

For maximum convenience, the password can also be supplied directly. Be aware
that this may store it in your shell history:

```bash
./hotspot.sh uplink "WorkshopWiFi" "the-password"
```

Return to PlaneLab hotspot mode:

```bash
./hotspot.sh up
```

The script automatically stops the hotspot, uses NetworkManager's normal
`device wifi connect` flow, and marks the temporary uplink as non-autoconnect.
After a reboot, the PlaneLab hotspot therefore starts automatically again. A
single Wi-Fi adapter cannot reliably serve the 5 GHz hotspot and connect to
another Wi-Fi network simultaneously. Use Ethernet or a second Wi-Fi adapter
if both must remain active.

### Choose the Ethernet mode

The recommended mode first tries to obtain a DHCP lease and IPv4 default
gateway from an Ethernet router. Merely activating through IPv6 link-local or
receiving an address without a gateway does not count as an uplink. If no
usable gateway is found within 12 seconds, PlaneLab automatically switches the
port to shared mode:

```bash
./hotspot.sh ethernet smart
```

This is the default behaviour after `./hotspot.sh install`. A lightweight
watcher checks for Ethernet carrier changes and reruns smart detection whenever
a cable is connected while the PlaneLab hotspot is active. It also detects an
already connected cable when the hotspot starts or the Pi reboots. The watcher
does nothing while PlaneLab is using temporary uplink Wi-Fi. Disable this
automation by setting `ETHERNET_SMART_WATCH=no` before reinstalling the hotspot;
`./hotspot.sh remove` removes the installed systemd service.

Use `auto` when the Pi is connected to a router and should receive an address
and internet connection through DHCP:

```bash
./hotspot.sh ethernet auto
```

Use `shared` when a laptop or other device is connected directly to the Pi and
the Pi should provide DHCP and networking over the Ethernet cable:

```bash
./hotspot.sh ethernet shared
```

Shared Ethernet uses `10.42.1.1/24`, separate from the Wi-Fi hotspot at
`10.42.0.1/24`. The selected Ethernet mode persists across reboots. It does not
change the Wi-Fi hotspot itself, which must remain in NetworkManager's `shared`
mode to provide addresses to its Wi-Fi clients.

## Internal paths

Configure applications with container paths, never host paths:

- Sonarr root folder: `/media/shows`
- Radarr root folder: `/media/movies`
- SABnzbd temporary folder: `/downloads/incomplete`
- SABnzbd completed folder: `/downloads/complete`
- RDTClient download and mapped paths: `/downloads`
- Youtarr internal data path: `/usr/src/app/data`

Youtarr's `YOUTUBE_OUTPUT_DIR` variable is informational and represents the
host directory. Its actual in-container download directory is `DATA_PATH`,
which defaults to `/usr/src/app/data`. The Compose file therefore mounts
`${MEDIA_ROOT}/YouTube` at `/usr/src/app/data`.

Containers address one another by Compose service name:

- `http://jellyfin:8096`
- `http://sonarr:8989`
- `http://radarr:7878`
- `http://prowlarr:9696`
- `http://sabnzbd:8080`
- `http://rdtclient:6500`

## Back up application data

```bash
./backup.sh
```

The script stops the stack briefly and stores consistent archives under a
timestamped `backups/` directory. Media, downloads, and Jellyfin cache are
excluded. The resulting backup contains credentials and must be stored
securely outside Git.

## Restore on a new machine

Copy a timestamped backup directory into `backups/`, then run:

```bash
./restore.sh backups/20260728T120000Z
```

If `.env` does not exist, restore copies it from the backup and stops so you
can change the Mac paths to `/mnt/nvme/...`. Run the restore command again only
after `/mnt/nvme` is mounted. The script refuses Pi restores using paths outside
that mounted filesystem.

Restore refuses non-empty volumes. To deliberately replace an existing
installation:

```bash
./restore.sh --replace backups/20260728T120000Z
```

`--replace` deletes and recreates matching PlaneLab configuration volumes.
It never touches media or download directories.

## Git

```bash
git init
git add compose.yml traefik.yml traefik-dynamic.yml .env.example hotspot.env.example .gitignore prepare.sh backup.sh restore.sh hotspot.sh ethernet-watch.sh planelab README.md
git commit -m "Initial PlaneLab stack"
```

Do not commit `.env`, `backups/`, media, downloads, API keys, or passwords.

## Useful checks

```bash
docker compose config
docker compose ps
docker compose logs --tail=100
docker compose exec sonarr ls -la /media/shows
docker compose exec radarr ls -la /media/movies
docker compose exec sabnzbd ls -la /downloads
```

Application volumes are declared `external: true`. Compose therefore reuses
volumes restored or created by `prepare.sh`, and even `docker compose down -v`
will not delete them. Delete an external volume only with an explicit
`docker volume rm planelab_...` command.
