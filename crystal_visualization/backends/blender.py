from __future__ import annotations

"""Blender (bpy) backend for publication-quality crystal renders.

This module must only be imported when bpy is available. CrystalRenderer
imports it lazily inside render() so the rest of the package works without
a Blender installation.

Two execution modes are supported:
  1. Inside Blender: run via `blender --background --python script.py`
  2. Standalone bpy wheel: `pip install bpy` (lags behind Blender releases).

The module builds a Blender scene from ASE Atoms, sets up an orthographic
camera, renders to a transparent TIFF, then calls the annotate module to
composite vector annotations (cell box, labels, scale bar) on top.
"""

import tomllib
from pathlib import Path

from ase import Atoms

_STYLES_DIR = Path(__file__).parents[2] / "config" / "styles"


def _load_style(name: str) -> dict:
    path = _STYLES_DIR / f"{name}.toml"
    if not path.exists():
        path = _STYLES_DIR / "default.toml"
    with open(path, "rb") as f:
        return tomllib.load(f)


def render(
    cluster: Atoms,
    center_index: int,
    camera: str,
    style_name: str,
    output: Path,
    save_blend: bool = False,
) -> Path:
    """Render the cluster with Blender and composite vector annotations.

    Writes:
      <output>.tiff  — raw Blender render (transparent background)
      <output>.svg   — vector annotation layer
      <output>       — composited final file (PDF/TIFF/EPS)
    Optionally writes:
      <output>.blend — Blender scene for manual inspection
    """
    try:
        import bpy  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "The 'blender' backend requires bpy. "
            "Either run inside Blender (`blender --background --python script.py`) "
            "or install the standalone wheel: `pip install bpy`. "
            "See DESIGN.md §2 for details."
        ) from e

    from crystal_visualization.backends import _blender_scene as scene_builder

    style = _load_style(style_name)

    # Build and render the Blender scene.
    tiff_path = output.with_suffix(".tiff")
    blend_path = output.with_suffix(".blend") if save_blend else None
    scene_builder.build_and_render(
        cluster=cluster,
        center_index=center_index,
        camera=camera,
        style=style,
        output_tiff=tiff_path,
        save_blend=blend_path,
    )

    # Composite vector annotation layer on top.
    from crystal_visualization import annotate, export

    svg_path = output.with_suffix(".svg")
    annotate.draw(cluster, center_index, tiff_path, style, svg_path)
    export.composite(tiff_path, svg_path, output)

    return output
