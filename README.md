# Ish KeyVault

Self-hosted Steam key vault for Docker and ZimaOS. The app uses a small Python/Flask web UI, reads and writes one shared `data/keys.csv`, is protected by login, and requires admin approval for every user after the first account.

## Features

- One shared Steam key list for all approved users
- Login, registration, and admin approval
- Password reset requests from the login screen, completed only by an admin in Notifications
- Public share links per key without login, protected by cryptic HMAC tokens
- Reveal, copy, share, redeem, and search keys on Steam or SteamDB
- Reactivation requests for used keys
- Admin key management: create, edit, delete, and reactivate entries
- Admin settings with bulk maintenance actions
- Light and dark themes, transparent KeyVault logo, and favicon

## Structure

```text
ish-keyvault/
|-- docker-compose.yml
|-- python/
|   |-- app.py
|   |-- Dockerfile
|   `-- requirements.txt
|-- public/
|   |-- index.html
|   |-- script.js
|   |-- style.css
|   |-- share.html
|   |-- share.js
|   |-- logo.svg
|   |-- favicon.svg
|   |-- favicon.png
|   `-- icon-512.png
`-- data/
    `-- keys.csv
```

## CSV Format

`data/keys.csv` remains the persistent key list:

```csv
Game,Key,RedeemedAt,addedAt
Hollow Knight,AAAAA-BBBBB-CCCCC,,2026-01-01T00:00:00.000Z
Dead Cells,DDDDD-EEEEE-FFFFF,,
```

`Game` and `Key` are required. Leave `RedeemedAt` empty when a key is free. The app sets the timestamp when a key is redeemed. `addedAt` is optional.

## ZimaOS / Docker

The Compose file is optimized for ZimaOS:

- no local build on the ZimaOS host
- no relative bind paths
- persistent app data under `/DATA/AppData/ish-keyvault/data`
- image pulled directly from GHCR

```bash
mkdir -p /DATA/AppData/ish-keyvault/data
docker compose pull
docker compose up -d
```

Open the app at:

```text
http://<zima-ip>:8080
```

If you run the app behind an HTTPS host or reverse proxy, forward it to `http://<zima-ip>:8080`. The app respects `X-Forwarded-Proto`, so secure cookies work correctly behind HTTPS.

Set `PUBLIC_BASE_URL` in `docker-compose.yml` to your external HTTPS URL when generated share links should always use the public host:

```yaml
- PUBLIC_BASE_URL=https://keys.example.com
```

The Compose file uses this prebuilt GHCR image:

```text
ghcr.io/maroishiku/ish-keyvault:latest
```

## First Login

1. Open the app.
2. Register.
3. The first user automatically becomes an admin.
4. Every later registration appears behind the bell icon and must be approved by an admin.

The app creates these persistent files:

- `data/users.json`
- `data/reactivation-requests.json`
- `data/password-reset-requests.json`
- `data/session-secret.txt`

Back up those files together with `data/keys.csv`.

## Security

- Passwords are stored with PBKDF2/SHA-256, per-user salt, and a high iteration count.
- Existing user files from the Node version remain compatible.
- Sessions use signed HttpOnly cookies.
- Plaintext keys are not returned by the normal list API.
- Share links are public, but cryptic and not guessable because they use HMAC tokens.
- CSV and JSON files are written atomically to stay stable across restarts.

## Maintenance

```bash
docker compose logs -f
docker compose restart
docker compose down
```

Admins can open the gear icon in the app to:

- delete all used keys
- reactivate all used keys
- clear resolved requests
- review quick metrics for keys, users, and requests
