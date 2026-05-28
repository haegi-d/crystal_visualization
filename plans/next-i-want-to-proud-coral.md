# Plan: Add Nb Nanowire and Si Substrate to Blender Scene

## Context

The crystal visualization currently renders only the atomic cluster (defect + coordination shell) as a floating object. The user wants to add the physical device context shown in the reference SEM/schematic images: a Nb superconducting nanowire on which the crystal sits, and a Si substrate below both. This produces a publication figure showing the full experimental device geometry for a quantum sensing / NMR experiment.

Physical dimensions (user-specified):
- Crystal reference size: ~400 nm
- Nb nanowire: 80 nm thick × 350 nm wide × 5 µm long (show ~3 µm depth)
- Si substrate: 300 nm thick, wider than nanowire

Visual target: The reference images show the nanowire as golden/yellow, the substrate as light blue, and the crystal sitting on top of the nanowire — matching the isometric schematic provided.

## Approach

All new geometry lives in `_blender_scene.py`. Dimensions are expressed as ratios of `cluster_reference_size` (the max bounding-box extent of the atom cluster), calibrated against the known physical crystal size (400 nm). This keeps the stylized geometry proportional regardless of which structure file is loaded.

```
cluster_size_angstrom = (positions.max - positions.min).max()
scale = cluster_size_angstrom / 400.0   # Å per nm
nanowire_t  = 80.0  * scale    # 80 nm → Å in scene
nanowire_w  = 350.0 * scale    # 350 nm
nanowire_l  = show_nm * scale  # show_nm default 3000 (3 µm)
substrate_t = 300.0 * scale    # 300 nm
```

Positioning:
- `cluster_bottom_z = positions[:, 2].min()` (minus box padding)
- Nanowire center Z = `cluster_bottom_z − nanowire_t / 2`
- Nanowire XY center = cluster XY mean, oriented along Y-axis (long axis)
- Substrate center Z = `nanowire_bottom_z − substrate_t / 2`
- Substrate XY: 3× nanowire_w wide, same length as nanowire

Camera: when nanowire/substrate enabled, expand ortho_scale to frame nanowire length and shift camera center to midpoint between crystal top and substrate bottom.

## Critical File

`crystal_visualization/backends/_blender_scene.py` — all changes here.

## Implementation Steps

### 1. Add `_make_nb_material(hex_color)` (~15 lines)
- Principled BSDF, metallic (0.9), low roughness (0.05)
- Default color `"#c8a84b"` (warm gold matching reference image)
- Slight anisotropy for metallic sheen

### 2. Add `_make_si_material(hex_color)` (~12 lines)
- Principled BSDF, slight subsurface, low roughness (0.1)
- Default color `"#a8c8e8"` (light blue matching reference image)
- Not fully metallic — wafer-like polished surface

### 3. Add `_add_nanowire(cluster, style)` → returns `(obj, nanowire_bottom_z)`
```python
def _add_nanowire(cluster, style):
    nw = style.get("nanowire", {})
    if not nw.get("enabled", False):
        return None, cluster.positions[:, 2].min()
    ...
    # compute scale from cluster bounding box
    # create bpy mesh box centered below cluster
    # apply Nb material
    # name object "nanowire"
```

### 4. Add `_add_substrate(nanowire_bottom_z, cluster_center_xy, crystal_size, style)` → returns obj
```python
def _add_substrate(nanowire_bottom_z, cx, cy, crystal_size, style):
    sub = style.get("substrate", {})
    if not sub.get("enabled", False):
        return None
    ...
    # create wide flat slab below nanowire_bottom_z
    # apply Si material
    # name object "substrate_si"
```

### 5. Update `_setup_camera` signature
Add optional `scene_center_override` and `ortho_scale_override` params. When supplied, use them instead of computing from cluster only:
```python
def _setup_camera(cluster, view, has_box=True,
                  scene_center_override=None,
                  ortho_scale_override=None):
```

### 6. Update `build_and_render()`
After atoms/bonds/box, insert:
```python
crystal_size = (cluster.positions.max(axis=0) - cluster.positions.min(axis=0)).max()
_, nw_bottom = _add_nanowire(cluster, style)
cx, cy = cluster.positions[:, :2].mean(axis=0)
_add_substrate(nw_bottom, cx, cy, crystal_size, style)

# Camera framing when substrate/nanowire present
nw_style = style.get("nanowire", {})
show_nm = float(nw_style.get("show_depth_nm", 3000.0))
scale = crystal_size / 400.0
if nw_style.get("enabled", False):
    nw_l = show_nm * scale
    sub_t = float(style.get("substrate", {}).get("thickness_nm", 300.0)) * scale
    scene_bot = nw_bottom - sub_t
    scene_top = cluster.positions[:, 2].max()
    scene_cz = (scene_top + scene_bot) / 2.0
    scene_center = (cx, cy, scene_cz)
    ortho = nw_l * 0.9
    _setup_camera(cluster, camera, has_box=box_enabled,
                  scene_center_override=scene_center,
                  ortho_scale_override=ortho)
else:
    _setup_camera(cluster, camera, has_box=box_enabled)
```

### 7. Add style config keys to `vivid.toml`
```toml
[nanowire]
enabled       = true
color         = "#c8a84b"   # warm gold (Nb)
show_depth_nm = 3000.0      # nm of nanowire shown (each side extends this / 2)

[substrate]
enabled      = true
color        = "#a8c8e8"    # light blue (Si wafer)
thickness_nm = 300.0
```

Also add disabled stubs to `default.toml` and `nature.toml`.

## Mesh construction detail

Use `bmesh` (matching existing `_add_crystal_box` pattern) to build the rectangular slabs:
- 8 corners, 6 quad faces
- `bmesh.ops.recalc_face_normals` for correct shading
- `bpy.ops.object.shade_smooth()` applied

## Output files

Save to new files to preserve the existing renders:
- `output/device_scene.blend` — new Blender scene with nanowire + substrate
- `output/device_scene.tiff` — rendered output

The existing `output/figure.blend` and `output/crystal_vivid.blend` are left untouched.

## Verification

1. Run via Blender MCP tool (`mcp__blender__execute_blender_code`) calling `build_and_render()` with `save_blend=Path("output/device_scene.blend")` and output tiff `Path("output/device_scene.tiff")`
2. Inspect `output/device_scene.blend` in Blender to confirm `nanowire` and `substrate_si` objects are present, positioned below the crystal cluster
3. Visual check: crystal sits on golden nanowire; light-blue substrate visible beneath; isometric camera frames the full composition

## Files modified
- `crystal_visualization/backends/_blender_scene.py` (primary)
- `config/styles/vivid.toml` (add `[nanowire]` + `[substrate]` sections)
- `config/styles/default.toml` (add disabled stubs)
- `config/styles/nature.toml` (add disabled stubs)
