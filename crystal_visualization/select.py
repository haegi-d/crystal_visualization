from __future__ import annotations

import numpy as np
from ase import Atoms
from scipy.spatial import KDTree


def find_defect(atoms: Atoms, species: str, index: int = 0) -> int:
    """Return the atom index of the nth occurrence of the given species."""
    indices = [i for i, s in enumerate(atoms.symbols) if s == species]
    if not indices:
        raise ValueError(f"No atoms of species '{species}' found in structure.")
    if index >= len(indices):
        raise ValueError(
            f"Requested index {index} but only {len(indices)} '{species}' atoms exist."
        )
    return indices[index]


def select_cluster(atoms: Atoms, center_index: int, cutoff: float) -> Atoms:
    """Return the center atom plus all neighbors within cutoff Ångströms."""
    # KDTree requires float64; ASE may return float32 on some CIF files.
    positions = atoms.positions.astype(np.float64)
    tree = KDTree(positions)
    neighbor_indices = tree.query_ball_point(positions[center_index], r=cutoff)
    return atoms[sorted(neighbor_indices)]


def distances_from_center(atoms: Atoms, center_index: int) -> np.ndarray:
    """Return Euclidean distances of all atoms from the atom at center_index."""
    return np.linalg.norm(atoms.positions - atoms.positions[center_index], axis=1)
