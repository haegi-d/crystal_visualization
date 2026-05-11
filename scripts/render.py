"""CLI entry point for crystal_visualization.

Usage:
    python scripts/render.py config/my_run.toml

The TOML config file must contain a [run] section:

    [run]
    structure = "data/Er_Y2O3.xyz"
    defect_species = "Er"
    defect_index = 0
    cutoff_angstrom = 5.0
    camera = "isometric"
    style = "nature"
    output = "output/figure.pdf"
    backend = "matplotlib"   # or "plotly" / "blender"
    save_blend = false
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from crystal_visualization import CrystalRenderer


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    config_path = Path(sys.argv[1])
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    run = config["run"]

    output = Path(run["output"])
    output.parent.mkdir(parents=True, exist_ok=True)

    (
        CrystalRenderer()
        .load_structure(run["structure"])
        .select_defect(run.get("defect_species", "Er"), run.get("defect_index", 0))
        .set_neighbor_cutoff(run.get("cutoff_angstrom", 5.0))
        .set_camera(run.get("camera", "isometric"))
        .set_style(run.get("style", "default"))
        .render(
            output=output,
            backend=run.get("backend", "matplotlib"),
            save_blend=run.get("save_blend", False),
        )
    )

    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
