"""The shared contract: vectors, registry coverage, manifest, vendored snapshot and its hash."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

import pytest
import yaml

from living_architecture.contract import (
    canonical_repr,
    compute_hash,
    contract_hash,
    glob_match,
    is_portable_regex,
    load_yaml,
    materialize_defaults,
    render_template,
    snapshot_dir,
)


def _repo_root() -> Path:
    return next(p for p in Path(__file__).resolve().parents if (p / "conformance" / "cases").is_dir())


REPO_ROOT = _repo_root()
SHARED = REPO_ROOT / "shared"
VECTORS = SHARED / "vectors"
CASES = REPO_ROOT / "conformance" / "cases"
BIN_DIR = Path(sys.executable).parent
HASH_FILE = "CONTRACT_HASH"
SHARED_FILES = (
    "schema/living-architecture.schema.json",
    "schema/index.schema.json",
    "findings.yaml",
    "cli.yaml",
    "conventions.yaml",
    "languages.yaml",
    "regex-subset.md",
    "scripts/fetch-coderabbit-threads.sh",
    "scripts/fetch-failed-pr-checks.sh",
    "scripts/reply-invalid-coderabbit.sh",
    "scripts/reply-to-pr-thread.sh",
    "scripts/wait-for-reviews.sh",
)


def _vectors(name: str) -> dict:
    return yaml.safe_load((VECTORS / name).read_text(encoding="utf-8"))


def _shared_yaml(name: str) -> dict:
    return yaml.safe_load((SHARED / name).read_text(encoding="utf-8"))


def _tree(root: Path) -> dict[str, tuple[bool, bytes]]:
    """Relative POSIX path -> (executable, bytes) for every file under `root`, minus the hash file."""
    return {
        p.relative_to(root).as_posix(): (bool(p.stat().st_mode & 0o111), p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != HASH_FILE and "__pycache__" not in p.parts
    }


# ---- shared files and vectors


@pytest.mark.parametrize("rel", SHARED_FILES)
def test_shared_file_exists(rel: str) -> None:
    assert (SHARED / rel).is_file()


@pytest.mark.parametrize("vector", _vectors("repr.yaml")["cases"], ids=lambda v: v["repr"])
def test_canonical_repr(vector: dict) -> None:
    assert canonical_repr(vector["value"]) == vector["repr"]


def test_render_template_repr_of_a_quote() -> None:
    assert render_template("got {value!r}", {"value": "it's"}) == "got \"it's\""


def test_render_template_plain_placeholder() -> None:
    assert render_template("{node} claims {unit}", {"node": "api", "unit": "pkg.api"}) == "api claims pkg.api"


@pytest.mark.parametrize("vector", _vectors("glob.yaml")["cases"], ids=lambda v: f"{v['pattern']}|{v['path']}")
def test_glob_dialect(vector: dict) -> None:
    assert glob_match(vector["pattern"], vector["path"]) is vector["match"]


@pytest.mark.parametrize("vector", _vectors("test-files.yaml")["python"], ids=lambda v: v["path"])
def test_python_test_globs_reproduce_classification(vector: dict) -> None:
    globs = _shared_yaml("languages.yaml")["python"]["test_globs"]
    assert any(glob_match(g, vector["path"]) for g in globs) is vector["test"]


@pytest.mark.parametrize("vector", _vectors("yaml.yaml")["cases"], ids=lambda v: v["name"])
def test_yaml_profile(vector: dict) -> None:
    assert load_yaml(vector["text"]) == json.loads(vector["json"])


@pytest.mark.parametrize("vector", _vectors("defaults.yaml")["cases"], ids=lambda v: v["name"])
def test_default_materialization(vector: dict) -> None:
    schema = json.loads((SHARED / "schema" / "living-architecture.schema.json").read_text(encoding="utf-8"))
    data = None if vector["config"] is None else load_yaml(vector["config"])
    assert materialize_defaults(schema, data) == vector["resolved"]


@pytest.mark.parametrize("vector", _vectors("materialize.yaml")["cases"], ids=lambda v: v["name"])
def test_generic_materialization(vector: dict) -> None:
    assert materialize_defaults(vector["schema"], vector["input"]) == vector["output"]


def test_materialization_does_not_mutate_its_input() -> None:
    schema = json.loads((SHARED / "schema" / "living-architecture.schema.json").read_text(encoding="utf-8"))
    data = {"reviewers": {"coderabbit": True}}
    materialize_defaults(schema, data)
    assert data == {"reviewers": {"coderabbit": True}}


@pytest.mark.parametrize("pattern", _vectors("regex-subset.yaml")["accept"])
def test_portable_regex_accepted(pattern: str) -> None:
    assert is_portable_regex(pattern)


@pytest.mark.parametrize("pattern", _vectors("regex-subset.yaml")["reject"])
def test_non_portable_regex_rejected(pattern: str) -> None:
    assert not is_portable_regex(pattern)


# ---- findings registry


def _template_regex(template: str) -> re.Pattern[str]:
    parts = re.split(r"(?<!\{)\{[a-z_]+(?:!r)?\}(?!\})", template)
    literal = [part.replace("{{", "{").replace("}}", "}") for part in parts]
    return re.compile("[^\n]+?".join(re.escape(part) for part in literal))


def _golden_records() -> list[str]:
    """Each golden file and each `contains` needle, as separate records."""
    records = [p.read_text(encoding="utf-8") for p in CASES.rglob("*") if p.is_file() and p.parent.name != "repo"
               and (p.name.startswith(("stdout", "stderr")) or "files" in p.relative_to(CASES).parts[1:2])]
    for case_file in CASES.glob("*/case.yaml"):
        expect = yaml.safe_load(case_file.read_text(encoding="utf-8"))["expect"]
        for stream in ("stdout", "stderr"):
            if isinstance(expect.get(stream), dict):
                records.extend(expect[stream]["contains"])
    return records


def _produced(template: str, records: list[str]) -> bool:
    pattern = _template_regex(template)
    if "\n" in template:
        return any(pattern.search(record) for record in records)
    return any(pattern.search(line) for record in records for line in record.splitlines())


def test_every_registry_template_is_produced_by_a_golden() -> None:
    records = _golden_records()
    registry = _shared_yaml("findings.yaml")["findings"]
    unproduced = sorted(fid for fid, template in registry.items() if not _produced(template, records))
    assert unproduced == []


# ---- CLI manifest


def _manifest_commands() -> set[str]:
    return set(_shared_yaml("cli.yaml")["commands"])


def test_console_scripts_equal_the_manifest() -> None:
    scripts = {ep.name for ep in entry_points(group="console_scripts") if ep.dist and ep.dist.name == "living-architecture"}
    assert scripts == _manifest_commands()


def test_manifest_declares_the_passthrough_commands() -> None:
    commands = _shared_yaml("cli.yaml")["commands"]
    passthrough = {name for name, spec in commands.items() if spec.get("passthrough")}
    assert passthrough >= {
        "la-count-comments",
        "la-fetch-coderabbit-threads",
        "la-reply-invalid-coderabbit",
        "la-reply-to-pr-thread",
        "la-fetch-failed-pr-checks",
        "la-wait-for-reviews",
    }


# ---- vendored snapshot and contract hash


def test_snapshot_matches_shared() -> None:
    stale = _tree(Path(str(snapshot_dir()))) != _tree(SHARED)
    assert not stale, "the vendored contract snapshot is stale; run scripts/sync-shared"


def test_snapshot_hash_file_matches_the_source_tree() -> None:
    recorded = (Path(str(snapshot_dir())) / HASH_FILE).read_text(encoding="utf-8").strip()
    assert recorded == compute_hash(SHARED) == contract_hash()


def _hash_after(tmp_path: Path, change: str) -> str:
    tree = tmp_path / change
    shutil.copytree(SHARED, tree)
    target = tree / "findings.yaml"
    if change == "bytes":
        target.write_bytes(target.read_bytes() + b"\n")
    elif change == "mode":
        target.chmod(target.stat().st_mode ^ stat.S_IXUSR)
    elif change == "path":
        target.rename(tree / "findings2.yaml")
    return compute_hash(tree)


@pytest.mark.parametrize("change", ["bytes", "mode", "path"])
def test_hash_covers_bytes_modes_and_paths(tmp_path: Path, change: str) -> None:
    assert _hash_after(tmp_path, change) != compute_hash(SHARED)


def test_hash_ignores_non_executable_mode_bits(tmp_path: Path) -> None:
    tree = tmp_path / "copy"
    shutil.copytree(SHARED, tree)
    target = tree / "findings.yaml"
    target.chmod(target.stat().st_mode ^ stat.S_IWGRP)
    assert compute_hash(tree) == compute_hash(SHARED)


def test_hash_ignores_the_hash_file_itself(tmp_path: Path) -> None:
    tree = tmp_path / "copy"
    shutil.copytree(SHARED, tree)
    (tree / HASH_FILE).write_text("anything\n", encoding="utf-8")
    assert compute_hash(tree) == compute_hash(SHARED)


def test_la_doctor_reports_the_contract_hash(tmp_path: Path) -> None:
    proc = subprocess.run(
        [str(BIN_DIR / "la-doctor"), "--contract-hash"], cwd=tmp_path, capture_output=True, text=True, check=False,
        env={**os.environ, "PATH": f"{BIN_DIR}{os.pathsep}{os.environ['PATH']}"},
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == f"{compute_hash(SHARED)}\n"
