from __future__ import annotations

"""Final assembly: composite Blender TIFF + SVG annotation → PDF / EPS / TIFF."""

from pathlib import Path

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
    # Convert SVG annotation to PDF and embed the TIFF as background.
    # Simple approach: render SVG to PDF; let the consumer merge with the TIFF.
    # Full compositing requires reportlab or pypdf — deferred to implementation.
    cairosvg.svg2pdf(url=str(svg_path), write_to=str(output))


def _composite_to_raster(tiff_path: Path, svg_path: Path, output: Path) -> None:
    base = Image.open(tiff_path).convert("RGBA")
    # Render SVG annotation to PNG at same resolution.
    svg_png = cairosvg.svg2png(url=str(svg_path), output_width=base.width, output_height=base.height)
    overlay = Image.frombytes("RGBA", base.size, svg_png)
    composited = Image.alpha_composite(base, overlay)
    composited.save(str(output))
