# PlaneLab

Offline-first Remux media stack for a Raspberry Pi or a macOS test machine.
Use it only with media and sources you are authorized to access.

## Control center

Run the dependency-free terminal interface:

```bash
./planelab
```

It handles setup, service control, modes, updates, backup and restore, network
management, logs, status, and service addresses. The same entry point works
without the menu:

```bash
./planelab setup
./planelab start
./planelab mode prepare
./planelab network uplink "WorkshopWiFi"
./planelab gpu status
```

## Services

| Service | Local URL | Purpose |
|---|---:|---|
| Remux | `http://jellyfin.planelab` | Media server and playback |
| Remux alias | `http://remux.planelab` | Alternate local name |
| Seerr | `http://seerr.planelab` | Requests |
| Sonarr | `http://sonarr.planelab` | TV management |
| Radarr | `http://radarr.planelab` | Movie management |
| Prowlarr | `http://prowlarr.planelab` | Indexer management |
| SABnzbd | `http://sabnzbd.planelab` | TorBox News/Usenet client |
| RDTClient | `http://rdtclient.planelab` | TorBox torrent adapter |
| Youtarr | `http://youtarr.planelab` | YouTube provisioning |

Remux replaces Jellyfin and keeps the familiar external port `8096`, the
`jellyfin.planelab` hostname, and `svc:jellyfin` Tailscale Service name. That
avoids changing existing client addresses. The `remux.planelab` hostname is an
additional alias; there is only one media-server container.

Traefik listens on port 80 and routes the local hostnames. Direct IP-and-port
addresses remain available for troubleshooting.

## First setup

The easiest setup is:

```bash
cp .env.example .env
./planelab setup
```

For a manual macOS test setup:

```bash
mkdir -p data/media/{offline/{movies,shows},YouTube}
mkdir -p data/downloads/{incomplete,complete/{radarr,sonarr}}
./prepare.sh
./gpu-passthrough.sh configure
docker compose config
docker compose pull
docker compose up -d
```

`prepare.sh` only creates the external Docker volumes. It does not start the
stack, modify Remux, or configure Tailscale.

On the first start after this migration, PlaneLab removes the legacy container
named `jellyfin` so Remux can claim port `8096`. It does not delete
the old `planelab_jellyfin_config` or `planelab_jellyfin_cache` volumes. They
remain available for manual recovery until you deliberately remove them.

## Raspberry Pi storage

Use Raspberry Pi OS 64-bit, install Docker Engine and its Compose plugin, and
mount the media SSD at `/mnt/nvme`.

```bash
sudo mkdir -p /mnt/nvme/media/{offline/{movies,shows},YouTube}
sudo mkdir -p /mnt/nvme/downloads/{incomplete,complete/{radarr,sonarr}}
sudo chown -R 1000:1000 /mnt/nvme
```

Use these values in `.env`:

```dotenv
MEDIA_ROOT=/mnt/nvme/media
DOWNLOAD_ROOT=/mnt/nvme/downloads
COMPOSE_FILE=compose.yml:compose.gpu.yml:compose.tailscale.yml
PLANELAB_GPU_PASSTHROUGH=auto
TAILSCALE_HOSTNAME=planelab
TAILSCALE_AUTHKEY=tskey-auth-...
```

Never start the stack until `/mnt/nvme` is mounted. PlaneLab refuses to create
the configured paths when that mount is absent.

## Remux sources and modes

Configure local Remux sources below the read-only `/media` mount:

- movies: `/media/offline/movies`
- series: `/media/offline/shows`
- YouTube: `/media/YouTube`

Configure Stremio add-ons and online catalogs in Remux itself. Remux handles
its own streaming and transcoding choices; PlaneLab no longer writes encoding
settings through an API.

PlaneLab modes control which containers run and apply a catalog filter to
every Remux user:

| Mode | Running services | Visible Remux catalogs |
|---|---|---|
| `home` | Remux, Traefik, and optional Tailscale | Online/non-local catalogs |
| `prepare` | Full stack, including download and request services | All catalogs |
| `travel` | Remux, Traefik, optional Tailscale, and the configured hotspot | Local catalogs |

```bash
./planelab mode home
./planelab mode prepare
./planelab mode travel
./planelab mode status
```

Create a key under **Remux Dashboard -> API Keys**, then enter it through
**Operating mode -> Configure Remux API key** or add it to `.env`:

```dotenv
REMUX_URL=http://localhost:8096
REMUX_API_KEY=your-generated-key
REMUX_LOCAL_ADDON_KINDS=opendal-local
```

PlaneLab discovers enabled catalogs, treats Remux's `opendal-local` addon as
offline/local, and writes a native `catalog not_in` rule to each user's
`Policy.FilterRules`. Remux applies that rule to content queries and omits
catalog containers that become empty. `REMUX_LOCAL_ADDON_KINDS` can contain a
comma-separated list if another addon kind should count as local.

PlaneLab owns catalog-type rules for these users: it replaces existing catalog
rules on each mode switch while preserving non-catalog rules such as genre or
parental filters. It refuses an existing top-level `any` filter when safely
combining it is impossible. If one user update fails, already updated users are
rolled back to their original policies.

Background containers receive restart policy `no` in `home` and `travel`, so
a Docker or machine restart does not bring download services back. `prepare`
restores `unless-stopped` and starts the full stack.

## GPU passthrough

PlaneLab only detects and exposes a supported Linux DRI render device to
Remux. Remux decides whether and how to use that device for transcoding.

