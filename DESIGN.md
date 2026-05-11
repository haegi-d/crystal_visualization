# Design decisions

This file is a decision log. Each section names the decision, lists the alternatives
that were seriously considered, and explains why the chosen option was preferred.
The goal is to make the reasoning durable — future contributors (and future-you) should
be able to understand not just what we chose, but why, so they can revisit decisions
when the constraints change.

---

## 1. Structure parser: ASE

**Decision:** use [ASE (Atomic Simulation Environment)](https://wiki.fysik.dtu.dk/ase/)
as the primary parser.

**Alternatives considered:**
- **pymatgen** — mature, excellent CIF support, widely used in DFT workflows.
- **ASE** — lighter, clean Python-first API.
- **ase + pymatgen together** — use pymatgen only for CIF symmetry reduction, ASE for everything else.

**Why ASE:**
The core object we need is a list of atom positions with species labels and an optional
unit cell — that is exactly `ase.Atoms`. ASE reads XYZ, CIF, POSCAR, and VESTA-exported
files out of the box via `ase.io.read`. The API is simple enough to hold in one's head:

```python
atoms = ase.io.read("structure.xyz")
atoms.positions   # (N, 3) float64
atoms.symbols     # chemical symbols list
atoms.cell        # 3×3 cell matrix
```

pymatgen is heavier (Java and C++ deps for some features), and its primary strength is
thermodynamic analysis (phase diagrams, pourbaix, etc.) which we do not need. If we
ever need symmetry-reduced CIF structures or Hubbard U values, pymatgen can be added
as an optional dependency for that one step without replacing ASE.

---

## 2. 3D renderer: Blender (bpy)

**Decision:** use [Blender](https://www.blender.org/) scripted via `bpy` for the
publication-quality 3D render.

**Alternatives considered:**
- **VESTA** — the standard crystallography viewer. Beautiful default styles, used in most papers.
  Problem: not scriptable from Python; requires manual export from the GUI. Breaks reproducibility.
- **PyMOL** — excellent for biomolecules. Designed for proteins/DNA, not inorganic crystals.
  Commercial license for some uses.
- **matplotlib Axes3D** — zero extra deps, inline in Jupyter.
  Problem: no real depth cues, no ambient occlusion, no subsurface scattering.
  Output quality is not competitive for a high-impact physics paper figure.
- **MayaVi / VTK** — powerful scientific visualization. Steeper learning curve;
  output style is closer to scientific dashboards than paper figures.
- **Crystal Maker / VESTA + export** — GUI tools. Not reproducible from a script.
- **Blender (bpy)** — fully scriptable, photorealistic Cycles/EEVEE renderer,
  orthographic camera, transparent TIFF export, free and open-source, active development.

**Why Blender:**
The key requirement is a figure that looks like it could appear in *Nature* or
*Physical Review Letters* — polished, with depth, soft shading, and crisp atom spheres.
Blender's Cycles renderer produces ray-traced output with ambient occlusion and
subsurface scattering at 600 DPI. The orthographic camera mode renders without
perspective distortion, which is correct for crystal unit cell figures.
`bpy` gives full programmatic control: atom positions → mesh spheres → HDRI lighting
→ render → TIFF, entirely from a Python script with no GUI interaction.

**bpy installation note:**
`bpy` is not a standard pip package. Options:
1. Run the script inside Blender's Python (`blender --background --python script.py`).
2. Install the `bpy` standalone wheel: `pip install bpy` (≥ Blender 3.x wheels available
   on PyPI, but lag behind Blender releases).

We support both. The `backends/blender.py` module detects which context it's running in.

---

## 3. Annotation layer: svgwrite + matplotlib

**Decision:** use `svgwrite` for programmatic SVG generation of the vector annotation
layer (cell box edges, atom labels, scale bar, arrows). Use `matplotlib` as a fallback
for the matplotlib backend's annotation.

**Alternatives considered:**
- **Manual Inkscape editing** — common in practice. Breaks reproducibility: the SVG
  file diverges from the script every time someone opens Inkscape and moves a label.
- **Blender text objects** — Blender can render text. Problem: text is rasterized at
  render time, so it bakes into the TIFF at fixed DPI. Changing a label means a full
  re-render.
- **matplotlib for everything** — matplotlib can composite raster images and draw
  vector annotations. Viable, but matplotlib's SVG backend has quirks with embedded
  raster images at high DPI.
- **reportlab / WeasyPrint** — full PDF toolkits. More than needed for this use case.
- **svgwrite** — minimal library for constructing SVG elements from Python. Generates
  clean, editable SVG files. Compositing with the Blender TIFF is handled by
  `cairosvg` (SVG → PDF) and `Pillow` (TIFF compositing).

**Why svgwrite:**
The annotation layer (cell edges, labels) is a thin overlay over the Blender render.
svgwrite generates exactly the SVG we describe — no surprises. The output SVG is
human-readable and can be opened in Inkscape for final tweaks without losing the
programmatic baseline. The key invariant is that running the script again regenerates
the same SVG, so manual edits are always optional, never required.

---

## 4. Output strategy: hybrid raster + vector

**Decision:** render atoms/bonds as a raster TIFF from Blender; draw cell box, labels,
and annotations as a vector SVG; composite into a final PDF/EPS/TIFF.

**Alternatives considered:**
- **Pure vector (SVG/PDF for everything)** — would require decomposing the 3D atom
  scene into flat SVG paths. No depth, no shading, no ambient occlusion. Output looks
  like a schematic, not a render.
- **Pure raster (one Blender TIFF)** — easy, but labels and cell edges bake into the
  TIFF. Changing a label font or adding an arrow requires a full re-render. Also,
  rasterized text does not meet journal requirements (some journals require vector text).
- **Hybrid (chosen)** — Blender handles what it does best (photorealistic 3D);
  svgwrite handles what vector is best for (resolution-independent text and lines).
  The two layers composite cleanly. The SVG layer is trivially adjustable without
  touching Blender.

**Final assembly:**
- `cairosvg` converts the SVG annotation layer to PDF.
- `Pillow` composites the TIFF atom render with the SVG overlay.
- Output: TIFF (for journals requiring raster), PDF (for journals requiring vector),
  or EPS (legacy support).

---

## 5. Configuration: TOML

**Decision:** use TOML files for all pipeline configuration.

**Alternatives considered:**
- **YAML** — widely used, human-friendly. Problem: YAML has implicit type coercions
  (e.g., `yes` → `True`, `1.0` → float vs string depending on context) that cause
  subtle bugs in scientific configs where values are often numbers that look like strings.
- **JSON** — no comments, trailing-comma errors, verbose for nested structures.
- **Python dict / dataclass** — configuration as code. Requires users to write Python;
  breaks the CLI/MCP use case where a non-programmer collaborator might edit the config.
- **TOML (chosen)** — no implicit type coercions, supports comments, clear spec,
  and `tomllib` is in the Python 3.11 standard library (no extra dep).

Style presets live in `config/styles/` as separate TOML files (`nature.toml`,
`default.toml`) so adding a new journal preset is a single file addition with no
code change.

---

## 6. API design: stateful CrystalRenderer class

**Decision:** expose the pipeline as a stateful `CrystalRenderer` class with chainable
methods, backed by plain functions in each module.

**Alternatives considered:**
- **Functional pipeline (pure functions)** — each stage takes the previous stage's
  output as input. Maximally composable, but awkward for the MCP use case: an MCP
  tool call is a single method invocation with no way to thread state through
  a series of function calls across tool calls.
- **CLI only** — `argparse`-based script. Easiest to run from the terminal, but not
  usable from Jupyter or as an MCP server without re-implementing the same logic.
- **Stateful class (chosen)** — each method (`load_structure`, `select_defect`, …)
  mutates the renderer's internal state and returns `self` so calls can be chained.
  The MCP server wraps each method as a tool; a session maps to one `CrystalRenderer`
  instance. Jupyter uses the same API inline. The CLI instantiates the class and calls
  methods driven by a TOML config.

The internal implementation of each pipeline stage is a plain function in its own
module (`parse.py`, `select.py`, …). The class in `renderer.py` is a thin orchestrator
that calls those functions. This keeps the class testable and the functions reusable.

---

## 7. Rendering backends: three-tier (matplotlib / plotly / blender)

**Decision:** support three rendering backends selected via the `backend=` argument to
`render()`.

**Alternatives considered:**
- **Blender only** — highest quality, but requires a Blender installation for every
  run. Impractical during structure selection and iteration, which may happen dozens
  of times per session.
- **matplotlib only** — always available, but 2D projection quality is not sufficient
  for the final figure.
- **py3Dmol** — JavaScript-based molecular viewer that embeds in Jupyter. Good for
  biomolecule conventions (ball-and-stick PDB style), but requires a running browser
  and does not export to PDF/TIFF programmatically.
- **Three-tier (chosen):**
  - `matplotlib` — instant, no extra deps beyond numpy/matplotlib, 2D orthographic
    projection with correct bond lines. Useful for: sanity-checking structure after
    parse, draft figures, quick PDF for a group meeting.
  - `plotly` — interactive 3D scatter in Jupyter. Hover tooltip shows species, atom
    index, and distance from defect. Useful for: choosing the right neighbor cutoff,
    verifying defect site selection, exploring the coordination shell.
  - `blender` — final publication render. Only invoked when the structure and style
    are finalized.

All three backends read from the same internal state (selected atoms, style preset,
camera view) so switching backend is one argument change with no other code edits.

---

## 8. Style presets: nature, physical_review, default

**Decision:** encode visual style (atom radii, CPK colors, bond thickness, background
color, DPI, font) in TOML presets rather than hardcoding in the backend.

**Why presets:**
Journal figure guidelines differ in significant ways: Nature requires white backgrounds
at 300–600 DPI; Physical Review uses specific line weights; some journals disallow
colored backgrounds. A preset file captures all of these choices in one place.
The `nature` preset uses enhanced CPK colors (slightly desaturated from the raw CPK
palette for printability), sphere radii scaled to look good at typical figure widths
(~86 mm single column), and a white background.

Adding a new journal preset is a TOML file addition with zero code changes.
