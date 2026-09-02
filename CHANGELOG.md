# Changelog

All notable changes to Keyku are documented here. Releases use immutable semantic-version tags.

## 0.3.5 - 2026-09-02

- Fixed first-run registration and other protected mutations behind an HTTPS-terminating reverse proxy when `ISHIKU_TRUST_PROXY=false`: the canonical origin from `ISHIKU_APP_URL` is now accepted independently of the internal HTTP scheme.
- Kept origin protection fail-closed for malformed, cross-site, and lookalike-domain origins without enabling trust in client-supplied forwarding headers.

### Compatibility and rollback

- Persistent data, authentication, ports, resource limits, and the initializer lifecycle are unchanged.
- Existing 0.2.5 through 0.3.4 data remains compatible. Rollback to 0.3.4 requires only the previous image and Compose file.

## 0.3.4 - 2026-09-02

- Raised the bounded memory limits for both the initializer and web service to 256 MiB so ZimaOS's automatic 256 MB reservations cannot exceed their limits and invalidate the Compose project.
- Extended the Compose contract regression to normalize every service exactly like ZimaOS and to reproduce the Docker memory-reservation error reported against 0.3.3.

### Compatibility and rollback

- Persistent data, authentication, host port `65005`, and container port `3000` are unchanged.
- Existing 0.2.5 through 0.3.3 data remains compatible. Back up the complete data directory before updating; rollback to 0.3.3 requires only the previous image and Compose file.

## 0.3.3 - 2026-09-02

- Added matching Compose `deploy.resources.limits` for the one-shot initializer so ZimaOS does not inject conflicting CPU, memory, and PID limits that prevent the project from starting.
- Added an executable Compose contract regression that proves the published primary and alternative Compose files remain valid after ZimaOS-style normalization and reject the original conflicting resource state.

### Compatibility and rollback

- Persistent data, authentication, host port `65005`, and container port `3000` are unchanged.
- Existing 0.2.5, 0.3.0, 0.3.1, and 0.3.2 data remains compatible. Back up the complete data directory before updating; rollback to 0.3.2 requires only the previous image and Compose file.

## 0.3.2 - 2026-08-31

- Restored the current clone-local ishiku design verifier and removed stale synchronization-conflict artifacts from the embedded kit.
- Added reproducible Playwright and axe-core coverage for setup, authentication, vault behavior, sharing, keyboard focus, all themes and modes, and all required responsive viewports.
- Fixed the WCAG contrast of the available-key status in light mode.
- Added the stable API error envelope while retaining the legacy `error` response field for older clients.
- Enforced the 32-character first-run setup-secret minimum without blocking already configured legacy installations.
- Updated GitHub Actions to current immutable releases with full commit pins and Node.js 24-compatible action runtimes.
- Corrected PWA icon purpose metadata, an accessible label, declared upstreams, and unused configuration documentation.

### Compatibility and rollback

- The persistent file formats and host/container ports remain unchanged (`65005` to `3000`).
- Keyku 0.3.2 reads existing 0.2.5, 0.3.0, and 0.3.1 data; the supplied initializer still prepares legacy bind-mount ownership.
- Back up the complete data directory before upgrading. Rollback to 0.3.1 uses the same data, while rollback to 0.2.5 requires its matching pre-upgrade backup.

## 0.3.1 - 2026-08-29

- Added a bounded, network-disabled one-shot data initializer for fresh ZimaOS bind mounts and root-owned data created by Keyku 0.2.5.
- Kept the long-running Keyku service on UID/GID `10001`, with no capabilities, no privilege escalation, and a read-only root filesystem.
- Added executable fresh-install, legacy-data, ownership, restart, and PBKDF2-to-Argon2id migration coverage.

### Compatibility and rollback

- Existing data stays at `/DATA/AppData/keyku/data`; no manual ownership change is required when using the complete 0.3.1 Compose file.
- Back up the complete data directory before upgrading. Rolling back to 0.2.5 still requires the matching pre-upgrade data backup.

## 0.3.0 - 2026-08-28

- Updated the ishiku application kit and design binding.
- Added the approved amber Keyku icon across browser, PWA, launcher, catalog, and in-app consumers.
- Moved the published ZimaOS host port to the reserved port 65005 while preserving container port 3000.
- Upgraded to Python 3.14, Flask 3.1.3, Gunicorn 26.2.0, Argon2id password hashing, and current security-fixed runtime packages.
- Added revocable server-side sessions, CSRF and same-origin enforcement, rate limiting, audit events, legacy password-hash upgrades, and stricter secret handling.
- Hardened the container with a non-root user, read-only root filesystem, dropped capabilities, bounded resources, health checks, and persistent-data guidance.
- Added automated application, security, accessibility, multi-architecture, SBOM, provenance, and vulnerability verification.

### Compatibility and rollback

- Existing CSV key data and PBKDF2 accounts remain readable; PBKDF2 hashes upgrade after successful authentication.
- Back up the complete persistent data directory before upgrading.
- Rolling back to 0.2.5 requires restoring the matching pre-0.3.0 data backup before starting the old image.
