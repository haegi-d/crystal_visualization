Ready for review
Select text to add comments on the plan
Plan: Pulse & Magnetic Field Visualization
Context
The scene already has: crystal cluster (Er defect), Nb nanowire below it, Si substrate, a spin arrow (+Z) at the defect, and an orbital ring. We want to add a physics-accurate visualization of three current pulses flowing through the nanowire (i_DC, i_RF, i_MW), their generated circulating B-fields (B_DC, B_RF, B_1), and the external in-plane field B_0. Output is a single static render; labels are SVG annotations post-render.

Color palette:

MW: violet #8E6EA7
RF: yellow #F4D824
DC: teal #2FA895
B-field: navy #2F485F
Six new visual elements
1. Current arrows along nanowire body
Three thin colored arrows (cylinder + cone) running along the nanowire's Y-axis at slight X offsets so all three are visible simultaneously:

i_DC (teal): X offset −small
i_RF (yellow): X offset 0 (center)
i_MW (violet): X offset +small
All arrows point in +Y (same direction). The alternating nature of RF/MW is conveyed by the B-field rings, not these arrows.

2. Waveform glyphs (floating above nanowire +Y end)
3D NURBS POLY curve with bevel_depth (thin tube), placed at Y = cy + half_l, floating above the wire at slightly different X offsets matching the current arrows. Each glyph extends vertically (Z direction) so it faces the isometric camera:

DC: flat-top pulse (rise → plateau → fall), 5 segments
RF: continuous sine wave, ~4 cycles sampled at 60 points
MW: Gaussian-envelope × sine burst, ~4 cycles, sampled at 80 points
3. B-field rings (ellipses in XZ plane)
One per current type, centered on the nanowire cross-section at Y = crystal_cy (the crystal's Y position). Implemented as a POLY curve (64 points) with bevel_depth, closed loop:

Semi-axis X = 1.35 × nanowire_half_x
Semi-axis Z = 1.35 × nanowire_half_z
Each ring offset by ±0.15 Å in Y to avoid z-fighting between the three
Arrow indicators (small _add_arrow-style shaft+cone) tangent to ring at the 12-o'clock position (closest to crystal):

B_DC (teal): one arrow pointing in −X (right-hand rule for current in +Y; field at top of ring points −X)
B_RF (yellow): two opposing arrows: one pointing +X, one −X (alternating current → field reverses)
B_MW (violet): same as RF
4. B_0 arrow
Horizontal arrow in the XY chip-plane. Direction configurable via [pulses.b0] angle_deg in the style TOML (0° = +X). Length configurable. Color: navy #2F485F. Placed at the crystal site, extending outward so it doesn't overlap the spin arrow.

Implementation
New functions in _blender_scene.py
Function	What it does
_make_emissive_material(hex, strength)	Emission shader for glyphs/rings so they glow against the scene
_curve_tube(pts, name, color_hex, bevel_r, closed)	Generic POLY curve with bevel — used for both glyphs and rings
_dc_waveform_pts(n_cycles, height, width)	Returns list of (x,y,z) for a flat-top pulse
_sine_waveform_pts(n_cycles, amplitude, n_pts)	Returns list of (x,y,z) for a continuous sine
_burst_waveform_pts(n_cycles, amplitude, n_pts)	Returns list of (x,y,z) for a Gaussian-envelope sine burst
_ellipse_pts(cx, cy, cz, rx, rz, n)	Returns N points of an ellipse in the XZ plane at Y=cy
_add_tangent_arrow(ring_cx, ring_cz, ring_rx, ring_rz, ring_y, direction, color_hex, scale)	Adds a small arrow tangent to the field ring at 12 o'clock
_add_pulse_visualization(cluster, center_index, style, nw_cx, nw_cy, nw_bottom_z, nw_half_x, nw_half_z, nw_half_l)	Orchestrates all six elements; guarded by style["pulses"]["enabled"]
build_and_render calls _add_pulse_visualization after _add_nanowire / _add_substrate, passing the nanowire geometry parameters that _add_nanowire already computes.

_add_nanowire needs to return (obj, nw_bottom_z, nw_cx, nw_cy, nw_half_x, nw_half_z, nw_half_l) instead of just (obj, bottom_z) — small signature change, handled inside build_and_render.

Config additions (all three style TOMLs)
[pulses]
enabled = false   # set true in vivid.toml to enable

[pulses.b0]
angle_deg = 45.0   # direction in XY plane (0 = +X axis)
length    = 3.5    # visual arrow length in scene Å
color     = "#2F485F"

[pulses.dc]
enabled     = true
color       = "#2FA895"
glyph_scale = 1.0

[pulses.rf]
enabled     = true
color       = "#F4D824"
glyph_scale = 1.0

[pulses.mw]
enabled     = true
color       = "#8E6EA7"
glyph_scale = 1.0
vivid.toml: set [pulses] enabled = true; default.toml and nature.toml: keep enabled = false.

Files to modify
crystal_visualization/backends/_blender_scene.py — all new functions + updated build_and_render + _add_nanowire return value
config/styles/vivid.toml — add [pulses] section with enabled = true
config/styles/default.toml — add [pulses] section with enabled = false
config/styles/nature.toml — add [pulses] section with enabled = false
Verification
Run python scripts/render.py config/styles/vivid.toml with pulses.enabled = true
Use the Blender MCP screenshot tool to check that:
Three current arrows are visible along the nanowire body, colour-coded
Three waveform glyphs (flat-top, sine, burst) appear above the wire's far end
Three elliptical B-field rings encircle the nanowire cross-section at the crystal height
B_DC ring has one tangent arrow; B_RF and B_MW rings each have two opposing arrows
B_0 arrow is horizontal and in-plane
Confirm right-hand rule: for current in +Y, the B_DC arrow at 12 o'clock points in −X
Confirm no z-fighting between the three rings (Y offsets working)
Toggle pulses.enabled = false and verify nothing breaks in a clean render