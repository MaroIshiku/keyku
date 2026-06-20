# Ish KeyVault

Self-hosted Steam-Key-Vault fuer Docker/ZimaOS. Die App nutzt eine kleine Python/Flask-WebUI, liest und schreibt eine gemeinsame `data/keys.csv`, ist per Login geschuetzt und erlaubt neue Nutzer erst nach Admin-Freigabe.

## Funktionen

- Gemeinsame Steam-Key-Liste fuer alle Nutzer
- Login, Registrierung und Admin-Approval
- Passwortreset-Anfrage im Login, neues Passwort nur durch Admin in Notifications
- Share-Link pro Key ohne Login, kryptisch per HMAC-Token
- Key anzeigen, kopieren, teilen, einloesen, Steam/SteamDB suchen
- Reaktivierungsanfragen fuer verbrauchte Keys
- Admin kann Keys anlegen, bearbeiten, loeschen und reaktivieren
- Light/Dark-Mode, transparentes KeyVault-Logo und Favicon

## Struktur

```text
ish-keyvault/
├── docker-compose.yml
├── nginx/
│   └── default.conf
├── python/
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
├── public/
│   ├── index.html
│   ├── script.js
│   ├── style.css
│   ├── share.html
│   ├── share.js
│   ├── logo.svg
│   ├── favicon.svg
│   ├── favicon.png
│   └── icon-512.png
└── data/
    └── keys.csv
```

## CSV-Format

`data/keys.csv` bleibt die persistente Key-Liste:

```csv
Game,Key,RedeemedAt,addedAt
Hollow Knight,AAAAA-BBBBB-CCCCC,,2026-01-01T00:00:00.000Z
Dead Cells,DDDDD-EEEEE-FFFFF,,
```

`Game` und `Key` muessen gesetzt sein. `RedeemedAt` leer lassen, wenn ein Key frei ist. Die App setzt den Zeitstempel beim Einloesen. `addedAt` ist optional.

## Start auf ZimaOS / Docker

```bash
cd /DATA/AppData/ish-keyvault
docker compose pull
docker compose up -d
```

Aufruf:

```text
http://<zima-ip>:8080
```

Wenn ein HTTPS-Host oder Reverse Proxy davor sitzt, leite ihn auf `http://<zima-ip>:8080` weiter. Nginx reicht `X-Forwarded-Proto` an Flask weiter, damit Secure-Cookies bei HTTPS korrekt funktionieren.

Das Compose-File nutzt das fertige GHCR-Image:

```text
ghcr.io/maroishiku/ish-keyvault:latest
```

## Erster Login

1. App oeffnen.
2. Registrieren.
3. Der allererste Nutzer wird automatisch Admin.
4. Alle weiteren Registrierungen erscheinen in der Glocke und muessen vom Admin angenommen werden.

Die App erzeugt persistent:

- `data/users.json`
- `data/reactivation-requests.json`
- `data/password-reset-requests.json`
- `data/session-secret.txt`

Diese Dateien zusammen mit `data/keys.csv` sichern.

## Sicherheit

- Passwoerter werden mit PBKDF2/SHA-256, Salt und hoher Iterationszahl gespeichert.
- Vorhandene Nutzerdateien aus der Node-Version bleiben kompatibel.
- Sessions laufen ueber signierte HttpOnly-Cookies.
- Klartext-Keys werden nicht in der normalen Listen-API ausgeliefert.
- Share-Links sind nicht login-geschuetzt, aber kryptisch per HMAC und nicht erratbar.
- Daten werden atomar geschrieben, damit CSV/JSON bei Neustarts stabil bleiben.

## Wartung

```bash
docker compose logs -f
docker compose restart
docker compose down
```
