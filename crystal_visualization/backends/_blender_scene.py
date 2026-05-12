from __future__ import annotations

"""Blender scene construction for crystal cluster renders.

Called only after bpy has been confirmed importable (guard lives in blender.py).
Builds atom spheres and bond cylinders, a liquid-glass crystal box, sets up an
orthographic camera, renders to a transparent TIFF, and optionally saves the
.blend file.
"""

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


def _set_input(node: bpy.types.Node, name: str, value: object) -> None:
    """Set a node input by name, skipping inputs absent in older Blender builds."""
    if name in node.inputs:
        node.inputs[name].default_value = value


def _make_atom_material(name: str, hex_color: str) -> bpy.types.Material:
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    r = int(hex_color[1:3], 16) / 255
    g = int(hex_color[3:5], 16) / 255
    b = int(hex_color[5:7], 16) / 255
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    # Low roughness + high specular gives the glossy plastic look.
    bsdf.inputs["Roughness"].default_value = 0.08
    _set_input(bsdf, "Specular IOR Level", 0.9)  # Blender 4.x
    _set_input(bsdf, "Specular", 0.9)             # Blender 3.x
    _set_input(bsdf, "Subsurface Weight", 0.05)   # Blender 4.x
    _set_input(bsdf, "Subsurface", 0.05)          # Blender 3.x
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

    r = int(hex_color[1:3], 16) / 255
    g = int(hex_color[3:5], 16) / 255
    b = int(hex_color[5:7], 16) / 255

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

    # Fresnel mix: transparent face-on, glowing at glancing angles
    mix = nodes.new("ShaderNodeMixShader")
    mix.location = (500, 0)
    links.new(mix.outputs[0], output.inputs["Surface"])

    layer_weight = nodes.new("ShaderNodeLayerWeight")
    layer_weight.location = (100, 200)
    layer_weight.inputs["Blend"].default_value = 0.25
    links.new(layer_weight.outputs["Facing"], mix.inputs["Fac"])

    # Glass body: full transmission, near-zero roughness, iridescence shimmer
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, -120)
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["IOR"].default_value = ior
    bsdf.inputs["Alpha"].default_value = alpha
    _set_input(bsdf, "Transmission Weight", 1.0)   # Blender 4.x
    _set_input(bsdf, "Transmission", 1.0)          # Blender 3.x
    _set_input(bsdf, "Iridescence", iridescence)
    _set_input(bsdf, "Iridescence IOR", 1.30)
    _set_input(bsdf, "Iridescence Thickness", 600.0)
    links.new(bsdf.outputs["BSDF"], mix.inputs[1])

    # Rim glow: warm white emission at edges via Layer Weight
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
    """Return (origin, va, vb, vc) of the bounding parallelepiped.

    Uses crystal cell axes when the structure has a defined cell, otherwise
    falls back to an axis-aligned bounding box.
    """
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

    # 8 corners indexed as (a-bit, b-bit, c-bit) → 0..7
    corners = [
        origin,           # 000
        origin + va,      # 100
        origin + vb,      # 010
        origin + vc,      # 001
        origin + va + vb, # 110
        origin + va + vc, # 101
        origin + vb + vc, # 011
        origin + va + vb + vc,  # 111
    ]
    # Quads with consistent outward normals
    face_verts = [
        (0, 2, 6, 3),  # -a
        (1, 5, 7, 4),  # +a
        (0, 3, 5, 1),  # -b
        (2, 4, 7, 6),  # +b
        (0, 1, 4, 2),  # -c
        (3, 6, 7, 5),  # +c
    ]

    mesh = bpy.data.meshes.new("crystal_box")
    bm = bmesh.new()
    verts = [bm.verts.new(tuple(float(x) for x in corner)) for corner in corners]
    bm.verts.ensure_lookup_table()
    for fi in face_verts:
        bm.faces.new([verts[i] for i in fi])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("crystal_box", mesh)
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
    shaft_radius: float = 0.06,
    shaft_length: float = 1.2,
    head_radius: float = 0.18,
    head_length: float = 0.45,
) -> None:
    """Add a 3D arrow (cylinder shaft + cone head) pointing up from position."""
    mat = bpy.data.materials.new(name="arrow")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    r = int(color_hex[1:3], 16) / 255
    g = int(color_hex[3:5], 16) / 255
    b = int(color_hex[5:7], 16) / 255
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.2
    _set_input(bsdf, "Metallic", 0.6)

    px, py, pz = position
    shaft_z = pz + shaft_length / 2
    bpy.ops.mesh.primitive_cylinder_add(
        radius=shaft_radius, depth=shaft_length, location=(px, py, shaft_z)
    )
    bpy.context.object.data.materials.append(mat)

    head_z = pz + shaft_length + head_length / 2
    bpy.ops.mesh.primitive_cone_add(
        radius1=head_radius, radius2=0.0, depth=head_length, location=(px, py, head_z)
    )
    bpy.context.object.data.materials.append(mat)


