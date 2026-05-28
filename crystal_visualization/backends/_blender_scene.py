from __future__ import annotations

"""Blender scene construction for crystal cluster renders.

Called only after bpy has been confirmed importable (guard lives in blender.py).
Builds atom spheres and bond cylinders, optionally a liquid-glass crystal box,
sets up an orthographic camera, renders to a TIFF, and optionally saves the
.blend file.
"""

import math
from pathlib import Path

import bmesh
import bpy
import mathutils
import numpy as np
from ase import Atoms

_VIEW_DIRECTIONS: dict[str, tuple[float, float, float]] = {
    "top": (0.0, 0.0, 1.0),
    "front": (0.0, -1.0, 0.0),
    "side": (1.0, 0.0, 0.0),
    "isometric": (1.0, -1.0, 1.0),
}


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes):
        bpy.data.meshes.remove(block)
    for block in list(bpy.data.materials):
        bpy.data.materials.remove(block)


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    return (
        int(hex_color[1:3], 16) / 255,
        int(hex_color[3:5], 16) / 255,
        int(hex_color[5:7], 16) / 255,
    )


def _set_input(node: bpy.types.Node, name: str, value: object) -> None:
    """Set a node input by name, skipping inputs absent in older Blender builds."""
    if name in node.inputs:
        node.inputs[name].default_value = value


def _make_atom_material(
    name: str, hex_color: str, candy: bool = False
) -> bpy.types.Material:
    """Principled BSDF atom material.

    candy=True uses very low roughness + subsurface scattering for the glossy
    hard-candy look seen in publication crystal diagrams.
    """
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    r, g, b = _hex_to_rgb(hex_color)
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)

    if candy:
        bsdf.inputs["Roughness"].default_value = 0.04
        _set_input(bsdf, "Specular IOR Level", 1.4)   # Blender 4.x
        _set_input(bsdf, "Specular", 1.0)              # Blender 3.x
        _set_input(bsdf, "Subsurface Weight", 0.18)    # Blender 4.x
        _set_input(bsdf, "Subsurface", 0.18)           # Blender 3.x
        lighter = (min(r + 0.25, 1.0), min(g + 0.25, 1.0), min(b + 0.25, 1.0), 1.0)
        _set_input(bsdf, "Subsurface Color", lighter)  # 3.x only; 4.x uses Base Color
    else:
        bsdf.inputs["Roughness"].default_value = 0.08
        _set_input(bsdf, "Specular IOR Level", 0.9)
        _set_input(bsdf, "Specular", 0.9)
        _set_input(bsdf, "Subsurface Weight", 0.05)
        _set_input(bsdf, "Subsurface", 0.05)

    return mat


def _make_bond_material(hex_color: str) -> bpy.types.Material:
    """Metallic-rod material for bond cylinders."""
    mat = bpy.data.materials.new(name="bond")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    r, g, b = _hex_to_rgb(hex_color)
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.25
    _set_input(bsdf, "Metallic", 0.75)
    return mat


def _make_nb_material(hex_color: str) -> bpy.types.Material:
    """High-reflectivity metallic material for the Nb nanowire."""
    mat = bpy.data.materials.new(name="nanowire_nb")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    r, g, b = _hex_to_rgb(hex_color)
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.05
    _set_input(bsdf, "Metallic", 0.95)
    _set_input(bsdf, "Anisotropic", 0.3)
    _set_input(bsdf, "Specular IOR Level", 1.5)
    _set_input(bsdf, "Specular", 1.0)
    return mat


def _make_si_material(hex_color: str) -> bpy.types.Material:
    """Polished Si wafer material for the substrate."""
    mat = bpy.data.materials.new(name="substrate_si")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    r, g, b = _hex_to_rgb(hex_color)
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.10
    _set_input(bsdf, "Metallic", 0.0)
    _set_input(bsdf, "Specular IOR Level", 0.8)
    _set_input(bsdf, "Specular", 0.8)
    return mat


