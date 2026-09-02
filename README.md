# Keyku - Key Vault

Self-hosted Steam key vault for Docker and ZimaOS.

## Short Description

Keyku manages a shared Steam key list with login, admin tooling, public share links, and reactivation requests. The app uses a small Flask backend, a static vanilla frontend, and persistent files in the mounted data directory.

## Part of the ishiku Family

Keyku follows the shared Pixel Soft Utility design system for ishiku apps: calm, rounded, practical, and built for self-hosting. Themes, app shell, setup behavior, and admin information surfaces are consistent across the app family.

The shared themes are Lavender, Mint, Sky, Amber, Rose, and Graphite. System, light, and dark modes are supported.

## Features

- Shared Steam key vault with search, status filters, and sorting
- Login with revocable server-side sessions, protected HttpOnly cookies, and CSRF validation
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

- Python 3.14
- Flask
- Gunicorn
- Vanilla HTML, CSS, and JavaScript
- Pixel Soft Utility design system
- Docker / Docker Compose

## Installation

### Docker Compose

For ZimaOS, the main Compose file uses absolute host paths:

```bash
sudo install -d -m 0750 -o 10001 -g 10001 /DATA/AppData/keyku/data
docker compose pull
docker compose up -d
```

The Compose delivery includes a bounded, network-disabled one-shot initializer. It prepares a newly created or legacy `/data` bind mount for UID/GID `10001`, then exits before the non-root Keyku service starts. Do not remove the `keyku-init` service or its `depends_on` gate.

Before the first start, edit `docker-compose.yml` and replace:

```yaml
- ISHIKU_SETUP_SECRET=
```

with a random setup secret of at least 32 characters.

The app is available at:

```text
http://<server-ip>:65005
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
| `ISHIKU_DATA_DIR` | Persistent data directory in the container, default `/data` |
| `ISHIKU_TRUST_PROXY` | Set to `true` when running behind a trusted reverse proxy |
| `ISHIKU_COOKIE_SECURE` | `auto` enables secure cookies for HTTPS; set explicitly only for a documented deployment need |
| `ISHIKU_SETUP_SECRET` | First-run setup secret of at least 32 characters for Docker Compose |
| `ISHIKU_SETUP_SECRET_FILE` | Optional file containing a first-run setup secret of at least 32 characters |
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
- `sessions.json`
- `audit.jsonl`
- `setup-state.json`

Back up these files together.

The container runs as UID/GID `10001`. When using a bind mount outside the supplied ZimaOS path, create it with the same ownership before starting Keyku. Rootless Podman users can apply the equivalent ownership through `podman unshare chown 10001:10001 <data-directory>`.

## Security

- The setup secret is only used for first-run registration.
- The admin password must not match the setup secret.
- Passwords are stored with Argon2id; legacy PBKDF2 hashes are upgraded after a successful sign-in.
- Public registration is closed after the first admin account.
- Sessions are server-side, revocable, rotated after authentication and password changes, idle- and absolute-time-limited, and protected by HttpOnly/SameSite cookies plus CSRF tokens.
- Sign-in and setup attempts are rate-limited without permanent account lockout.
- Normal key list responses never include plaintext keys.
- Share links are public, cryptic, and HMAC-based.
- API responses use `Cache-Control: no-store`.
- Error responses expose the stable `code`, `message`, and `requestId` envelope while retaining the legacy `error` field for older clients.
- Security headers include content type protection, referrer policy, permissions policy, frame protection, and a restrictive Content Security Policy.
- Do not commit real secrets, `.env` files, logs, or runtime data.

## Updates and Backup

Before every update, stop Keyku and copy the complete persistent directory. Version 0.3.0 and later upgrade legacy PBKDF2 password hashes to Argon2id after a successful sign-in, so a rollback to 0.2.5 must restore the matching pre-upgrade data backup as well as the older image. Version 0.3.1 adds automatic permission preparation for both root-owned 0.2.5 data and fresh ZimaOS bind directories while keeping the web service non-root. Version 0.3.2 keeps that data format unchanged; existing completed installations continue to start even if an old setup-secret value was shorter than the new first-run minimum. Versions 0.3.3 and 0.3.4 make all resource declarations compatible with ZimaOS Compose normalization, including its automatic 256 MB service reservations, without changing persistent data.

```bash
docker compose stop
sudo cp -a /DATA/AppData/keyku/data /DATA/AppData/keyku/data-backup-$(date +%Y%m%d-%H%M%S)
docker compose pull
docker compose up -d
docker compose logs -f
```

To roll back, stop Keyku, restore the complete pre-upgrade data directory, set the Compose image to the previous immutable version, and start it again. Never combine a newer data directory with an older application image.

## Development

Frontend files are static in `public/`; the backend is in `python/app.py`.

Run the complete clone-local gate with Node.js 24, Python 3.14, and Docker available:

```bash
node .ishiku/kit/scripts/verify-app . --full
```

```bash
docker build -t keyku:local .
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
