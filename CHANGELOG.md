# Changelog

All notable changes to Keyku are documented here. Releases use immutable semantic-version tags.

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