def _make_liquid_glass_material(box_style: dict) -> bpy.types.Material:
    """Principled BSDF glass with Fresnel rim glow and iridescence.

    Node graph:
      LayerWeight(Facing) ──► Mix(Fac)
      Principled BSDF     ──► Mix(Shader1) ──► Output
      Emission            ──► Mix(Shader2)
    """
    hex_color = box_style.get("color", "#c8e4ff")
    alpha = float(box_style.get("alpha", 0.12))
    ior = float(box_style.get("ior", 1.45))
    roughness = float(box_style.get("roughness", 0.02))
    iridescence = float(box_style.get("iridescence", 0.40))
    rim_strength = float(box_style.get("rim_strength", 0.35))

    r, g, b = _hex_to_rgb(hex_color)

    mat = bpy.data.materials.new(name="liquid_glass")
    mat.use_nodes = True
    if hasattr(mat, "blend_method"):   # removed in Blender 4.2
        mat.blend_method = "BLEND"
    if hasattr(mat, "shadow_method"):  # removed in Blender 4.2
        mat.shadow_method = "NONE"
    mat.use_backface_culling = False

    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (700, 0)

    mix = nodes.new("ShaderNodeMixShader")
    mix.location = (500, 0)
    links.new(mix.outputs[0], output.inputs["Surface"])

    layer_weight = nodes.new("ShaderNodeLayerWeight")
    layer_weight.location = (100, 200)
    layer_weight.inputs["Blend"].default_value = 0.25
    links.new(layer_weight.outputs["Facing"], mix.inputs["Fac"])

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, -120)
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["IOR"].default_value = ior
    bsdf.inputs["Alpha"].default_value = alpha
    _set_input(bsdf, "Transmission Weight", 1.0)
    _set_input(bsdf, "Transmission", 1.0)
    _set_input(bsdf, "Iridescence", iridescence)
    _set_input(bsdf, "Iridescence IOR", 1.30)
    _set_input(bsdf, "Iridescence Thickness", 600.0)
    links.new(bsdf.outputs["BSDF"], mix.inputs[1])

    emission = nodes.new("ShaderNodeEmission")
    emission.location = (300, 120)
    emission.inputs["Color"].default_value = (
        min(r * 0.6 + 0.4, 1.0),
        min(g * 0.6 + 0.4, 1.0),
        min(b * 0.4 + 0.6, 1.0),
        1.0,
    )
    emission.inputs["Strength"].default_value = rim_strength
    links.new(emission.outputs["Emission"], mix.inputs[2])

    return mat


