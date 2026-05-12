from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
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
    bonds: list[tuple[int, int]] | None = None,
) -> Path:
    """Render an interactive 3D scatter plot.

    Writes an HTML file to output (or displays inline in Jupyter if output
    has no suffix). Hover tooltip shows species, atom index, and 3D position.
    """
    style = _load_style(style_name)
    atom_style = style.get("atoms", {})
    default_colors = atom_style.get("colors", {})
    default_radii = atom_style.get("radii", {})

    positions = cluster.positions
    symbols = list(cluster.symbols)
    center_pos = positions[center_index]

    distances = np.linalg.norm(positions - center_pos, axis=1)
    hover = [
        f"{sym} | idx {i} | d={d:.2f} Å"
        for i, (sym, d) in enumerate(zip(symbols, distances))
    ]

    colors = [default_colors.get(sym, "#aaaaaa") for sym in symbols]
    sizes = [default_radii.get(sym, 0.4) * 40 for sym in symbols]

    traces = [
        go.Scatter3d(
            x=positions[:, 0],
            y=positions[:, 1],
            z=positions[:, 2],
            mode="markers",
            marker=dict(color=colors, size=sizes, opacity=0.9, line=dict(width=0.5, color="#333333")),
            text=hover,
            hoverinfo="text",
        )
    ]

    # Draw bond lines as separate Scatter3d traces.
    bond_color = style.get("bonds", {}).get("color", "#888888")

    for i, j in (bonds or []):
        traces.append(
            go.Scatter3d(
                x=[positions[i, 0], positions[j, 0], None],
                y=[positions[i, 1], positions[j, 1], None],
                z=[positions[i, 2], positions[j, 2], None],
                mode="lines",
                line=dict(color=bond_color, width=2),
                hoverinfo="none",
                showlegend=False,
            )
        )

    fig = go.Figure(data=traces)
    fig.update_layout(
        scene=dict(aspectmode="data"),
        showlegend=False,
        margin=dict(l=0, r=0, t=0, b=0),
    )

    if output.suffix == ".html" or output.suffix == "":
        fig.write_html(str(output.with_suffix(".html")))
        return output.with_suffix(".html")

    # In Jupyter, call fig.show() instead of writing a file.
    fig.show()
    return output
