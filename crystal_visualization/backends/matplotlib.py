from __future__ import annotations

import tomllib
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from ase import Atoms

_STYLES_DIR = Path(__file__).parents[2] / "config" / "styles"


def _load_style(name: str) -> dict:
    path = _STYLES_DIR / f"{name}.toml"
    if not path.exists():
        path = _STYLES_DIR / "default.toml"
    with open(path, "rb") as f:
        return tomllib.load(f)


def _project(positions: np.ndarray, view: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (x, y) 2D projection coordinates for the given camera view."""
    if view == "isometric":
        # Standard crystallographic isometric: rotate 45° around Z, then 35.26° around X.
        theta = np.radians(45)
        phi = np.radians(35.264)
        x = positions[:, 0] * np.cos(theta) - positions[:, 1] * np.sin(theta)
        y = (
            positions[:, 0] * np.sin(theta) * np.sin(phi)
            + positions[:, 1] * np.cos(theta) * np.sin(phi)
            + positions[:, 2] * np.cos(phi)
        )
        return x, y
    if view == "top":
        return positions[:, 0], positions[:, 1]
    if view == "front":
        return positions[:, 0], positions[:, 2]
    if view == "side":
        return positions[:, 1], positions[:, 2]
    raise ValueError(f"Unknown view: {view!r}")


def render(
    cluster: Atoms,
    center_index: int,
    camera: str,
    style_name: str,
    output: Path,
    bonds: list[tuple[int, int]] | None = None,
) -> Path:
    """Render a 2D projection scatter plot of the cluster to output."""
    style = _load_style(style_name)
    atom_style = style.get("atoms", {})
    fig_style = style.get("figure", {})

    dpi = fig_style.get("dpi", 300)
    bg = fig_style.get("background", "white")
    fig_width_mm = fig_style.get("width_mm", 86)
    fig_height_mm = fig_style.get("height_mm", 86)

    fig, ax = plt.subplots(
        figsize=(fig_width_mm / 25.4, fig_height_mm / 25.4),
        facecolor=bg,
    )
    ax.set_facecolor(bg)
    ax.set_aspect("equal")
    ax.axis("off")

    x, y = _project(cluster.positions, camera)

    # Draw bonds before atoms so atoms render on top.
    bond_color = style.get("bonds", {}).get("color", "#888888")
    bond_lw = style.get("bonds", {}).get("linewidth", 0.8)

    for i, j in (bonds or []):
        ax.plot([x[i], x[j]], [y[i], y[j]], color=bond_color, lw=bond_lw, zorder=1)

    # Draw atoms.
    default_colors = atom_style.get("colors", {})
    default_radii = atom_style.get("radii", {})

    for idx, (symbol, xi, yi) in enumerate(zip(cluster.symbols, x, y)):
        color = default_colors.get(symbol, "#aaaaaa")
        radius = default_radii.get(symbol, 0.4)
        edgecolor = "#333333" if idx != center_index else "#000000"
        lw = 0.5 if idx != center_index else 1.5
        circle = plt.Circle(
            (xi, yi), radius, color=color, ec=edgecolor, lw=lw, zorder=2 + yi
        )
        ax.add_patch(circle)

    ax.autoscale()
    fig.savefig(output, dpi=dpi, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    return output
