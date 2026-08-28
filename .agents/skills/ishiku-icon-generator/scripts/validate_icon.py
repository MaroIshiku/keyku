#!/usr/bin/env python3
"""Validate ishiku SVG and RGBA PNG app-icon invariants."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw


VISIBLE_ALPHA_THRESHOLD = 32
SAFE_MARGIN_MAX_RATIO = 0.08


def result(path: Path, kind: str, details: dict, errors: list[str]) -> dict:
    return {"path": str(path), "kind": kind, "valid": not errors, "details": details, "errors": errors}


def validate_png(path: Path, profile: str = "standard") -> dict:
    errors: list[str] = []
    with Image.open(path) as source:
        details = {"format": source.format, "mode": source.mode, "dimensions": [source.width, source.height]}
        details["profile"] = profile
        if source.format != "PNG":
            errors.append("asset must use PNG encoding")
        if source.width != source.height:
            errors.append("width and height must match")
        if source.mode != "RGBA":
            errors.append("PNG must use RGBA mode")
        if "A" not in source.getbands():
            return result(path, "png", details, errors)

        image = source.convert("RGBA")
        alpha = image.getchannel("A")
        bbox = alpha.getbbox()
        expected = (0, 0, image.width, image.height)
        details["alpha_bbox"] = list(bbox) if bbox else None
        details["alpha_extrema"] = list(alpha.getextrema())

        if profile == "maskable":
            details["expected_alpha_bbox"] = list(expected)
            if alpha.getextrema() != (255, 255):
                errors.append("maskable PNG must have a fully opaque RGBA canvas")
            return result(path, "png", details, errors)

        visible_alpha = alpha.point(lambda value: 255 if value >= VISIBLE_ALPHA_THRESHOLD else 0)
        visible_bbox = visible_alpha.getbbox()
        details["visible_alpha_threshold"] = VISIBLE_ALPHA_THRESHOLD
        details["visible_alpha_bbox"] = list(visible_bbox) if visible_bbox else None
        details["safe_margin_max_ratio"] = SAFE_MARGIN_MAX_RATIO
        if visible_bbox is None:
            errors.append("PNG must contain visible pixels")
        else:
            left, top, right, bottom = visible_bbox
            margins = [
                left / image.width,
                top / image.height,
                (image.width - right) / image.width,
                (image.height - bottom) / image.height,
            ]
            details["transparent_margin_ratios"] = margins
            if any(margin > SAFE_MARGIN_MAX_RATIO for margin in margins):
                errors.append("transparent safety margin must not exceed 8 percent on any side")

        corner_points = [(0, 0), (image.width - 1, 0), (0, image.height - 1), (image.width - 1, image.height - 1)]
        corner_alpha = [alpha.getpixel(point) for point in corner_points]
        details["corner_alpha"] = corner_alpha
        if any(value > 16 for value in corner_alpha):
            errors.append("rounded tile corners must remain transparent; reject white or checkerboard preview canvases")

        midpoint_points = [(image.width // 2, 0), (image.width - 1, image.height // 2), (image.width // 2, image.height - 1), (0, image.height // 2)]
        midpoint_alpha = [alpha.getpixel(point) for point in midpoint_points]
        details["edge_midpoint_alpha"] = midpoint_alpha

    return result(path, "png", details, errors)


def numeric_length(value: str | None) -> float | None:
    if not value:
        return None
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:px)?\s*", value)
    return float(match.group(1)) if match else None


def validate_svg(path: Path) -> dict:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    root = ET.fromstring(text)
    details: dict = {}
    if root.tag.rsplit("}", 1)[-1] != "svg":
        errors.append("root element must be svg")

    view_box = root.attrib.get("viewBox", "").split()
    details["viewBox"] = view_box
    if len(view_box) != 4:
        errors.append("SVG must define a four-number viewBox")
    else:
        try:
            values = [float(value) for value in view_box]
            if values[2] <= 0 or values[3] <= 0 or abs(values[2] - values[3]) > 1e-6:
                errors.append("SVG viewBox must be square")
        except ValueError:
            errors.append("SVG viewBox must contain numbers")

    width = numeric_length(root.attrib.get("width"))
    height = numeric_length(root.attrib.get("height"))
    details["dimensions"] = [width, height]
    if width is not None and height is not None and abs(width - height) > 1e-6:
        errors.append("SVG width and height must match")

    tags = [element.tag.rsplit("}", 1)[-1] for element in root.iter()]
    details["elements"] = sorted(set(tags))
    if "image" in tags:
        errors.append("SVG must not embed raster images without an approved exception")
    if "text" in tags:
        errors.append("SVG app icon must not contain text")
    for element in root.iter():
        for value in element.attrib.values():
            if re.search(r"(?:https?:)?//", value, flags=re.IGNORECASE):
                errors.append("SVG must not reference remote dependencies")
                break

    return result(path, "svg", details, sorted(set(errors)))


def validate(path: Path, profile: str = "standard") -> dict:
    if not path.is_file():
        return result(path, "unknown", {}, ["file does not exist"])
    suffix = path.suffix.lower()
    try:
        if suffix == ".png":
            return validate_png(path, profile=profile)
        if suffix == ".svg":
            return validate_svg(path)
        return result(path, "unknown", {}, ["only .png and .svg assets are supported"])
    except Exception as error:
        return result(path, suffix.removeprefix(".") or "unknown", {}, [str(error)])


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ishiku-icon-validator-") as directory:
        root = Path(directory)
        valid_png = root / "valid.png"
        excessive_margin_png = root / "margin.png"
        opaque_preview_png = root / "opaque-preview.png"
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).rounded_rectangle((2, 2, 61, 61), radius=14, fill=(77, 155, 232, 255))
        image.save(valid_png)
        margin = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(margin).rounded_rectangle((8, 8, 55, 55), radius=12, fill=(77, 155, 232, 255))
        margin.save(excessive_margin_png)
        Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(opaque_preview_png)
        valid_svg = root / "valid.svg"
        valid_svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#4D9BE8"/></svg>', encoding="utf-8")
        invalid_svg = root / "raster.svg"
        invalid_svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><image href="data:image/png;base64,AA=="/></svg>', encoding="utf-8")
        assert validate(valid_png)["valid"]
        assert not validate(excessive_margin_png)["valid"]
        assert not validate(opaque_preview_png)["valid"]
        assert validate(opaque_preview_png, profile="maskable")["valid"]
        assert validate(valid_svg)["valid"]
        assert not validate(invalid_svg)["valid"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", nargs="*", type=Path)
    parser.add_argument("--profile", choices=("standard", "maskable"), default="standard")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print(json.dumps({"status": "VERIFIED", "self_test": "passed"}, indent=2))
        return 0
    if not args.assets:
        parser.error("provide at least one SVG or PNG asset")
    assets = [validate(path, profile=args.profile) for path in args.assets]
    valid = all(asset["valid"] for asset in assets)
    print(json.dumps({"status": "VERIFIED" if valid else "IMPLEMENTED_BUT_NOT_VERIFIED", "assets": assets}, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
