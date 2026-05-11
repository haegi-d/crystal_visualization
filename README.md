# crystal_visualization

Publication-quality visualization of crystal defects for high-impact physics papers.
Targets Er-doped crystalline hosts (Y₂O₃, YAG, …) but works with any defect + host
described by XYZ, CIF, POSCAR, or VESTA files.

---

## Pipeline

```
VESTA / CIF / POSCAR / XYZ
          │
          ▼
  parse   │  ASE → Atoms object
          │
          ▼
  select  │  Er defect + neighbor shell (KDTree cutoff)
          │
          ▼
  scene   │  Blender spheres, bonds, unit-cell box
          │
          ▼
  render  │  Orthographic camera → transparent TIFF @ 600 DPI
          │
          ▼
annotate  │  Vector layer: cell edges, labels, scale bar (SVG)
          │
          ▼
  export  │  TIFF · PDF · EPS  (journal-dependent)
```

Three backends let you iterate before committing to a full Blender render:

| Backend | When to use | Output |
|---|---|---|
| `matplotlib` | Draft figures, Jupyter inline, no Blender | PDF / PNG |
| `plotly` | Interactive 3D, inspect atom indices | HTML / Jupyter widget |
| `blender` | Final publication figure | TIFF + SVG → PDF/EPS |

All backends share the same style preset (colors, radii, bond thickness).

---

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

The `blender` backend requires a separate Blender installation (≥ 4.0).
See [DESIGN.md](DESIGN.md#3d-renderer-blender) for setup instructions.

---

## Quickstart

**Jupyter notebook:**

```python
from crystal_visualization import CrystalRenderer

cr = CrystalRenderer()
(cr
  .load_structure("data/Er_Y2O3.xyz")
  .select_defect(species="Er", index=0)
  .set_neighbor_cutoff(angstrom=5.0)
  .set_camera(view="isometric")
  .set_style(style="nature")
  .render(output="output/figure.pdf", backend="matplotlib"))   # swap to "blender" for final
```

**Command line:**

```bash
python scripts/render.py config/my_run.toml
```

---

## Output format strategy

Atoms and bonds are rendered as a high-resolution transparent TIFF by Blender —
photorealistic shading cannot be replicated in vector format.
Cell box edges, atom labels, and scale annotations are drawn as a separate SVG layer
so they remain resolution-independent and editable in Inkscape / Illustrator.
The two layers are composited into the final PDF/EPS/TIFF by the export stage.

---

## Project docs

- [DESIGN.md](DESIGN.md) — decision log: why each library and approach was chosen
- [STYLE.md](STYLE.md) — Python coding conventions for this project
