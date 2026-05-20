"""Huawei Cloud draw.io icon library loader.

Reads XML library files from vendor/hwc-drawio-libraries/color/, parses
entries (title, SVG data, dimensions), and exposes lookup by product name.
Also supports materializing embedded SVG data URIs to local SVG/PNG files so
draw.io CLI can reference stable file paths during PNG export.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from urllib.parse import quote
from functools import lru_cache
from pathlib import Path

import cairosvg

logger = logging.getLogger(__name__)

LIB_DIR = Path(__file__).resolve().parent.parent / "vendor" / "hwc-drawio-libraries" / "color"


@lru_cache(maxsize=1)
def load_hwc_libraries() -> list[dict]:
    """Load and parse all HWC draw.io library files.

    Each library file is an <mxlibrary> wrapping a JSON array of entries.
    Returns a flat list of all entries across all libraries.
    """
    all_entries: list[dict] = []
    if not LIB_DIR.is_dir():
        logger.warning("HWC icon library directory not found: %s", LIB_DIR)
        return all_entries

    for fname in sorted(os.listdir(LIB_DIR)):
        if not fname.endswith(".xml"):
            continue
        fpath = LIB_DIR / fname
        try:
            content = fpath.read_text(encoding="utf-8").strip()
            # Strip <mxlibrary> / </mxlibrary> wrappers
            prefix = "<mxlibrary>"
            suffix = "</mxlibrary>"
            if content.startswith(prefix):
                content = content[len(prefix):]
            if content.endswith(suffix):
                content = content[: -len(suffix)]
            entries = json.loads(content)
            for e in entries:
                e["_library_file"] = fname
            all_entries.extend(entries)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse library %s: %s", fname, exc)

    logger.info("Loaded %d HWC icon entries from %s", len(all_entries), LIB_DIR)
    return all_entries


@lru_cache(maxsize=1)
def _title_index() -> dict[str, dict]:
    """Build a title -> entry index (first match wins for duplicates)."""
    index: dict[str, dict] = {}
    for entry in load_hwc_libraries():
        title = entry.get("title", "")
        if title and title not in index:
            index[title] = entry
    return index


def resolve_hwc_icon(icon_title: str) -> dict | None:
    """Look up an icon entry by its exact library title.

    Returns the entry dict with keys: title, data, w, h, aspect, _library_file.
    Returns None if not found.
    """
    return _title_index().get(icon_title)


def list_supported_products() -> list[str]:
    """Return sorted list of all available icon titles."""
    return sorted(_title_index().keys())


def materialize_icon_svg(icon_title: str, output_dir: Path) -> Path | None:
    """Write an icon's embedded SVG data URI to a local SVG file.

    draw.io CLI export does not reliably render `data:image/svg+xml;base64,...`
    passed inline through mxGraph style attributes. Materializing the SVG to a
    file and referencing it with a file URI is much more stable.
    """
    entry = resolve_hwc_icon(icon_title)
    if not entry:
        return None
    data = entry.get("data", "")
    prefix = "data:image/svg+xml;base64,"
    if not isinstance(data, str) or not data.startswith(prefix):
        logger.warning("Icon %s does not contain an SVG data URI", icon_title)
        return None

    svg_b64 = data[len(prefix):]
    try:
        svg_bytes = base64.b64decode(svg_b64)
    except Exception as exc:
        logger.warning("Failed to decode icon SVG for %s: %s", icon_title, exc)
        return None

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", icon_title).strip("_") or "icon"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{safe_name}.svg"
    path.write_bytes(svg_bytes)
    return path


def materialize_icon_png(icon_title: str, output_dir: Path, *, size: int = 72) -> Path | None:
    """Rasterize an icon's embedded SVG to a local PNG file.

    draw.io CLI export is more reliable with PNG image nodes than SVG-backed
    image nodes. This function keeps the vendor source as SVG, but caches a
    PNG variant for HLD rendering.
    """
    svg_path = materialize_icon_svg(icon_title, output_dir)
    if not svg_path:
        return None

    png_path = svg_path.with_suffix(".png")
    try:
        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(png_path),
            output_width=size,
            output_height=size,
        )
    except Exception as exc:
        logger.warning("Failed to rasterize icon PNG for %s: %s", icon_title, exc)
        return None
    return png_path


def build_icon_png_data_uri(icon_title: str, output_dir: Path, *, size: int = 72) -> str | None:
    """Return a PNG data URI for an icon, generating a cached PNG if needed."""
    png_path = materialize_icon_png(icon_title, output_dir, size=size)
    if not png_path or not png_path.exists():
        return None
    try:
        encoded = base64.b64encode(png_path.read_bytes()).decode("ascii")
    except Exception as exc:
        logger.warning("Failed to encode icon PNG data URI for %s: %s", icon_title, exc)
        return None
    return f"data:image/png;base64,{encoded}"


def build_icon_svg_data_uri(icon_title: str) -> str | None:
    """Return a draw.io-compatible SVG data URI without `;base64`.

    mxCell style strings use `;` as a property delimiter. A standard
    `data:image/svg+xml;base64,...` URI contains `;base64`, which breaks style
    parsing and causes draw.io to ignore the image. draw.io's own libraries use
    URL-encoded SVG content instead: `data:image/svg+xml,<encoded>`.
    """
    entry = resolve_hwc_icon(icon_title)
    if not entry:
        return None
    data = entry.get("data", "")
    prefix = "data:image/svg+xml;base64,"
    if not isinstance(data, str) or not data.startswith(prefix):
        logger.warning("Icon %s does not contain an SVG data URI", icon_title)
        return None
    try:
        svg_text = base64.b64decode(data[len(prefix):]).decode("utf-8")
    except Exception as exc:
        logger.warning("Failed to decode icon SVG text for %s: %s", icon_title, exc)
        return None
    return f"data:image/svg+xml,{quote(svg_text, safe='')}"
