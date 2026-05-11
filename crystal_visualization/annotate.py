from __future__ import annotations

"""Vector annotation layer: cell box edges, atom labels, scale bar.

Produces an SVG file that is composited on top of the Blender TIFF render.
Using SVG here (rather than baking annotations into the Blender render) means:
- Labels are resolution-independent and font-editable in Inkscape.
- Changing a label does not require a full Blender re-render.
- The SVG can be adjusted manually while keeping the programmatic baseline.
"""

from pathlib import Path

import svgwrite
from ase import Atoms


def draw(
    cluster: Atoms,
    center_index: int,
    reference_tiff: Path,
    style: dict,
    output: Path,
) -> Path:
    """Write an SVG annotation layer sized to match reference_tiff.

    Stub: draws a scale bar and a label for the center atom.
    Full implementation will add cell box edges projected into camera space.
    """
    from PIL import Image

    img = Image.open(reference_tiff)
    width, height = img.size

    ann_style = style.get("annotations", {})
    font_size = ann_style.get("font_size", 12)
    font_family = ann_style.get("font_family", "Helvetica")
    scale_bar_angstrom = ann_style.get("scale_bar_angstrom", 5)

    dwg = svgwrite.Drawing(str(output), size=(width, height))

    # Scale bar (bottom-left corner, 10% margin).
    margin = int(width * 0.1)
    angstrom_per_px = _estimate_scale(cluster, width)
    bar_px = int(scale_bar_angstrom / angstrom_per_px) if angstrom_per_px > 0 else 50

    bar_y = height - margin
    dwg.add(dwg.line(
        start=(margin, bar_y), end=(margin + bar_px, bar_y),
        stroke="black", stroke_width=2,
    ))
    dwg.add(dwg.text(
        f"{scale_bar_angstrom} Å",
        insert=(margin + bar_px // 2, bar_y - 4),
        text_anchor="middle",
        font_size=font_size,
        font_family=font_family,
        fill="black",
    ))

    # Label for center atom.
    center_symbol = cluster.symbols[center_index]
    dwg.add(dwg.text(
        center_symbol,
        insert=(width // 2, height // 2),
        text_anchor="middle",
        font_size=font_size * 1.2,
        font_family=font_family,
        fill="black",
    ))

    dwg.save()
    return output


def _estimate_scale(cluster: Atoms, image_width_px: int) -> float:
    """Rough estimate of Å/pixel for the scale bar. Replaced by exact camera projection."""
    extent = cluster.positions[:, 0].max() - cluster.positions[:, 0].min()
    if extent == 0:
        return 0.0
    return extent / (image_width_px * 0.8)