- Intel and AMD DRI render devices on non-Pi Linux are passed through.
- macOS Docker and Raspberry Pi leave passthrough disabled.
- unsupported or missing devices leave passthrough disabled.
- set `PLANELAB_GPU_PASSTHROUGH=off` to force it off.

Detection writes the machine-local `compose.gpu.yml`; this generated file is
not backed up and is regenerated on setup, restore, start, restart, and mode
changes.

```bash
./planelab gpu status
./planelab gpu configure
```

There is no encoder setter. The Remux API key is used only for per-user catalog
visibility during mode changes.

## Remote access with Tailscale

On Linux, PlaneLab runs Tailscale in the host network namespace when
`compose.tailscale.yml` is part of `COMPOSE_FILE`. Create a one-off auth key in
the Tailscale admin console and configure `.env` as shown above.

Start and inspect it with:

```bash
./planelab start
docker compose exec tailscale tailscale status
```

The startup wrapper waits for authentication, applies
`tailscale/serve.json`, and advertises the node for `svc:jellyfin` after every
container restart. That compatibility-named service forwards `tcp:8096` to
Remux.

Create `svc:jellyfin` with endpoint `tcp:8096` in the Tailscale Services page.
The PlaneLab node needs a tag-based identity, for example
`tag:media-server`. Apply the tag on the Machines page or use a tagged auth
key, then approve PlaneLab as a Service host.

With MagicDNS enabled, the direct tailnet addresses are:

| Service | Tailnet URL |
|---|---:|
| Remux | `http://planelab:8096` |
| Seerr | `http://planelab:5055` |
| Sonarr | `http://planelab:8989` |
| Radarr | `http://planelab:7878` |
| Prowlarr | `http://planelab:9696` |
| SABnzbd | `http://planelab:8080` |
| RDTClient | `http://planelab:6500` |
| Youtarr | `http://planelab:3087` |

Without MagicDNS, replace `planelab` with the `100.x.y.z` address reported by:

```bash
docker compose exec tailscale tailscale ip -4
```

Tailscale stays running in every PlaneLab mode. Its identity lives in the
external `planelab_tailscale_state` volume and is excluded from transferable
backups, preventing restored machines from claiming the same node identity.
On macOS, omit `compose.tailscale.yml` and use the native Tailscale app.

## PlaneLab hotspot

On Raspberry Pi OS with NetworkManager:

```bash
cp hotspot.env.example hotspot.env
nano hotspot.env
./hotspot.sh install
```

Run installation from a local console or Ethernet SSH session. The script
refuses to disconnect the active Wi-Fi SSH path unless `--force` is supplied.
The default hotspot uses address `10.42.0.1`, a hidden 5 GHz SSID, and
WPA2/WPA3 Personal transition mode. No uplink is needed for local Remux
playback.

Useful commands:

```bash
./hotspot.sh status
./hotspot.sh up
./hotspot.sh down
./hotspot.sh uplink "WorkshopWiFi"
./hotspot.sh ethernet smart
./hotspot.sh ethernet auto
./hotspot.sh ethernet shared
```

`smart` first requests a normal DHCP uplink and switches to shared Ethernet if
no usable IPv4 gateway appears. Shared Ethernet uses `10.42.1.1/24`. The Wi-Fi
hotspot remains on `10.42.0.1/24`.

## Application paths

Use container paths when configuring applications:

- Sonarr root: `/media/offline/shows`
- Radarr root: `/media/offline/movies`
- SABnzbd temporary folder: `/downloads/incomplete`
- SABnzbd completed folder: `/downloads/complete`
- RDTClient download/mapped path: `/downloads`
- Remux local source root: `/media`
- Youtarr internal data path: `/usr/src/app/data`

Containers address one another by Compose service name, for example
`http://remux:3000`, `http://sonarr:8989`, `http://radarr:7878`, and
`http://sabnzbd:8080`.

## UsenetCrawler compatibility proxy

UsenetCrawler's general search can return releases omitted by structured TV
search. PlaneLab includes a local proxy:

```text
Sonarr -> Prowlarr -> usenet-proxy -> UsenetCrawler -> SABnzbd
```

In Prowlarr, add a Generic Newznab indexer using URL
`http://usenet-proxy:8080`, API path `/api`, and your UsenetCrawler API key.
Disable the old direct UsenetCrawler entry so queries are not duplicated.

## Backup and restore

```bash
./backup.sh
./restore.sh backups/20260728T120000Z
```

Backups briefly stop the managed stack and archive every application volume,
including `planelab_remux_data`. Media, downloads, GPU configuration, and the
Tailscale machine identity are excluded. The private `.env` and backup data
contain credentials and must be stored securely outside Git.

Restore preserves machine-specific paths and network settings when a target
already has `.env`. It refuses non-empty volumes unless `--replace` is used.
That option replaces matching application volumes but never touches media or
download directories.

## Useful checks

```bash
docker compose config
docker compose ps
docker compose logs --tail=100
docker compose exec remux ls -la /media/offline
docker compose exec sonarr ls -la /media/offline/shows
docker compose exec radarr ls -la /media/offline/movies
docker compose exec sabnzbd ls -la /downloads
```

Application volumes are declared `external: true`, so Compose reuses volumes
created by `prepare.sh` or restore. Even `docker compose down -v` does not
delete them; external volumes require an explicit `docker volume rm` command.

Remux is still early-stage software and may contain rough edges or breaking
changes. Its upstream project and current container example are documented at
[lostb1t/remux](https://github.com/lostb1t/remux).
