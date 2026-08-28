---
name: ishiku-icon-generator
description: Create, regenerate, directly export, validate, and prepare ishiku-family RGBA app icons for browser, PWA, launcher, favicon, repository, and webapp use. Use automatically when an ishiku app needs a new or replacement icon, icon-size exports, or icon integration.
---

# ishiku icon generator

Create one visually consistent ishiku raster source, preserve it as the canonical artwork, derive every smaller PNG directly from it, and integrate only when authorized.

## Inputs and authority

For a target app, read its `workspace.yaml`, resolved repository `AGENTS.md`, `.ishiku/project.yaml`, AppSpec purpose, current icon assets, manifests, HTML entry points, service worker, and application icon metadata. Treat approved artwork as protected unless replacement is authorized.

At workspace scope, load `Root/.ishiku/design-system/contract.json` once and use `app_icons` as the specification. Do not copy the full contract into app repositories. In standalone clones, use `.ishiku/design-system.lock`, existing local family assets, and this skill.

If the user requests concepts or previews only, work in a temporary directory and do not update consumers.

## Required references

- For a new or regenerated ImageGen source, read [references/raster-source.md](references/raster-source.md) and use its fixed style lock, category palettes, prompt template, RGBA source contract, and direct-export rule.
- For browser/PWA staging or repository integration, read [references/webapp-import.md](references/webapp-import.md) and follow its asset roles, manifest semantics, cache handling, and integration checks.

## Workflow

1. Inventory the app purpose and every existing icon consumer: AppMark/header, HTML favicon and Apple links, Web App Manifest, service-worker cache, app metadata, Compose/catalog metadata, README, and release assets.
2. Infer one primary utility symbol and at most one small contextual cue. Use no text, wordmark, mascot, emoji, or third-party brand mark.
3. Classify the app into the central recognition category. Category color identifies the icon family; it never selects or hardcodes the application's UI theme.
4. For new family artwork, use built-in image generation with the fixed raster style lock. Generate one square icon per result without legacy image references unless the user explicitly requests reference-based editing.
5. Accept only a square PNG at least 1024 px in RGBA mode with real transparent corners, no preview canvas, and no more than 8% transparent safety margin per side at alpha ≥ 32. Preserve the accepted file unchanged as `icon-source.png`.
6. Do not crop, stretch, recenter, redraw, re-mask, re-background, or replace the accepted source rim. If the source is wrong, regenerate it. Derive all target sizes only with `scripts/export_pngs.py`, which performs direct Lanczos downsampling without crop or mask changes.
7. Visually inspect the source and the 64 px and 32 px exports on light and dark solid backgrounds. Confirm symbol recognition, family style, palette, transparency, and intact edges.
8. For webapp preparation, use `scripts/prepare_webapp_icons.py`. Treat its JSON and HTML outputs as merge fragments, not replacements for an existing manifest or document.
9. Update repository consumers only when integration is requested. Preserve established paths where compatible, refresh service-worker caches when URLs are cached, run the app's versioned checks, and refresh `.ishiku/design-system.lock` only through the supported binding command after intentional repository changes.

## Canonical files and sizes

The raster path uses `icon-source.png` as immutable accepted artwork and directly exports:

```text
icon-1024.png icon-512.png icon-256.png icon-192.png
icon-180.png icon-128.png icon-64.png icon-32.png
```

Keep `icon-notes.yaml` with app, purpose, symbol rationale, category, palette, generation path, native source dimensions, RGBA mode, safe-margin measurements, and consumer paths. SVG is optional and is used only when the approved source is genuinely vector artwork; never wrap the raster source in SVG.

## Commands

```text
python scripts/validate_icon.py <icon-source.png> [more standard PNG or SVG assets]
python scripts/validate_icon.py --profile maskable <icon-maskable-512.png>
python scripts/export_pngs.py <icon-source.png> <output-directory>
python scripts/prepare_webapp_icons.py <icon-source.png> <public-icon-directory> --url-prefix </public/url>
```

The scripts require Pillow and refuse destructive replacement unless `--force` is passed after explicit replacement authorization. Do not claim verification when dependencies are missing.

## Completion

Report the symbol rationale, category and palette, generation path, native source dimensions and mode, measured alpha margin, created paths and sizes, direct-export result, validator result, visual 64/32 inspection, prepared or updated consumers, and remaining deviations. Use `VERIFIED` only after deterministic validation and visual inspection pass for every delivered asset and, when integrated, the app's relevant versioned checks pass.
