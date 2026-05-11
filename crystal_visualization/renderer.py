from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from ase import Atoms

from crystal_visualization import parse, select

log = logging.getLogger(__name__)

Backend = Literal["matplotlib", "plotly", "blender"]
CameraView = Literal["isometric", "top", "front", "side"]


class CrystalRenderer:
    """Stateful pipeline for crystal defect visualization.

    Each method mutates internal state and returns self for chaining.
    The same instance can be reused across multiple render() calls.
    """

    def __init__(self) -> None:
        self._atoms: Atoms | None = None
        self._cluster: Atoms | None = None
        self._center_index: int | None = None
        self._cutoff: float = 5.0
        self._camera: CameraView = "isometric"
        self._style: str = "default"

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------

    def load_structure(self, path: str | Path) -> "CrystalRenderer":
        """Load a structure file (XYZ, CIF, POSCAR) into the renderer."""
        self._atoms = parse.load(path)
        self._cluster = None
        log.info("Loaded %d atoms from %s", len(self._atoms), path)
        return self

    def select_defect(self, species: str, index: int = 0) -> "CrystalRenderer":
        """Identify the defect site by species and occurrence index."""
        if self._atoms is None:
            raise RuntimeError("Call load_structure() before select_defect().")
        self._center_index = select.find_defect(self._atoms, species, index)
        log.info("Defect: %s[%d] → atom index %d", species, index, self._center_index)
        self._cluster = None
        return self

    def set_neighbor_cutoff(self, angstrom: float) -> "CrystalRenderer":
        """Set the neighbor shell radius in Ångströms."""
        self._cutoff = angstrom
        self._cluster = None
        return self

    def set_camera(self, view: CameraView = "isometric") -> "CrystalRenderer":
        """Set the camera orientation for the render."""
        self._camera = view
        return self

    def set_style(self, style: str = "default") -> "CrystalRenderer":
        """Load a style preset from config/styles/<style>.toml."""
        self._style = style
        return self

    def render(
        self,
        output: str | Path,
        backend: Backend = "matplotlib",
        save_blend: bool = False,
    ) -> Path:
        """Run the full pipeline and write the output figure.

        Args:
            output: Destination path. Extension determines format (.pdf, .tiff, .png).
            backend: 'matplotlib' for quick draft, 'plotly' for interactive Jupyter,
                     'blender' for publication-quality final render.
            save_blend: If True and backend='blender', save the .blend scene alongside output.
        """
        self._build_cluster()
        output = Path(output)

        if backend == "matplotlib":
            from crystal_visualization.backends.matplotlib import render as mpl_render
            return mpl_render(self._cluster, self._center_index, self._camera, self._style, output)

        if backend == "plotly":
            from crystal_visualization.backends.plotly import render as plotly_render
            return plotly_render(self._cluster, self._center_index, self._camera, self._style, output)

        if backend == "blender":
            from crystal_visualization.backends.blender import render as blender_render
            return blender_render(
                self._cluster, self._center_index, self._camera, self._style, output,
                save_blend=save_blend,
            )

        raise ValueError(f"Unknown backend: {backend!r}. Choose 'matplotlib', 'plotly', or 'blender'.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_cluster(self) -> None:
        if self._atoms is None:
            raise RuntimeError("Call load_structure() first.")
        if self._center_index is None:
            raise RuntimeError("Call select_defect() first.")
        if self._cluster is None:
            self._cluster = select.select_cluster(self._atoms, self._center_index, self._cutoff)
            log.info("Cluster: %d atoms within %.1f Å", len(self._cluster), self._cutoff)
