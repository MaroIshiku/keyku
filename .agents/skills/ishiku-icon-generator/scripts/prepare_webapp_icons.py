#!/usr/bin/env python3
"""Prepare deterministic browser, PWA, and Apple icon assets from one RGBA source."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from PIL import Image, ImageColor, ImageDraw

from export_pngs import DEFAULT_SIZES, export
from validate_icon import validate_png


ALIAS_FILES = {
    "favicon-32.png": "icon-32.png",
    "apple-touch-icon.png": "icon-180.png",
}


def public_url(prefix: str, filename: str) -> str:
    normalized = "/" + prefix.strip("/") if prefix.strip("/") else ""
    return str(PurePosixPath(normalized or "/") / filename)


def prepare(
    source: Path,
    output_directory: Path,
    url_prefix: str,
    force: bool = False,
    maskable_background: str | None = None,
) -> dict:
    planned = [output_directory / f"icon-{size}.png" for size in DEFAULT_SIZES]
    planned.extend(output_directory / name for name in ALIAS_FILES)
    planned.extend((output_directory / "manifest-icons.json", output_directory / "head-icon-links.html"))
    if maskable_background:
        planned.append(output_directory / "icon-maskable-512.png")

    source_resolved = source.resolve()
    existing = [str(path) for path in planned if path.exists() and path.resolve() != source_resolved]
    if existing and not force:
        return {
            "status": "IMPLEMENTED_BUT_NOT_VERIFIED",
            "errors": [f"refusing to overwrite existing web assets: {', '.join(existing)}"],
        }

    export_report = export(source, output_directory, DEFAULT_SIZES, force=force)
    if export_report["status"] != "VERIFIED":
        return export_report

    output_directory.mkdir(parents=True, exist_ok=True)
    aliases = []
    for alias, original in ALIAS_FILES.items():
        target = output_directory / alias
        shutil.copyfile(output_directory / original, target)
        aliases.append(validate_png(target))

    manifest_icons = [
        {
            "src": public_url(url_prefix, "icon-192.png"),
            "sizes": "192x192",
            "type": "image/png",
            "purpose": "any",
        },
        {
            "src": public_url(url_prefix, "icon-512.png"),
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "any",
        },
    ]

    maskable_result = None
    if maskable_background:
        background = ImageColor.getrgb(maskable_background)
        with Image.open(output_directory / "icon-512.png") as opened:
            icon = opened.convert("RGBA")
        maskable = Image.new("RGBA", (512, 512), background + (255,))
        maskable.alpha_composite(icon)
        maskable_path = output_directory / "icon-maskable-512.png"
        maskable.save(maskable_path, "PNG", optimize=True)
        maskable_result = validate_png(maskable_path, profile="maskable")
        manifest_icons.append(
            {
                "src": public_url(url_prefix, maskable_path.name),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            }
        )

    manifest_path = output_directory / "manifest-icons.json"
    manifest_path.write_text(json.dumps(manifest_icons, indent=2) + "\n", encoding="utf-8")
    links = [
        f'<link rel="icon" type="image/png" sizes="32x32" href="{public_url(url_prefix, "favicon-32.png")}">',
        f'<link rel="apple-touch-icon" sizes="180x180" href="{public_url(url_prefix, "apple-touch-icon.png")}">',
    ]
    links_path = output_directory / "head-icon-links.html"
    links_path.write_text("\n".join(links) + "\n", encoding="utf-8")

    valid = all(item["valid"] for item in aliases) and (maskable_result is None or maskable_result["valid"])
    return {
        "status": "VERIFIED" if valid else "IMPLEMENTED_BUT_NOT_VERIFIED",
        "source_export": export_report,
        "aliases": aliases,
        "maskable": maskable_result,
        "manifest_fragment": str(manifest_path),
        "head_links_fragment": str(links_path),
        "integration_required": [
            "merge manifest-icons.json into the app web manifest",
            "merge head-icon-links.html into the HTML head",
            "add the files to a service-worker precache when the app has one",
            "update app-specific logo metadata without changing established public URLs unnecessarily",
        ],
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ishiku-web-icons-") as directory:
        root = Path(directory)
        source = root / "icon-source.png"
        image = Image.new("RGBA", (1254, 1254), (0, 0, 0, 0))
        ImageDraw.Draw(image).rounded_rectangle((40, 40, 1213, 1213), radius=260, fill=(142, 232, 206, 255))
        image.save(source)
        output = root / "public" / "icons"
        report = prepare(source, output, "/icons", maskable_background="#8EE8CE")
        assert report["status"] == "VERIFIED"
        assert (output / "icon-192.png").is_file()
        assert (output / "icon-512.png").is_file()
        assert (output / "apple-touch-icon.png").is_file()
        assert (output / "favicon-32.png").is_file()
        assert (output / "icon-maskable-512.png").is_file()
        manifest = json.loads((output / "manifest-icons.json").read_text(encoding="utf-8"))
        assert [item["purpose"] for item in manifest] == ["any", "any", "maskable"]
        assert prepare(source, output, "/icons")["status"] == "IMPLEMENTED_BUT_NOT_VERIFIED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("output_directory", nargs="?", type=Path)
    parser.add_argument("--url-prefix", default="/icons")
    parser.add_argument("--maskable-background", help="opaque CSS hex color for an optional maskable PWA asset")
    parser.add_argument("--force", action="store_true", help="overwrite existing generated web assets")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print(json.dumps({"status": "VERIFIED", "self_test": "passed"}, indent=2))
        return 0
    if args.source is None or args.output_directory is None:
        parser.error("provide a source PNG and web asset output directory")
    report = prepare(
        args.source,
        args.output_directory,
        args.url_prefix,
        force=args.force,
        maskable_background=args.maskable_background,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
