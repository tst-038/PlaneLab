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
./planelab mode prepare
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

## Home, preparation and travel modes

PlaneLab keeps one complete set of application volumes and switches runtime
behaviour without deleting containers or splitting backups:

| Mode | Intended machine | Running services | Visible managed libraries |
|---|---|---|---|
| `home` | Home server | Jellyfin and Traefik | Gelato online movies/series |
| `prepare` | Pi with internet | Full stack | Online and offline movies/series |
| `travel` | Pi while travelling | Jellyfin and Traefik | Offline movies/series |

Unmanaged Jellyfin libraries such as YouTube, music or photos remain visible in
every mode. Modes change library access for existing Jellyfin users; they do
not delete or recreate libraries. A comma-separated
`JELLYFIN_EXCLUDED_USERS` value can exempt specific accounts.

Create an API key under **Jellyfin Dashboard -> Advanced -> API Keys**, then
configure it through **Operating mode -> Configure Jellyfin API key** in the
TUI or place it in the private `.env`:

```dotenv
JELLYFIN_URL=http://localhost:8096
JELLYFIN_API_KEY=your-generated-key
JELLYFIN_EXCLUDED_USERS=
PLANELAB_TRAVEL_HOTSPOT=auto
```

All four managed libraries must exist with these exact container paths before
the first mode switch:

```text
/media/offline/movies
/media/offline/shows
/media/gelato/movies
/media/gelato/shows
```

Switch from the TUI or command line:

```bash
./planelab mode home
./planelab mode prepare
./planelab mode travel
./planelab mode status
```

Stopped background containers receive Docker restart policy `no`, so a daemon
or machine reboot does not unexpectedly start download services in `home` or
`travel`. `prepare` restores `unless-stopped` and starts the complete stack.
With `PLANELAB_TRAVEL_HOTSPOT=auto`, travel mode activates an already installed
hotspot on Linux when NetworkManager and `hotspot.env` are available. It never
installs or replaces a hotspot automatically.

## UsenetCrawler search compatibility

UsenetCrawler's general `search` returns releases that its structured
`tvsearch` omits. PlaneLab includes a small local proxy that changes
title-based TV searches into general searches:

```text
Sonarr -> Prowlarr -> usenet-proxy -> UsenetCrawler -> SABnzbd
```

The proxy removes the broken category, season and episode filters and sends
only the series title as a general search. Sonarr then parses and filters the
broad result set itself. Capability checks, downloads and API keys pass through
unchanged. Request URLs are deliberately not logged because they contain the
API key.

Build and start it:

```bash
docker compose up -d --build usenet-proxy
```

In Prowlarr, remove or disable the direct UsenetCrawler entry, then add its
**Generic Newznab** replacement:

- Name: `UsenetCrawler via PlaneLab proxy`
- URL: `http://usenet-proxy:8080`
- API path: `/api`
- API key: a newly generated UsenetCrawler key
- Categories: the normal TV categories

Run **Test**, save it, and perform a Prowlarr search first. Prowlarr will sync
this indexer to Sonarr through the already configured application connection.
Do not keep the old direct entry enabled or every query will be sent twice.

## First start on macOS

```bash
cp .env.example .env
mkdir -p data/media/{offline/{movies,shows},gelato/{movies,shows},YouTube}
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
sudo mkdir -p /mnt/nvme/media/{offline/{movies,shows},gelato/{movies,shows},YouTube}
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

- Sonarr root folder: `/media/offline/shows`
- Radarr root folder: `/media/offline/movies`
- Gelato movie base path: `/media/gelato/movies`
- Gelato series base path: `/media/gelato/shows`
- SABnzbd temporary folder: `/downloads/incomplete`
- SABnzbd completed folder: `/downloads/complete`
- RDTClient download and mapped paths: `/downloads`
- Youtarr internal data path: `/usr/src/app/data`

Youtarr's `YOUTUBE_OUTPUT_DIR` variable is informational and represents the
host directory. Its actual in-container download directory is `DATA_PATH`,
which defaults to `/usr/src/app/data`. The Compose file therefore mounts
`${MEDIA_ROOT}/YouTube` at `/usr/src/app/data`.

### Offline and Gelato libraries

Keep downloaded files and Gelato catalog entries in separate trees:

```text
/media
├── offline
│   ├── movies
│   └── shows
├── gelato
│   ├── movies
│   └── shows
└── YouTube
```

Create four dedicated Jellyfin libraries:

| Jellyfin library | Type | Only path |
|---|---|---|
| `✈️ Films gedownload` | Movies | `/media/offline/movies` |
| `✈️ Series gedownload` | Shows | `/media/offline/shows` |
| `🌐 Films online` | Movies | `/media/gelato/movies` |
| `🌐 Series online` | Shows | `/media/gelato/shows` |

Configure Gelato to import movies and series only into its two
`/media/gelato/...` paths. Never add a Gelato path to either downloaded
library. Jellyfin's global search and continue-watching views can still include
online entries because those views span libraries.

For an existing installation, create the new directories first, move existing
movie and series files into the corresponding `/media/offline/...`
directories, then update the root folders in Radarr and Sonarr. Do not leave
the old `/media/movies` or `/media/shows` roots configured after migration.

Containers address one another by Compose service name:

- `http://jellyfin:8096`
- `http://sonarr:8989`
- `http://radarr:7878`
- `http://prowlarr:9696`
- `http://usenet-proxy:8080` (Prowlarr only)
- `http://sabnzbd:8080`
- `http://rdtclient:6500`

## Back up application data

```bash
./backup.sh
```

The script stops the stack briefly and stores consistent archives under a
timestamped `backups/` directory. Media, downloads, and Jellyfin cache are
excluded. The resulting backup contains credentials and must be stored
securely outside Git. Every application volume is included even when its
container is stopped by the current mode. Backup records the current mode and
restarts only the services that were running before the backup.

## Restore on a new machine

Copy a timestamped backup directory into `backups/`, then run:

```bash
./restore.sh backups/20260728T120000Z
```

If `.env` does not exist, restore copies it from the backup and stops so you
can review `MEDIA_ROOT` and `DOWNLOAD_ROOT` for the current machine. Relative
macOS paths such as `./data/media` are valid. When either configured path is
under `/mnt/nvme`, restore additionally verifies that `/mnt/nvme` is mounted
before creating directories or touching application volumes.

When the target already has `.env`, restore preserves its machine-specific
paths, UID/GID and network settings. It imports the MariaDB, Youtarr and
Jellyfin API credentials that belong to the restored volumes. If the backup
contains a recorded PlaneLab mode, restore reapplies that mode instead of
blindly starting every service.

### Server-to-Pi handoff

The home server never needs to download media:

```text
Home server: mode home -> backup
Pi:          restore -> mode prepare -> download travel media -> mode travel
Return:      Pi backup -> restore on server -> mode home
```

The configuration backup is complete, but media remains intentionally
separate. Offline files must already be on the Pi NVMe or be transferred
separately. Do not run both restored copies as independently changing masters;
stop and back up the current machine before restoring onto the other one.

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
docker compose exec sonarr ls -la /media/offline/shows
docker compose exec radarr ls -la /media/offline/movies
docker compose exec jellyfin ls -la /media/gelato
docker compose exec sabnzbd ls -la /downloads
```

Application volumes are declared `external: true`. Compose therefore reuses
volumes restored or created by `prepare.sh`, and even `docker compose down -v`
will not delete them. Delete an external volume only with an explicit
`docker volume rm planelab_...` command.
