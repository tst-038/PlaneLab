# PlaneLab

Offline-first Jellyfin provisioning stack for a Raspberry Pi or a macOS test
machine. Use it only with media and sources you are authorized to access.

## Services

| Service | URL | Purpose |
|---|---:|---|
| Jellyfin | `:8096` | Offline playback |
| Seerr | `:5055` | Requests |
| Sonarr | `:8989` | TV management |
| Radarr | `:7878` | Movie management |
| Prowlarr | `:9696` | Indexer management |
| SABnzbd | `:8080` | TorBox News/Usenet client |
| RDTClient | `:6500` | TorBox torrent adapter |
| Youtarr | `:3087` | YouTube library provisioning |

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

## Internal paths

Configure applications with container paths, never host paths:

- Sonarr root folder: `/media/shows`
- Radarr root folder: `/media/movies`
- SABnzbd temporary folder: `/downloads/incomplete`
- SABnzbd completed folder: `/downloads/complete`
- RDTClient download and mapped paths: `/downloads`

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
git add compose.yml .env.example .gitignore prepare.sh backup.sh restore.sh README.md
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
