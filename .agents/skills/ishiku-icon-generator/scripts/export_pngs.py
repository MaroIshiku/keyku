#!/usr/bin/env python3
"""Directly downscale a validated ishiku RGBA source into standard PNG sizes."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from validate_icon import validate_png


DEFAULT_SIZES = (1024, 512, 256, 192, 180, 128, 64, 32)


def export(source: Path, output_directory: Path, sizes: list[int] | tuple[int, ...], force: bool = False) -> dict:
    source_result = validate_png(source)
    if not source_result["valid"]:
        return {"status": "IMPLEMENTED_BUT_NOT_VERIFIED", "source": source_result, "outputs": []}

    unique_sizes = list(dict.fromkeys(sizes))
    source_size = source_result["details"]["dimensions"][0]
    oversized = [size for size in unique_sizes if size > source_size]
    if oversized:
        return {
            "status": "IMPLEMENTED_BUT_NOT_VERIFIED",
            "source": source_result,
            "outputs": [],
            "errors": [f"refusing to upscale source; requested sizes exceed {source_size}: {oversized}"],
        }

    targets = [output_directory / f"icon-{size}.png" for size in unique_sizes]
    source_resolved = source.resolve()
    existing = [str(target) for target in targets if target.exists() and target.resolve() != source_resolved]
    if existing and not force:
        return {"status": "IMPLEMENTED_BUT_NOT_VERIFIED", "source": source_result, "outputs": [], "errors": [f"refusing to overwrite existing exports: {', '.join(existing)}"]}
    output_directory.mkdir(parents=True, exist_ok=True)
    outputs = []
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
        for size, target in zip(unique_sizes, targets, strict=True):
            if target.resolve() != source_resolved:
                image.resize((size, size), Image.Resampling.LANCZOS).save(target, format="PNG", optimize=True)
            outputs.append(validate_png(target))
    valid = all(output["valid"] for output in outputs)
    return {
        "status": "VERIFIED" if valid else "IMPLEMENTED_BUT_NOT_VERIFIED",
        "operation": "direct-lanczos-downscale-no-crop-no-mask-change",
        "source": source_result,
        "outputs": outputs,
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ishiku-icon-exporter-") as directory:
        root = Path(directory)
        source = root / "icon-source.png"
        image = Image.new("RGBA", (1254, 1254), (0, 0, 0, 0))
        ImageDraw.Draw(image).rounded_rectangle((40, 40, 1213, 1213), radius=260, fill=(42, 157, 132, 255))
        image.save(source)
        report = export(source, root / "exports", (1024, 192, 64, 32))
        assert report["status"] == "VERIFIED"
        assert report["operation"] == "direct-lanczos-downscale-no-crop-no-mask-change"
        assert [item["details"]["dimensions"] for item in report["outputs"]] == [[1024, 1024], [192, 192], [64, 64], [32, 32]]
        with Image.open(source) as opened, Image.open(root / "exports" / "icon-64.png") as exported:
            expected = opened.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
            assert ImageChops.difference(expected, exported.convert("RGBA")).getbbox() is None
        blocked = export(source, root / "exports", (192, 64, 32))
        assert blocked["status"] == "IMPLEMENTED_BUT_NOT_VERIFIED"
        assert blocked["errors"]
        assert export(source, root / "exports", (192, 64, 32), force=True)["status"] == "VERIFIED"
        assert export(source, root / "exports", (2048,), force=True)["status"] == "IMPLEMENTED_BUT_NOT_VERIFIED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("output_directory", nargs="?", type=Path)
    parser.add_argument("--sizes", nargs="+", type=int, default=DEFAULT_SIZES)
    parser.add_argument("--force", action="store_true", help="overwrite existing derived PNG exports")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print(json.dumps({"status": "VERIFIED", "self_test": "passed"}, indent=2))
        return 0
    if args.source is None or args.output_directory is None:
        parser.error("provide a source PNG and output directory")
    if any(size <= 0 for size in args.sizes):
        parser.error("sizes must be positive integers")
    report = export(args.source, args.output_directory, args.sizes, force=args.force)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
