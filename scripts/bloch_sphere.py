"""Generate a Bloch sphere figure showing spin dynamics in the rotating frame.

Vectors shown:
  Δ ∝ B_DC   — blue,  detuning along z'
  Ω₁ ∝ B_mw  — green, microwave Rabi term along y'
  Ω_eff       — tan,   effective field (vector sum of the two above)
  S           — red,   spin state on precession cone around Ω_eff

Usage::

    python scripts/bloch_sphere.py                 # saves bloch_sphere.png
    python scripts/bloch_sphere.py out.pdf         # saves to given path
"""

from __future__ import annotations

import sys

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from mpl_toolkits.mplot3d.proj3d import proj_transform


# ---------------------------------------------------------------------------
# 3-D arrow helper
# ---------------------------------------------------------------------------

class _Arrow3D(FancyArrowPatch):
    """FancyArrowPatch rendered in a 3-D axes."""

    def __init__(self, xs: list, ys: list, zs: list, *args, **kwargs):
        super().__init__((0, 0), (0, 0), *args, **kwargs)
        self._verts3d = xs, ys, zs

    def do_3d_projection(self, renderer=None):  # noqa: ARG002
        xs, ys, zs = proj_transform(*self._verts3d, self.axes.M)
        self.set_positions((xs[0], ys[0]), (xs[1], ys[1]))
        return float(np.min(zs))


