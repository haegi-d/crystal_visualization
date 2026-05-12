from __future__ import annotations

"""Final assembly: composite Blender TIFF + SVG annotation → PDF / EPS / TIFF."""

from pathlib import Path

import io

import cairosvg
from PIL import Image


def composite(tiff_path: Path, svg_path: Path, output: Path) -> Path:
    """Overlay the SVG annotation on the TIFF render and write to output.

    output suffix determines format: .pdf, .tiff/.tif, .eps, .png.
    """
    suffix = output.suffix.lower()

    if suffix == ".pdf":
        _composite_to_pdf(tiff_path, svg_path, output)
    elif suffix in (".tiff", ".tif", ".png"):
        _composite_to_raster(tiff_path, svg_path, output)
    elif suffix == ".eps":
        # EPS via PDF intermediate (cairosvg does not support EPS directly).
        pdf_tmp = output.with_suffix(".pdf")
        _composite_to_pdf(tiff_path, svg_path, pdf_tmp)
        # Caller can use ghostscript to convert PDF→EPS if needed.
        return pdf_tmp
    else:
        raise ValueError(f"Unsupported output format: {suffix!r}")

    return output


def _composite_to_pdf(tiff_path: Path, svg_path: Path, output: Path) -> None:
    base = Image.open(tiff_path).convert("RGBA")
    svg_png = cairosvg.svg2png(url=str(svg_path), output_width=base.width, output_height=base.height)
    overlay = Image.open(io.BytesIO(svg_png)).convert("RGBA")
    composited = Image.alpha_composite(base, overlay).convert("RGB")
    composited.save(str(output), format="PDF", resolution=300)


def _composite_to_raster(tiff_path: Path, svg_path: Path, output: Path) -> None:
    base = Image.open(tiff_path).convert("RGBA")
    # Render SVG annotation to PNG at same resolution.
    svg_png = cairosvg.svg2png(url=str(svg_path), output_width=base.width, output_height=base.height)
    overlay = Image.open(io.BytesIO(svg_png)).convert("RGBA")
    composited = Image.alpha_composite(base, overlay)
    composited.save(str(output))
