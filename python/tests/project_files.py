"""Scratch Python projects for the refactor tests."""

import sys
from pathlib import Path


def file_tree(root: Path) -> dict[str, bytes]:
    """Every file under `root`, by relative path."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def write_project(root: Path, files: dict[str, str], *, venv: bool = True) -> Path:
    """`files` (text kept byte for byte) plus `pkg/__init__.py`; with `venv`, the basedpyright config names this
    interpreter's environment, so pydantic resolves wherever PATH points."""
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    if venv:
        prefix = Path(sys.prefix)
        (root / "pyproject.toml").write_text(
            f'[tool.basedpyright]\nvenvPath = "{prefix.parent}"\nvenv = "{prefix.name}"\n', encoding="utf-8"
        )
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        with open(root / rel, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    return root