def _arrow(ax, p0, p1, color: str, lw: float = 2.2, ms: float = 14) -> None:
    arr = _Arrow3D(
        [p0[0], p1[0]], [p0[1], p1[1]], [p0[2], p1[2]],
        arrowstyle="-|>",
        color=color, lw=lw, mutation_scale=ms,
    )
    ax.add_artist(arr)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _great_circle(normal: list | np.ndarray, n: int = 300):
    """Return (x, y, z) arrays for the great circle with the given normal."""
    n_hat = np.asarray(normal, float)
    n_hat /= np.linalg.norm(n_hat)
    ref = np.array([1.0, 0.0, 0.0]) if abs(n_hat[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(n_hat, ref)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n_hat, e1)
    t = np.linspace(0, 2 * np.pi, n)
    pts = np.cos(t)[:, None] * e1 + np.sin(t)[:, None] * e2
    return pts[:, 0], pts[:, 1], pts[:, 2]


# ---------------------------------------------------------------------------
# Main figure
# ---------------------------------------------------------------------------

def generate_figure(output: str = "bloch_sphere.png") -> None:
    """Draw the Bloch sphere and write it to *output*."""

    fig = plt.figure(figsize=(7, 7), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")
    ax.set_axis_off()
    ax.set_box_aspect([1, 1, 1])
    ax.view_init(elev=15, azim=-50)

    # ------------------------------------------------------------------
    # Sphere surface
    # ------------------------------------------------------------------
    u = np.linspace(0, 2 * np.pi, 120)
    v = np.linspace(0, np.pi, 60)
    xs = np.outer(np.cos(u), np.sin(v))
    ys = np.outer(np.sin(u), np.sin(v))
    zs = np.outer(np.ones_like(u), np.cos(v))
    ax.plot_surface(xs, ys, zs, alpha=0.10, color="lightgray",
                    linewidth=0, shade=True)

    # ------------------------------------------------------------------
    # Great-circle grid
    # ------------------------------------------------------------------
    gc_kw = dict(color="#666666", lw=0.8, alpha=0.50)
    for normal in [
        [0, 0, 1],    # equator
        [1, 0, 0],    # yz meridian
        [0, 1, 0],    # xz meridian
        [1, 1, 0],    # NE–SW diagonal
        [1, -1, 0],   # NW–SE diagonal
        [0, 1, 1],    # tilted meridian
        [0, 1, -1],   # tilted meridian (other direction)
    ]:
        gx, gy, gz = _great_circle(normal)
        ax.plot(gx, gy, gz, **gc_kw)

    # ------------------------------------------------------------------
    # Physics: Ω_eff = Δ ẑ + Ω₁ ŷ  (rotating frame)
    # ------------------------------------------------------------------
    delta = 0.55    # detuning   → z-component
    omega1 = 0.835  # Rabi rate  → y-component
    mag = np.sqrt(delta**2 + omega1**2)
    dz = delta / mag   # normalized z-component
    dy = omega1 / mag  # normalized y-component

    O = np.zeros(3)
    omega_eff_hat = np.array([0.0, dy, dz])   # unit vector along Ω_eff

    # Spin S on precession cone around Ω_eff
    alpha = np.radians(38)   # half-angle of cone
    phi = np.radians(-15)    # phase (rotation around cone, negative pulls S toward viewer)

    e_perp = np.array([1.0, 0.0, 0.0])
    e_perp -= np.dot(e_perp, omega_eff_hat) * omega_eff_hat
    e_perp /= np.linalg.norm(e_perp)
    e2 = np.cross(omega_eff_hat, e_perp)

    s_vec = (np.cos(alpha) * omega_eff_hat
             + np.sin(alpha) * (np.cos(phi) * e_perp + np.sin(phi) * e2))
    s_vec /= np.linalg.norm(s_vec)

    # ------------------------------------------------------------------
    # Dashed precession circle of S around Ω_eff
    # ------------------------------------------------------------------
    t = np.linspace(0, 2 * np.pi, 300)
    prec = (np.cos(alpha) * omega_eff_hat[:, None]
            + np.sin(alpha) * (np.outer(e_perp, np.cos(t))
                               + np.outer(e2, np.sin(t))))
    ax.plot(prec[0], prec[1], prec[2], "--",
            color="#bb3333", lw=1.3, alpha=0.70)

    # ------------------------------------------------------------------
    # Coordinate axes
    # ------------------------------------------------------------------
    ax_len = 1.38
    for d in [[1, 0, 0], [0, 1, 0], [0, 0, 1]]:
        _arrow(ax, O, np.array(d, float) * ax_len, "#555555", lw=1.3, ms=11)

    ax.text(ax_len + 0.09, 0, 0,        "$x'$", fontsize=15, ha="center", va="center", color="#444444")
    ax.text(0, ax_len + 0.09, 0,        "$y'$", fontsize=15, ha="center", va="center", color="#444444")
    ax.text(0, 0,        ax_len + 0.07, "$z'$", fontsize=15, ha="center", va="center", color="#444444")

    # ------------------------------------------------------------------
    # Δ along z' (blue)
    # ------------------------------------------------------------------
    _arrow(ax, O, np.array([0.0, 0.0, dz]), "#3366cc", lw=2.3, ms=14)
    ax.text(-0.20, -0.10, dz * 0.55,
            r"$\Delta \propto B_\mathrm{DC}$",
            color="#3366cc", fontsize=12, ha="right")

    # ------------------------------------------------------------------
    # Ω₁ along y' (green)
    # ------------------------------------------------------------------
    _arrow(ax, O, np.array([0.0, dy, 0.0]), "#447733", lw=2.3, ms=14)
    ax.text(0.05, dy * 0.40, -0.35,
            r"$\Omega_1 \propto B_\mathrm{mw}$",
            color="#447733", fontsize=12, ha="left")

    # ------------------------------------------------------------------
    # Ω_eff field direction – tan/beige arrow (the resultant field vector)
    # ------------------------------------------------------------------
    _arrow(ax, O, omega_eff_hat, "#c8964a", lw=2.3, ms=14)

    # ------------------------------------------------------------------
    # Spin S – red arrow with Ω_eff label and S marker
    # ------------------------------------------------------------------
    _arrow(ax, O, s_vec, "#aa2222", lw=2.3, ms=14)

    mid = s_vec * 0.46
    ax.text(mid[0] + 0.10, mid[1] - 0.04, mid[2] + 0.12,
            r"$\Omega_\mathrm{eff}$",
            color="#aa2222", fontsize=13, ha="left")

    ax.scatter(*s_vec, color="#aa2222", s=40, zorder=10)
    ax.text(s_vec[0] + 0.10, s_vec[1] - 0.04, s_vec[2] + 0.06,
            "$S$", color="#aa2222", fontsize=14, fontweight="bold")

    # ------------------------------------------------------------------
    # Axis limits and output
    # ------------------------------------------------------------------
    lim = 1.12
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(-lim, lim)

    plt.tight_layout(pad=0)
    plt.savefig(output, dpi=200, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    print(f"Saved → {output}")
    plt.show()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "bloch_sphere.png"
    generate_figure(out)
