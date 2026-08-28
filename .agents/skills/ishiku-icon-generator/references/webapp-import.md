# Webapp icon preparation and import

Read this reference when staging or integrating an accepted ishiku RGBA source into a web application.

## Standard raster set

Generate every size directly from `icon-source.png` with `scripts/export_pngs.py`:

| File | Intended use |
| --- | --- |
| `icon-source.png` | immutable accepted native source and provenance |
| `icon-1024.png` | repository/release master |
| `icon-512.png` | PWA, launcher, catalog, Docker or release metadata |
| `icon-256.png` | high-density UI or repository presentation |
| `icon-192.png` | PWA install icon |
| `icon-180.png` | Apple touch source |
| `icon-128.png` | desktop or compact launcher metadata |
| `icon-64.png` | UI and readability check |
| `icon-32.png` | browser favicon and readability check |

All PNG outputs remain square RGBA and preserve the source transparency and safety margin. Never crop or reconstruct smaller sizes independently.

## Deterministic staging

Use:

```text
python scripts/prepare_webapp_icons.py <icon-source.png> <public-icon-directory> --url-prefix </public/url>
```

The command creates the full raster set plus:

- `favicon-32.png`, an exact file copy of `icon-32.png`;
- `apple-touch-icon.png`, an exact file copy of `icon-180.png`;
- `manifest-icons.json`, a merge-ready Web App Manifest icon array;
- `head-icon-links.html`, merge-ready favicon and Apple touch `<link>` elements.

It refuses to overwrite existing assets unless replacement is explicitly authorized with `--force`.

## Manifest semantics

Transparent standard icons use `purpose: "any"`. Never label a transparent icon as `maskable`.

When an app actually consumes a maskable icon, pass the category tile color explicitly:

```text
python scripts/prepare_webapp_icons.py <icon-source.png> <public-icon-directory> --url-prefix </public/url> --maskable-background <#RRGGBB>
```

This additionally creates `icon-maskable-512.png` on a fully opaque category-colored RGBA canvas and adds a separate `purpose: "maskable"` entry. Keep the normal 192 and 512 entries with `purpose: "any"`.

## Repository integration

Staging files does not authorize integration. When integration is requested:

1. Preserve the application's established public asset directory and URLs where compatible; do not rename versioned legacy assets casually.
2. Merge `manifest-icons.json` into the existing manifest rather than replacing unrelated manifest fields.
3. Merge the generated `<link>` elements into every relevant HTML entry point and keep the existing manifest link.
4. Update application-specific icon metadata such as `app.manifest.json`, header/AppMark configuration, Compose catalog metadata, README, or release metadata only when each consumer exists and is in scope.
5. Add changed icon URLs to a service-worker precache when present. Change the cache version or asset fingerprint so installed clients do not retain stale icons.
6. Confirm served files have `image/png`, return HTTP 200, and resolve under the application's base path. Avoid root-relative URLs when the app supports a non-root base path unless that behavior is already established.
7. Do not claim `maskable` without the separately generated opaque asset. Do not use the Apple alias as a maskable asset.
8. Run the app's versioned tests/build, validate the final manifest, and inspect favicon, installed-PWA, AppMark, 64 px, and 32 px rendering on light and dark surfaces.

## Integration snippets

The generated manifest fragment has this baseline shape:

```json
[
  {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
  {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"}
]
```

The generated head links have this baseline shape:

```html
<link rel="icon" type="image/png" sizes="32x32" href="/icons/favicon-32.png">
<link rel="apple-touch-icon" sizes="180x180" href="/icons/apple-touch-icon.png">
```