def _build_box_vectors(
    cluster: Atoms, padding: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (origin, va, vb, vc) of the bounding parallelepiped."""
    positions = cluster.positions
    cell = cluster.cell.array
    cell_vol = abs(float(np.linalg.det(cell)))

    if cell_vol > 0.1:
        inv_cell = np.linalg.inv(cell)
        fracs = positions @ inv_cell
        fmin = fracs.min(axis=0)
        fmax = fracs.max(axis=0)
        axis_lengths = np.array([np.linalg.norm(cell[i]) for i in range(3)])
        pad_frac = padding / axis_lengths
        fmin -= pad_frac
        fmax += pad_frac
        a, b, c = cell[0], cell[1], cell[2]
        origin = fmin[0] * a + fmin[1] * b + fmin[2] * c
        va = (fmax[0] - fmin[0]) * a
        vb = (fmax[1] - fmin[1]) * b
        vc = (fmax[2] - fmin[2]) * c
    else:
        pmin = positions.min(axis=0) - padding
        pmax = positions.max(axis=0) + padding
        origin = pmin
        va = np.array([pmax[0] - pmin[0], 0.0, 0.0])
        vb = np.array([0.0, pmax[1] - pmin[1], 0.0])
        vc = np.array([0.0, 0.0, pmax[2] - pmin[2]])

    return origin, va, vb, vc


def _add_crystal_box(cluster: Atoms, style: dict) -> bpy.types.Object | None:
    """Create a closed liquid-glass parallelepiped enclosing the cluster atoms."""
    box_style = style.get("crystal_box", {})
    if not box_style.get("enabled", True):
        return None

    padding = float(box_style.get("padding_angstrom", 0.8))
    origin, va, vb, vc = _build_box_vectors(cluster, padding)

    corners = [
        origin,
        origin + va,
        origin + vb,
        origin + vc,
        origin + va + vb,
        origin + va + vc,
        origin + vb + vc,
        origin + va + vb + vc,
    ]
    face_verts = [
        (0, 2, 6, 3),
        (1, 5, 7, 4),
        (0, 3, 5, 1),
        (2, 4, 7, 6),
        (0, 1, 4, 2),
        (3, 6, 7, 5),
    ]

    mesh = bpy.data.meshes.new("crystal_hull")
    bm = bmesh.new()
    verts = [bm.verts.new(tuple(float(x) for x in corner)) for corner in corners]
    bm.verts.ensure_lookup_table()
    for fi in face_verts:
        bm.faces.new([verts[i] for i in fi])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("crystal_hull", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()
    obj.data.materials.append(_make_liquid_glass_material(box_style))
    return obj


def _add_atom(
    position: tuple[float, float, float],
    radius: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=position, segments=32, ring_count=16)
    obj = bpy.context.object
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def _add_bond(
    p0: tuple[float, float, float],
    p1: tuple[float, float, float],
    tube_radius: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    v0 = mathutils.Vector(p0)
    v1 = mathutils.Vector(p1)
    mid = (v0 + v1) / 2
    length = (v1 - v0).length

    bpy.ops.mesh.primitive_cylinder_add(radius=tube_radius, depth=length, location=mid)
    obj = bpy.context.object
    direction = v1 - v0
    rot = direction.to_track_quat("Z", "Y")
    obj.rotation_euler = rot.to_euler()
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def _add_arrow(
    position: tuple[float, float, float],
    color_hex: str = "#e03030",
    shaft_radius: float = 0.07,
    shaft_length: float = 1.3,
    head_radius: float = 0.22,
    head_length: float = 0.50,
) -> None:
    """Add a 3D arrow (cylinder shaft + cone head) pointing up from position."""
    mat = bpy.data.materials.new(name="arrow")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    r, g, b = _hex_to_rgb(color_hex)
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.15
    _set_input(bsdf, "Metallic", 0.75)

    px, py, pz = position
    bpy.ops.mesh.primitive_cylinder_add(
        radius=shaft_radius, depth=shaft_length, location=(px, py, pz + shaft_length / 2)
    )
    shaft = bpy.context.object
    shaft.name = "spin_shaft"
    shaft.data.materials.append(mat)
    bpy.ops.object.shade_smooth()

    bpy.ops.mesh.primitive_cone_add(
        radius1=head_radius, radius2=0.0, depth=head_length,
        location=(px, py, pz + shaft_length + head_length / 2),
    )
    head = bpy.context.object
    head.name = "spin_head"
    head.data.materials.append(mat)
    bpy.ops.object.shade_smooth()


def _add_orbital_ring(
    center_pos: tuple[float, float, float],
    center_radius: float,
    ring_style: dict,
) -> bpy.types.Object | None:
    """Add a metallic torus ring around the defect center, suggesting an orbital."""
    if not ring_style.get("enabled", False):
        return None

    color_hex = ring_style.get("color", "#0077ff")
    tube_radius = float(ring_style.get("tube_radius", 0.07))
    ring_radius = center_radius + float(ring_style.get("ring_radius", 1.5))
    tilt_deg = float(ring_style.get("tilt_deg", 30.0))

    bpy.ops.mesh.primitive_torus_add(
        major_radius=ring_radius,
        minor_radius=tube_radius,
        location=center_pos,
        major_segments=80,
        minor_segments=16,
    )
    obj = bpy.context.object
    obj.name = "orbital_ring"
    obj.rotation_euler = (math.radians(tilt_deg), math.radians(10), math.radians(45))

    mat = bpy.data.materials.new(name="orbital_ring")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    r, g, b = _hex_to_rgb(color_hex)
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.08
    _set_input(bsdf, "Metallic", 0.90)
    _set_input(bsdf, "Specular IOR Level", 1.5)
    _set_input(bsdf, "Specular", 1.0)

    obj.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return obj


def _build_box_mesh(
    cx: float, cy: float, cz: float,
    dx: float, dy: float, dz: float,
    name: str,
) -> bpy.types.Object:
    """Create a rectangular box mesh centered at (cx, cy, cz) with given half-extents."""
    corners = [
        np.array([cx - dx, cy - dy, cz - dz]),
        np.array([cx + dx, cy - dy, cz - dz]),
        np.array([cx - dx, cy + dy, cz - dz]),
        np.array([cx + dx, cy + dy, cz - dz]),
        np.array([cx - dx, cy - dy, cz + dz]),
        np.array([cx + dx, cy - dy, cz + dz]),
        np.array([cx - dx, cy + dy, cz + dz]),
        np.array([cx + dx, cy + dy, cz + dz]),
    ]
    face_verts = [
        (0, 2, 3, 1),
        (4, 5, 7, 6),
        (0, 1, 5, 4),
        (2, 6, 7, 3),
        (0, 4, 6, 2),
        (1, 3, 7, 5),
    ]
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = [bm.verts.new(tuple(float(x) for x in c)) for c in corners]
    bm.verts.ensure_lookup_table()
    for fi in face_verts:
        bm.faces.new([verts[i] for i in fi])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()
    return obj


def _add_nanowire(
    cluster: Atoms, style: dict
) -> tuple[bpy.types.Object | None, float]:
    """Add a Nb nanowire box below the cluster; return (obj, nanowire_bottom_z).

    Dimensions are proportional to the crystal's bounding box, scaled by the
    ratio of cluster_size_Å / 400 nm so the geometry matches the physical device.
    The nanowire runs along the Y-axis (long dimension) in the scene.
    """
    nw_style = style.get("nanowire", {})
    cluster_bottom = float(cluster.positions[:, 2].min())
    if not nw_style.get("enabled", False):
        return None, cluster_bottom

    crystal_size = float((cluster.positions.max(axis=0) - cluster.positions.min(axis=0)).max())
    scale = crystal_size / 400.0  # Å per physical nm

    half_t = 80.0 * scale / 2.0      # Z half-thickness (80 nm)
    half_w = 350.0 * scale / 2.0     # X half-width    (350 nm)
    show_nm = float(nw_style.get("show_depth_nm", 3000.0))
    half_l = show_nm * scale / 2.0   # Y half-length

    cx = float(cluster.positions[:, 0].mean())
    cy = float(cluster.positions[:, 1].mean())
    center_z = cluster_bottom - half_t

    color_hex = nw_style.get("color", "#c8a84b")
    obj = _build_box_mesh(cx, cy, center_z, half_w, half_l, half_t, "nanowire")
    obj.data.materials.append(_make_nb_material(color_hex))
    return obj, center_z - half_t


def _add_substrate(
    nanowire_bottom_z: float,
    cx: float,
    cy: float,
    crystal_size: float,
    style: dict,
) -> bpy.types.Object | None:
    """Add a Si substrate slab below the nanowire."""
    sub_style = style.get("substrate", {})
    if not sub_style.get("enabled", False):
        return None

    scale = crystal_size / 400.0
    thickness_nm = float(sub_style.get("thickness_nm", 300.0))
    half_t = thickness_nm * scale / 2.0

    nw_style = style.get("nanowire", {})
    show_nm = float(nw_style.get("show_depth_nm", 3000.0))
    half_l = show_nm * scale / 2.0
    half_w = 350.0 * scale / 2.0 * 3.0  # substrate 3× wider than nanowire

    center_z = nanowire_bottom_z - half_t

    color_hex = sub_style.get("color", "#a8c8e8")
    obj = _build_box_mesh(cx, cy, center_z, half_w, half_l, half_t, "substrate_si")
    obj.data.materials.append(_make_si_material(color_hex))
    return obj


def _setup_camera(
    cluster: Atoms,
    view: str,
    has_box: bool = True,
    scene_center_override: tuple[float, float, float] | None = None,
    ortho_scale_override: float | None = None,
) -> bpy.types.Object:
    pos = cluster.positions
    extents = float((pos.max(axis=0) - pos.min(axis=0)).max())

    if scene_center_override is not None:
        center = np.array(scene_center_override, dtype=float)
        ortho = ortho_scale_override if ortho_scale_override is not None else extents * 1.55
        distance = ortho * 2.0
    else:
        center = pos.mean(axis=0)
        ortho = extents * (1.55 if has_box else 1.20)
        distance = extents * 2.5 + 5.0

    direction = np.array(_VIEW_DIRECTIONS.get(view, _VIEW_DIRECTIONS["isometric"]), dtype=float)
    direction /= np.linalg.norm(direction)
    cam_location = tuple(center + direction * distance)

    bpy.ops.object.camera_add(location=cam_location)
    cam_obj = bpy.context.object
    cam_obj.name = "cam"
    cam_obj.data.type = "ORTHO"
    cam_obj.data.ortho_scale = ortho

    direction_vec = mathutils.Vector(tuple(center)) - mathutils.Vector(cam_location)
    rot = direction_vec.to_track_quat("-Z", "Y")
    cam_obj.rotation_euler = rot.to_euler()

    bpy.context.scene.camera = cam_obj
    return cam_obj


def _setup_neutral_lighting() -> None:
    bpy.ops.object.light_add(type="SUN", location=(10, -10, 20))
    sun = bpy.context.object
    sun.data.energy = 3.5
    sun.data.angle = 0.08

    bpy.ops.object.light_add(type="AREA", location=(-8, 6, 8))
    fill = bpy.context.object
    fill.data.energy = 1.5
    fill.data.size = 12.0

    bpy.ops.object.light_add(type="SPOT", location=(0, 15, -5))
    rim = bpy.context.object
    rim.data.energy = 4.0
    rim.data.spot_size = 1.2
    rim.data.color = (0.7, 0.85, 1.0)
    direction = mathutils.Vector((0.0, 0.0, 0.0)) - mathutils.Vector((0.0, 15.0, -5.0))
    rim.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _setup_vivid_lighting() -> None:
    """Multi-colored studio rig: warm key, cool fill, bright rim, soft under-glow."""
    bpy.ops.object.light_add(type="SUN", location=(8, -12, 20))
    sun = bpy.context.object
    sun.data.energy = 4.5
    sun.data.angle = 0.05
    sun.data.color = (1.0, 0.96, 0.88)
    direction = mathutils.Vector((0, 0, 0)) - mathutils.Vector((8.0, -12.0, 20.0))
    sun.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    bpy.ops.object.light_add(type="AREA", location=(-14, 5, 8))
    fill = bpy.context.object
    fill.data.energy = 2.5
    fill.data.size = 20.0
    fill.data.color = (0.82, 0.90, 1.0)

    bpy.ops.object.light_add(type="SPOT", location=(0, 18, 5))
    rim = bpy.context.object
    rim.data.energy = 7.0
    rim.data.spot_size = 1.0
    rim.data.color = (0.85, 0.92, 1.0)
    direction = mathutils.Vector((0, 0, 0)) - mathutils.Vector((0.0, 18.0, 5.0))
    rim.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    bpy.ops.object.light_add(type="AREA", location=(0, 0, -12))
    under = bpy.context.object
    under.data.energy = 0.8
    under.data.size = 25.0
    under.data.color = (1.0, 0.88, 0.78)


def _configure_render(output_tiff: Path, width_px: int, height_px: int, style: dict) -> None:
    render_style = style.get("render", {})
    samples = int(render_style.get("samples", 256))

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.max_bounces = 12
    scene.cycles.transmission_bounces = 8
    scene.render.resolution_x = width_px
    scene.render.resolution_y = height_px
    scene.render.image_settings.file_format = "TIFF"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.filepath = str(output_tiff)

    bg_hex = style.get("figure", {}).get("background", "#ffffff")
    if bg_hex in ("white", "#fff", "#ffffff"):
        bg_rgb = (1.0, 1.0, 1.0)
    else:
        bg_rgb = _hex_to_rgb(bg_hex)

    world = scene.world
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    if bg_node:
        bg_node.inputs["Color"].default_value = (*bg_rgb, 1.0)
        bg_node.inputs["Strength"].default_value = 1.0


def build_and_render(
    cluster: Atoms,
    center_index: int,
    camera: str,
    style: dict,
    output_tiff: Path,
    bonds: list[tuple[int, int]] | None = None,
    save_blend: Path | None = None,
) -> None:
    """Build a Blender scene from ASE Atoms and render to a TIFF."""
    _clear_scene()

    atom_colors: dict[str, str] = style.get("atoms", {}).get("colors", {})
    atom_radii: dict[str, float] = style.get("atoms", {}).get("radii", {})
    bond_style = style.get("bonds", {})
    fig_style = style.get("figure", {})
    render_style = style.get("render", {})

    bond_color_hex = bond_style.get("color", "#666666")
    tube_radius = float(bond_style.get("tube_radius", 0.08))
    candy = bool(render_style.get("candy_atoms", False))
    vivid = bool(render_style.get("vivid_lighting", False))

    dpi = int(fig_style.get("dpi", 300))
    width_mm = float(fig_style.get("width_mm", 120))
    height_mm = float(fig_style.get("height_mm", 120))
    width_px = int(width_mm / 25.4 * dpi)
    height_px = int(height_mm / 25.4 * dpi)

    box_enabled = style.get("crystal_box", {}).get("enabled", True)
    _add_crystal_box(cluster, style)

    mat_cache: dict[str, bpy.types.Material] = {}
    for idx, (symbol, pos) in enumerate(zip(cluster.symbols, cluster.positions)):
        color = atom_colors.get(symbol, "#aaaaaa")
        radius = float(atom_radii.get(symbol, 0.4))
        mat_key = symbol
        if mat_key not in mat_cache:
            mat_cache[mat_key] = _make_atom_material(mat_key, color, candy=candy)
        obj = _add_atom(tuple(pos), radius, mat_cache[mat_key])
        obj.name = f"{symbol}_{idx}"

    bond_mat = _make_bond_material(bond_color_hex)
    for i, j in (bonds or []):
        _add_bond(tuple(cluster.positions[i]), tuple(cluster.positions[j]), tube_radius, bond_mat)

    center_pos = tuple(cluster.positions[center_index])
    center_radius = float(atom_radii.get(str(cluster.symbols[center_index]), 0.4))
    arrow_color = style.get("annotations", {}).get("arrow_color", "#e03030")
    _add_arrow(
        position=(center_pos[0], center_pos[1], center_pos[2] + center_radius),
        color_hex=arrow_color,
    )

    ring_style = style.get("orbital_ring", {})
    _add_orbital_ring(center_pos, center_radius, ring_style)

    crystal_size = float((cluster.positions.max(axis=0) - cluster.positions.min(axis=0)).max())
    cx_scene = float(cluster.positions[:, 0].mean())
    cy_scene = float(cluster.positions[:, 1].mean())
    _, nw_bottom = _add_nanowire(cluster, style)
    _add_substrate(nw_bottom, cx_scene, cy_scene, crystal_size, style)

    nw_style = style.get("nanowire", {})
    if nw_style.get("enabled", False):
        scale = crystal_size / 400.0
        show_nm = float(nw_style.get("show_depth_nm", 3000.0))
        nw_l = show_nm * scale
        sub_t = float(style.get("substrate", {}).get("thickness_nm", 300.0)) * scale
        scene_bot = nw_bottom - sub_t
        scene_top = float(cluster.positions[:, 2].max())
        scene_cz = (scene_top + scene_bot) / 2.0
        _setup_camera(
            cluster, camera, has_box=box_enabled,
            scene_center_override=(cx_scene, cy_scene, scene_cz),
            ortho_scale_override=nw_l * 0.9,
        )
    else:
        _setup_camera(cluster, camera, has_box=box_enabled)

    if vivid:
        _setup_vivid_lighting()
    else:
        _setup_neutral_lighting()

    _configure_render(output_tiff, width_px, height_px, style)
    bpy.ops.render.render(write_still=True)

    if save_blend is not None:
        bpy.ops.wm.save_as_mainfile(filepath=str(save_blend))
