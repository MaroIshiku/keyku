# Keyku - Key Vault

Self-hosted Steam key vault for Docker and ZimaOS.

## Short Description

Keyku manages a shared Steam key list with login, admin tooling, public share links, and reactivation requests. The app uses a small Flask backend, a static vanilla frontend, and persistent files in the mounted data directory.

## Part of the ishiku Family

Keyku follows the shared Pixel Soft Utility design system for ishiku apps: calm, rounded, practical, and built for self-hosting. Themes, app shell, setup behavior, and admin information surfaces are consistent across the app family.

The shared themes are Lavender, Mint, Sky, Amber, Rose, and Graphite. System, light, and dark modes are supported.

## Features

- Shared Steam key vault with search, status filters, and sorting
- Login with signed HttpOnly session cookies
- First-run setup for the initial admin account
- Simple setup secret via Docker Compose environment variable
- Optional hardened setup secret via Docker secret file
- Admin tools for keys, users, requests, and maintenance
- Public per-key share links protected with HMAC tokens
- Reveal, copy, redeem, Steam search, and SteamDB actions
- Reactivation requests for already used keys
- Password reset requests handled by admins
- Health and readiness endpoints for container operation

## Tech Stack

- Python 3.12
- Flask
- Gunicorn
- Vanilla HTML, CSS, and JavaScript
- Pixel Soft Utility design system
- Docker / Docker Compose

## Installation

### Docker Compose

For ZimaOS, the main Compose file uses absolute host paths:

```bash
mkdir -p /DATA/AppData/keyku/data
docker compose pull
docker compose up -d
```

Before the first start, edit `docker-compose.yml` and replace:

```yaml
- ISHIKU_SETUP_SECRET=
```

with a long random setup secret of your own.

The app is available at:

```text
http://<server-ip>:8186
```

### First Start

On first start, Keyku checks whether an admin account exists. If not, the setup window opens immediately. If no setup secret is configured, the app stays closed and shows the missing configuration key.

### Create the Admin Account

Enter the setup secret, display name, admin username, and admin password in the setup window. After the first admin is created, public registration is closed. Additional accounts are created by admins inside the app.

## Configuration

### Environment Variables

| Variable | Description |
| --- | --- |
| `TZ` | Time zone, recommended `Europe/Berlin` |
| `ISHIKU_APP_URL` | Public URL behind a reverse proxy, used for share links |
| `ISHIKU_BASE_PATH` | Optional base path, default `/` |
| `ISHIKU_DATA_DIR` | Persistent data directory in the container, default `/data` |
| `ISHIKU_LOG_LEVEL` | Log level, default `info` |
| `ISHIKU_TRUST_PROXY` | Set to `true` when running behind a trusted reverse proxy |
| `ISHIKU_SETUP_SECRET` | Simple first-run setup secret for Docker Compose |
| `ISHIKU_SETUP_SECRET_FILE` | Optional path to a mounted Docker secret file |
| `PORT` | Internal HTTP port, default `3000` |

### Docker Secrets

The simple path is `ISHIKU_SETUP_SECRET` in Compose. If you prefer a mounted Docker secret, use:

```yaml
secrets:
  ishiku_setup_secret:
    file: ./secrets/setup_secret.txt
```

and set:

```yaml
ISHIKU_SETUP_SECRET_FILE: /run/secrets/ishiku_setup_secret
```

The setup secret is only used for the first admin setup and is not stored in the app database.

### Persistent Data

Keyku creates these files in the data directory:

- `keys.csv`
- `users.json`
- `reactivation-requests.json`
- `password-reset-requests.json`
- `session-secret.txt`
- `setup-state.json`

Back up these files together.

## Security

- The setup secret is only used for first-run registration.
- The admin password must not match the setup secret.
- Passwords are stored as salted PBKDF2/SHA-256 hashes.
- Public registration is closed after the first admin account.
- Sessions use signed HttpOnly cookies with SameSite=Lax.
- Normal key list responses never include plaintext keys.
- Share links are public, cryptic, and HMAC-based.
- API responses use `Cache-Control: no-store`.
- Security headers include content type protection, referrer policy, permissions policy, frame protection, and a restrictive Content Security Policy.
- Do not commit real secrets, `.env` files, logs, or runtime data.

## Updates and Backup

```bash
docker compose pull
docker compose up -d
docker compose logs -f
```

Back up the complete persistent data directory before destructive maintenance actions.

## Development

Frontend files are static in `public/`; the backend is in `python/app.py`.

```bash
docker build -f python/Dockerfile -t keyku:local .
docker run --rm -p 3000:3000 \
  -e ISHIKU_SETUP_SECRET=replace-with-a-long-random-setup-secret \
  -v keyku-data:/data \
  keyku:local
```

## Created with ChatGPT Codex

This project was implemented and updated with assistance from ChatGPT Codex. Codex does not own or maintain the project.

## Status and License

Status: active development.

No license file is currently included.
