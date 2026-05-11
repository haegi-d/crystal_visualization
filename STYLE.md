# Coding style

This project is research code intended to be readable by physicists who are not
professional software engineers, reproducible years later, and extensible without
a rewrite. The rules below serve those three goals.

---

## Formatting

- **black**, line length 88. Run before every commit.
- **ruff** for linting (rules: E, F, I — errors, pyflakes, isort).
- Both are configured in `pyproject.toml`; run with `ruff check . && black .`.

## Type hints

Required on all public function signatures. Not required for internal one-liners.

```python
# good
def select_neighbors(atoms: Atoms, center_index: int, cutoff: float) -> Atoms:

# fine for a private helper
def _xyz_to_array(x, y, z):
```

Use `from __future__ import annotations` at the top of each file so forward
references don't need quoting.

## Docstrings

One line maximum. Describe the return value or the non-obvious side effect.
No parameter lists — the type hints cover that. No multi-paragraph blocks.

```python
def load_structure(path: str | Path) -> Atoms:
    """Read a structure file and return an ASE Atoms object."""
```

## Comments

Only write a comment when the **why** is non-obvious. Never describe what the code
does — well-named identifiers already do that.

```python
# good: explains a non-obvious constraint
# KDTree requires float64; ASE may return float32 on some CIF files
positions = atoms.positions.astype(np.float64)

# bad: restates the code
# convert positions to float64
positions = atoms.positions.astype(np.float64)
```

## Functions over classes

Prefer plain functions inside each module. The only class in the public API is
`CrystalRenderer` in `renderer.py`, which is a thin orchestrator over those functions.
Do not add classes for pipeline stages — a function is enough.

## No premature abstractions

Three similar lines of code are better than a helper function invented to avoid
repetition once. Only introduce a helper when the same logic appears in three or more
places, or when naming the concept makes the call site meaningfully clearer.

## Error handling

Only catch exceptions you can handle meaningfully. Do not wrap every call in a
try/except to produce a nicer error message — let exceptions propagate with their
original traceback. Validate at boundaries (file paths, user-provided species names,
cutoff values) and nowhere else.

## Logging

Use `logging.getLogger(__name__)` in library modules. Never use `print()` in
`crystal_visualization/`. Scripts and notebooks may use print freely.

## Naming

- snake_case everywhere; PEP 8.
- Chemical element symbols keep their capitalization: `Er`, `Y`, `O`, not `er`, `y`, `o`.
- File-format names in lowercase: `xyz`, `cif`, `poscar`.
- Style preset names in lowercase: `"nature"`, `"default"`.

## Testing

- **pytest**; one test file per module (`tests/test_parse.py`, `tests/test_select.py`).
- Test functions named `test_<what_is_being_tested>`.
- No mocking of the filesystem — use small fixture files in `tests/fixtures/`.
- No mocking of ASE — ASE is a library, not a service; test against real output.

## Dependencies

- Pin exact versions in `pyproject.toml` for reproducibility.
- Prefer stdlib over third-party for trivial operations (e.g., use `pathlib.Path`
  not a path utility library).
- `bpy` (Blender) is an optional dependency — all imports inside `backends/blender.py`
  must be guarded so the rest of the package imports cleanly without Blender installed.

## Git

- Commit messages: imperative mood, present tense (`add neighbor selection`, not `added`).
- One logical change per commit.
- No binary files in the repo: `.blend`, `.tiff`, `.png`, large structure files
  go in `output/` or `data/` which are gitignored.
