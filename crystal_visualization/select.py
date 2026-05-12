from __future__ import annotations

import numpy as np
from ase import Atoms
from ase.geometry import get_distances
from ase.neighborlist import NeighborList, natural_cutoffs


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
    """Return the center atom plus all neighbors within cutoff Ångströms.

    Uses the Minimum Image Convention so periodic structures (CIF/POSCAR)
    are handled correctly. Falls back to Euclidean distance for XYZ files
    where pbc is all-False.
    """
    center = atoms.positions[center_index : center_index + 1]  # (1, 3)
    _, dists = get_distances(center, atoms.positions, cell=atoms.cell, pbc=atoms.pbc)
    indices = np.where(dists[0] <= cutoff)[0]
    return atoms[sorted(indices)]


def get_bonds(atoms: Atoms, mult: float = 1.1) -> list[tuple[int, int]]:
    """Return bonded atom-index pairs using chemistry-aware cutoffs.

    Cutoffs are based on covalent radii sums scaled by mult, so Er-O and Y-O
    bonds are detected at the correct threshold without a single magic number.
    """
    cutoffs = natural_cutoffs(atoms, mult=mult)
    nl = NeighborList(cutoffs, self_interaction=False, bothways=False)
    nl.update(atoms)
    pairs: list[tuple[int, int]] = []
    for i in range(len(atoms)):
        neighbors, _ = nl.get_neighbors(i)
        for j in neighbors:
            if j > i:
                pairs.append((i, int(j)))
    return pairs


def filter_by_bonds(
    cluster: Atoms,
    bonds: list[tuple[int, int]],
    center_index: int,
    trim: dict[str, str],
) -> tuple[Atoms, list[tuple[int, int]], int]:
    """Remove atoms of a species unless they bond to the required partner species.

    Returns the filtered cluster, remapped bond pairs, and the updated center index.
    Example: trim={"O": "Er"} keeps only O atoms that have at least one bond to Er.
    """
    bonded: set[int] = set()
    for i, j in bonds:
        si, sj = cluster[i].symbol, cluster[j].symbol
        for species, partner in trim.items():
            if si == species and sj == partner:
                bonded.add(i)
            if sj == species and si == partner:
                bonded.add(j)

    trimmed_species = set(trim.keys())
    keep = [
        i for i in range(len(cluster))
        if cluster[i].symbol not in trimmed_species or i in bonded
    ]

    new_cluster = cluster[keep]
    old_to_new = {old: new for new, old in enumerate(keep)}
    new_bonds = [
        (old_to_new[i], old_to_new[j])
        for i, j in bonds
        if i in old_to_new and j in old_to_new
    ]
    return new_cluster, new_bonds, old_to_new[center_index]


def distances_from_center(atoms: Atoms, center_index: int) -> np.ndarray:
    """Return distances of all atoms from center_index, respecting PBC."""
    center = atoms.positions[center_index : center_index + 1]
    _, dists = get_distances(center, atoms.positions, cell=atoms.cell, pbc=atoms.pbc)
    return dists[0]
