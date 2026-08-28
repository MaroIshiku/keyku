# Raster source generation

Read this reference when creating or regenerating an ishiku raster icon with the built-in image generator. The goal is one approved canonical RGBA source that can be downscaled without redesign or cleanup.

## Canonical source contract

- Produce exactly one icon on a square canvas at the image generator's native resolution; require at least 1024 × 1024 pixels.
- Save the untouched accepted result as `icon-source.png` in RGBA mode. Do not crop, stretch, recenter, replace its tile, redraw its rim, synthesize a new alpha mask, or remove its small transparent safety margin.
- Keep real transparency outside the tile. Never bake in white, checkerboard, magenta, or another preview background.
- A transparent safety margin is intentional and must be no more than 8% of the canvas on each side when measured at alpha ≥ 32.
- Rounded outer corners remain transparent. Antialiased partial alpha at tile edges is expected.
- Regenerate the source when its composition, alpha, background, or family style is wrong. Do not compound image-generation errors with invasive postprocessing.

## Fixed family style lock

Keep the following style wording unchanged across a batch. Change only the app purpose, utility symbol, category name, and category colors.

- Cohesive matte ceramic/clay soft 3D bas-relief app icon.
- Straight-on orthographic view with no camera tilt, perspective, or rotation.
- One centered rounded-squircle tile with a small transparent safety margin.
- Smooth category-colored tile with only subtle tonal shading and one thin inset tonal rim; no waves, blobs, texture, scene, or decorative background motif.
- One large, immediately recognizable raised warm off-white utility pictogram and at most one compact darker category-colored badge or action cue.
- Consistent rounded geometry, extrusion depth, pictogram thickness, upper-left soft studio lighting, internal ambient occlusion, and restrained internal shadow.
- Matte surfaces only: no gloss, glass, chrome, mirror reflection, lens flare, hard cast shadow, or outer halo.
- No text, letters, app name, wordmark, mascot, emoji, UI screenshot, or third-party brand mark.

## Recognition categories

Use one category consistently. The first tone is the tile color and the last tone is the dark accent.

| Category | Use | Tile | Accent | Current apps |
| --- | --- | --- | --- | --- |
| Files & Transfers | downloading, receiving, converting, file movement | `#8EE8CE` | `#006C54` | Dropiku, Pulliku, Seediku, Vertiku |
| Networking & Security | DNS, monitoring, VPN, secure network access | `#A9CFFF` | `#3169C6` | Dyniku, Pingiku, Tuniku |
| Private & Personal | identity, personal dashboard, private travel data | `#CDBDFF` | `#5B3FB4` | Meiku, Nestiku, Ryoiku |
| Libraries & Collections | books, keys, games, owned collections | `#FFD37A` | `#8A5100` | Libiku, Keyku, Playiku |
| System & Administration | neutral infrastructure without a better category | `#C3CEDB` | `#3E4754` | fallback only |

Color is category recognition, not application-theme configuration.

## Prompt template

Use this template as one prompt. Do not add legacy icon references for a fresh family batch. When extending an approved batch, compare the output visually with its accepted sources but retain this exact style lock.

```text
Create exactly one logo-brand app icon for {APP_NAME}, a self-hosted utility for {SHORT_PURPOSE}.

UTILITY SYMBOL
Show {PRIMARY_SYMBOL}. Optionally add only this compact contextual cue: {BADGE_OR_NONE}. The meaning must remain recognizable at 32 px. Do not include any text or third-party brand mark.

CATEGORY
{CATEGORY_NAME}. Use {TILE_COLOR} for the rounded-squircle tile, a warm off-white raised pictogram, and {ACCENT_COLOR} only for the darker accent or badge.

FIXED FAMILY STYLE — follow literally
Cohesive matte ceramic/clay soft 3D bas-relief app icon. Straight-on orthographic view with no camera tilt, perspective, or rotation. One centered rounded-squircle tile with a small transparent safety margin. Smooth category-colored tile with only subtle tonal shading and one thin inset tonal rim; no waves, blobs, texture, scene, or decorative background motif. One large, immediately recognizable raised warm off-white utility pictogram and at most one compact darker category-colored badge or action cue. Consistent rounded geometry, extrusion depth, pictogram thickness, upper-left soft studio lighting, internal ambient occlusion, and restrained internal shadow. Matte surfaces only: no gloss, glass, chrome, mirror reflection, lens flare, hard cast shadow, or outer halo.

OUTPUT
Square 1:1 PNG at native generator resolution, at least 1024 × 1024, RGBA with true transparent pixels outside the tile. Leave a small, even transparent safety margin around the complete tile. No checkerboard, white canvas, colored fallback canvas, crop marks, icon sheet, mockup, device frame, text, letters, app name, wordmark, mascot, emoji, UI screenshot, or external background.
```

## Acceptance and export

1. Confirm square PNG, RGBA, real transparency, safe margin, transparent corners, category palette, one-symbol composition, and style-lock fidelity.
2. Inspect the source itself before any transformation. If it is accepted, preserve it byte-for-byte as `icon-source.png`.
3. Run `scripts/export_pngs.py icon-source.png <output-directory>`. It directly downsamples with Lanczos to 1024, 512, 256, 192, 180, 128, 64, and 32 px and performs no crop or mask change.
4. Validate every output and visually inspect 64 px and 32 px on both light and dark solid backgrounds.
5. Keep generation rationale and category metadata in `icon-notes.yaml`; never copy the full central design contract into an app repository.