def _setup_camera(cluster: Atoms, view: str) -> bpy.types.Object:
    center = cluster.positions.mean(axis=0)
    pos = cluster.positions
    extents = (pos.max(axis=0) - pos.min(axis=0)).max()
    distance = extents * 2.5 + 5.0

    direction = np.array(_VIEW_DIRECTIONS.get(view, _VIEW_DIRECTIONS["isometric"]), dtype=float)
    direction /= np.linalg.norm(direction)
    cam_location = tuple(center + direction * distance)

    bpy.ops.object.camera_add(location=cam_location)
    cam_obj = bpy.context.object
    cam_obj.data.type = "ORTHO"
    cam_obj.data.ortho_scale = extents * 1.6  # wider to show the box

    direction_vec = mathutils.Vector(cam_location) - mathutils.Vector(tuple(center))
    rot = direction_vec.to_track_quat("-Z", "Y")
    cam_obj.rotation_euler = rot.to_euler()

    bpy.context.scene.camera = cam_obj
    return cam_obj


def _setup_lighting() -> None:
    # Key — warm, high angle
    bpy.ops.object.light_add(type="SUN", location=(10, -10, 20))
    sun = bpy.context.object
    sun.data.energy = 3.5
    sun.data.angle = 0.08

    # Fill — soft opposite side
    bpy.ops.object.light_add(type="AREA", location=(-8, 6, 8))
    fill = bpy.context.object
    fill.data.energy = 1.5
    fill.data.size = 12.0

    # Rim — cold blue back-light; makes the glass edges pop
    bpy.ops.object.light_add(type="SPOT", location=(0, 15, -5))
    rim = bpy.context.object
    rim.data.energy = 4.0
    rim.data.spot_size = 1.2
    rim.data.color = (0.7, 0.85, 1.0)
    direction = mathutils.Vector((0.0, 0.0, 0.0)) - mathutils.Vector((0.0, 15.0, -5.0))
    rim.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _configure_render(output_tiff: Path, width_px: int, height_px: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 256           # glass needs more samples to converge
    scene.cycles.max_bounces = 12
    scene.cycles.transmission_bounces = 8
    scene.render.resolution_x = width_px
    scene.render.resolution_y = height_px
    scene.render.image_settings.file_format = "TIFF"
    # Standalone bpy wheel silently zeroes the alpha channel when film_transparent
    # is True, making compositing produce a blank image.  Use an opaque white
    # background instead; the SVG annotation layer is composited on top regardless.
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.filepath = str(output_tiff)
    world = scene.world
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    if bg_node:
        bg_node.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
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
    """Build a Blender scene from ASE Atoms and render to a transparent TIFF."""
    _clear_scene()

    atom_colors: dict[str, str] = style.get("atoms", {}).get("colors", {})
    atom_radii: dict[str, float] = style.get("atoms", {}).get("radii", {})
    bond_style = style.get("bonds", {})
    fig_style = style.get("figure", {})

    bond_color_hex = bond_style.get("color", "#666666")
    tube_radius = bond_style.get("tube_radius", 0.08)

    dpi = fig_style.get("dpi", 300)
    width_mm = fig_style.get("width_mm", 120)
    height_mm = fig_style.get("height_mm", 120)
    width_px = int(width_mm / 25.4 * dpi)
    height_px = int(height_mm / 25.4 * dpi)

    # Box first so Cycles sorts it behind opaque atoms in the depth pass
    _add_crystal_box(cluster, style)

    mat_cache: dict[str, bpy.types.Material] = {}
    for idx, (symbol, pos) in enumerate(zip(cluster.symbols, cluster.positions)):
        color = atom_colors.get(symbol, "#aaaaaa")
        radius = atom_radii.get(symbol, 0.4)
        mat_key = f"{symbol}_{idx == center_index}"
        if mat_key not in mat_cache:
            mat_cache[mat_key] = _make_atom_material(mat_key, color)
        _add_atom(tuple(pos), radius, mat_cache[mat_key])

    bond_mat = _make_atom_material("bond", bond_color_hex)
    for i, j in (bonds or []):
        _add_bond(tuple(cluster.positions[i]), tuple(cluster.positions[j]), tube_radius, bond_mat)

    center_pos = tuple(cluster.positions[center_index])
    center_radius = atom_radii.get(str(cluster.symbols[center_index]), 0.4)
    arrow_style = style.get("annotations", {})
    arrow_color = arrow_style.get("arrow_color", "#e03030")
    _add_arrow(
        position=(center_pos[0], center_pos[1], center_pos[2] + center_radius),
        color_hex=arrow_color,
    )

    _setup_camera(cluster, camera)
    _setup_lighting()
    _configure_render(output_tiff, width_px, height_px)

    bpy.ops.render.render(write_still=True)

    if save_blend is not None:
        bpy.ops.wm.save_as_mainfile(filepath=str(save_blend))
