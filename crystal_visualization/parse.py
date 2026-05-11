from __future__ import annotations

from pathlib import Path

import ase.io
from ase import Atoms


def load(path: str | Path) -> Atoms:
    """Read a structure file (XYZ, CIF, POSCAR, VESTA-export) and return ASE Atoms."""
    return ase.io.read(str(path))
