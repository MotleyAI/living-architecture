"""Every module-rename case of the corpus, run as its one-entry map, reproduces that case's goldens."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from conformance_runner import (
    CASES,
    CROSS,
    TWIN,
    Variant,
    case_args,
    check_case,
    load_case,
    selected,
    variants,
)

MODULE_CASES = [case for case in CASES if case.name.startswith(("refactor-rename-module-", "refactor-ts-rename-module-"))]
RUNS = [
    pytest.param(case_dir, variant, id=f"{case_dir.name}[{variant.id}]")
    for case_dir in MODULE_CASES
    for variant in variants(load_case(case_dir))
    if selected(load_case(case_dir), variant, TWIN, cross=CROSS)
]
ENTRY_OPTIONS = {"--file": "file", "--symbol": "symbol", "--line": "line", "--col": "col", "--offset": "offset",
                 "--new-name": "new_name"}
NUMERIC = {"line", "col", "offset"}


def as_map(args: list[str]) -> tuple[list[str], dict[str, object]]:
    """A `rename` argv as `rename-map <ROOT>/map.yaml` with the same options, and its one entry."""
    at = args.index("rename")
    rest = [str(a) for a in args[at + 1:]]
    entry: dict[str, object] = {}
    options: list[str] = []
    i = 0
    while i < len(rest):
        key = ENTRY_OPTIONS.get(rest[i])
        if key is None:
            options.append(rest[i])
            i += 1
            continue
        entry[key] = int(rest[i + 1]) if key in NUMERIC else rest[i + 1]
        i += 2
    if not NUMERIC & entry.keys() and "symbol" not in entry:
        entry = {"module": entry["file"], "new_name": entry["new_name"]}
    return [*map(str, args[:at]), "rename-map", "<ROOT>/map.yaml", *options], entry


def test_the_corpus_holds_module_rename_cases() -> None:
    assert len(MODULE_CASES) > 20


def test_a_rename_without_a_locator_becomes_a_module_entry() -> None:
    assert as_map(["--apply", "rename", "--file", "pkg/a.py", "--new-name", "b", "--stub", "2.0"]) == (
        ["--apply", "rename-map", "<ROOT>/map.yaml", "--stub", "2.0"], {"module": "pkg/a.py", "new_name": "b"})


def test_a_located_rename_keeps_its_locator() -> None:
    assert as_map(["rename", "--file", "pkg/use.py", "--line", "1", "--col", "17", "--new-name", "b", "--keep", "x"]) == (
        ["rename-map", "<ROOT>/map.yaml", "--keep", "x"], {"file": "pkg/use.py", "line": 1, "col": 17, "new_name": "b"})


def test_the_corpus_holds_typescript_module_rename_cases() -> None:
    typescript = [c for c in MODULE_CASES if "typescript" in load_case(c).get("languages", [])]
    assert len(typescript) > 20


def test_a_typescript_rename_without_a_locator_becomes_a_module_entry() -> None:
    assert as_map(["rename", "--file", "src/a.ts", "--new-name", "b", "--keep", "src/a.ts"]) == (
        ["rename-map", "<ROOT>/map.yaml", "--keep", "src/a.ts"], {"module": "src/a.ts", "new_name": "b"})


@pytest.mark.parametrize(("case_dir", "variant"), RUNS)
def test_a_module_rename_equals_its_one_entry_map(case_dir: Path, variant: Variant, tmp_path: Path) -> None:
    case = load_case(case_dir)
    args, entry = as_map(case_args(case, variant))
    copy = tmp_path / "dr" / "cases" / case_dir.name
    shutil.copytree(case_dir, copy)
    (copy / "case.yaml").write_text(yaml.safe_dump({**case, "args": args}, sort_keys=False), encoding="utf-8")
    root = tmp_path / "run"
    root.mkdir()
    (root / "map.yaml").write_text(yaml.safe_dump([entry], sort_keys=False), encoding="utf-8")
    assert check_case(copy, root, variant=variant) == []
