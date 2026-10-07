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
    normalize,
    render_template,
    snapshot_dir,
    validate,
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
    "schema/node.schema.json",
    "schema/facts.schema.json",
    "schema/conventions-facts.schema.json",
    "findings.yaml",
    "cli.yaml",
    "conventions.yaml",
    "languages.yaml",
    "architecture.yaml",
    "regex-subset.md",
    "scripts/fetch-coderabbit-threads.sh",
    "scripts/fetch-failed-pr-checks.sh",
    "scripts/reply-invalid-coderabbit.sh",
    "scripts/reply-to-pr-thread.sh",
    "scripts/wait-for-reviews.sh",
    "scripts/pr-reviewers.sh",
    "scripts/review-bots.bash",
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


def _schema(name: str) -> dict:
    return json.loads((SHARED / "schema" / f"{name}.schema.json").read_text(encoding="utf-8"))


def test_node_schema_defines_both_node_varieties() -> None:
    defs = _schema("node")["$defs"]
    assert defs["precise"]["required"] == ["package"]
    assert set(defs["precise"]["properties"]) == {"package", "claims", "arc42", "specs"}
    assert set(defs["virtual"]["properties"]) == {"packages", "arc42", "specs"}
    assert defs["precise"]["additionalProperties"] is False
    assert defs["virtual"]["additionalProperties"] is False


@pytest.mark.parametrize(
    ("variety", "metadata", "valid"),
    [
        ("precise", {"package": "p", "claims": ["a"], "arc42": "d.md", "specs": ["s"]}, True),
        ("precise", {"package": ["p"]}, False),
        ("precise", {"package": "p", "claims": "a"}, False),
        ("precise", {"package": "p", "claims": [1]}, False),
        ("precise", {"package": "p", "arc42": ["d.md"]}, False),
        ("precise", {"package": "p", "specs": "s"}, False),
        ("virtual", {"packages": ["a"], "arc42": "d.md", "specs": ["s"]}, True),
        ("virtual", {}, True),
        ("virtual", {"packages": "a"}, False),
        ("virtual", {"packages": [1]}, False),
    ],
)
def test_node_schema_value_types(variety: str, metadata: dict, valid: bool) -> None:
    schema = {"$defs": _schema("node")["$defs"], "$ref": f"#/$defs/{variety}"}
    assert (validate(schema, metadata) == []) is valid


def test_index_schema_does_not_define_nodes() -> None:
    index = _schema("index")
    assert "nodes" not in index["properties"]
    assert index["additionalProperties"] is False


def test_index_schema_keys() -> None:
    index = _schema("index")
    assert set(index["properties"]) == {
        "python", "typescript", "cross_cutting_arc42", "cross_cutting_specs", "legacy_arrows", "diagrams", "view_depth",
    }
    assert set(index["patternProperties"]) == {"^x-"}


_SETTINGS = {"cross_cutting_arc42": [], "cross_cutting_specs": {}, "legacy_arrows": {"baseline": 0}, "diagrams": {},
             "view_depth": {}}


@pytest.mark.parametrize(
    ("document", "valid"),
    [
        ({"python": {"root_package": "pkg"}}, True),
        ({"python": {"root_package": "pkg", "source_root": "python/src"}}, True),
        ({"typescript": {"root_package": "src", "source_root": "node", "tsconfig": "node/tsconfig.json"}}, True),
        ({"python": {"root_package": "pkg"}, "typescript": {"root_package": "src"}, "x-foo": 1, **_SETTINGS}, True),
        ({"python": {"root_package": "pkg"}, "x-guards": {"baseline": 0}}, True),
        ({}, False),
        ({"x-a": 1}, False),
        (_SETTINGS, False),
        ({"root_package": "pkg"}, False),
        ({"python": {"root_package": "pkg"}, "root_package": "pkg"}, False),
        ({"python": {"root_package": "pkg"}, "source_root": "src"}, False),
        ({"python": {"root_package": "pkg"}, "nodes": {}}, False),
        ({"python": {"root_package": "pkg"}, "guards": {"baseline": 0}}, False),
        ({"python": {"root_package": "pkg"}, "rust": {"root_package": "src"}}, False),
        ({"python": {}}, False),
        ({"python": {"root_package": ""}}, False),
        ({"python": {"root_package": "pkg", "tsconfig": "tsconfig.json"}}, False),
        ({"python": {"root_package": "pkg", "extra": 1}}, False),
        ({"typescript": {"root_package": "src", "extra": 1}}, False),
        ({"python": "pkg"}, False),
    ],
)
def test_index_schema_language_sections(document: dict, valid: bool) -> None:
    assert (validate(_schema("index"), document) == []) is valid


@pytest.mark.parametrize("vector", _vectors("facts.yaml")["accept"], ids=lambda v: v["name"])
def test_facts_schema_accepts(vector: dict) -> None:
    assert validate(_schema("facts"), vector["document"]) == []


@pytest.mark.parametrize("vector", _vectors("facts.yaml")["reject"], ids=lambda v: v["name"])
def test_facts_schema_rejects(vector: dict) -> None:
    assert validate(_schema("facts"), vector["document"]) != []


@pytest.mark.parametrize("vector", _vectors("conventions-facts.yaml")["accept"], ids=lambda v: v["name"])
def test_conventions_facts_schema_accepts(vector: dict) -> None:
    assert validate(_schema("conventions-facts"), vector["document"]) == []


@pytest.mark.parametrize("vector", _vectors("conventions-facts.yaml")["reject"], ids=lambda v: v["name"])
def test_conventions_facts_schema_rejects(vector: dict) -> None:
    assert validate(_schema("conventions-facts"), vector["document"]) != []


def test_config_schema_typecheck_commands() -> None:
    typecheck = _schema("living-architecture")["properties"]["commands"]["properties"]["typecheck"]
    defaults = {name: spec.get("default") for name, spec in typecheck["properties"].items()}
    assert defaults == {"python": "basedpyright", "typescript": "tsc --noEmit"}
    assert typecheck["additionalProperties"] is False


@pytest.mark.parametrize(
    ("commands", "valid"),
    [
        ({"typecheck": {"python": "basedpyright -p python"}}, True),
        ({"typecheck": {"typescript": None}}, True),
        ({"typecheck": {}}, True),
        ({"typecheck": "basedpyright"}, False),
        ({"typecheck": {"rust": "cargo check"}}, False),
        ({"typecheck": {"python": 1}}, False),
    ],
)
def test_config_schema_typecheck_values(commands: dict, valid: bool) -> None:
    assert (validate(_schema("living-architecture"), {"commands": commands}) == []) is valid


def test_language_facts() -> None:
    languages = _shared_yaml("languages.yaml")
    python, typescript = languages["python"], languages["typescript"]
    assert (python["local_bin"], python["baseline_file"]) == (".venv/bin", ".basedpyright/baseline.json")
    assert typescript["markers"] == ["tsconfig.json"]
    assert (typescript["files_label"], typescript["comment_prefix"]) == ("TS/JS", "//")
    assert typescript["suppression"] == "// @ts-expect-error — <reason>"
    assert (typescript["local_bin"], typescript["baseline_file"]) == ("node_modules/.bin", ".tsc-baseline.json")
    assert "type_checker" not in python
    assert "type_checker" not in typescript


def test_every_rule_has_a_description_per_language() -> None:
    rules = _shared_yaml("conventions.yaml")["rules"]
    assert {name: sorted(rule["description"]) for name, rule in rules.items()} == {
        name: ["python", "typescript"] for name in rules
    }


def test_config_rules_match_the_conventions_registry() -> None:
    registry = list(_shared_yaml("conventions.yaml")["rules"])
    rules = _schema("living-architecture")["properties"]["conventions"]["properties"]["rules"]
    assert rules["items"]["enum"] == registry
    assert rules["default"] == registry


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


@pytest.mark.parametrize("vector", _vectors("test-files.yaml")["typescript"], ids=lambda v: v["path"])
def test_typescript_test_globs_classify(vector: dict) -> None:
    globs = _shared_yaml("languages.yaml")["typescript"]["test_globs"]
    assert any(glob_match(g, vector["path"]) for g in globs) is vector["test"]


@pytest.mark.parametrize("vector", _vectors("yaml.yaml")["cases"], ids=lambda v: v["name"])
def test_yaml_profile(vector: dict) -> None:
    value = load_yaml(vector["text"])
    if "json" in vector:
        assert value == json.loads(vector["json"])
    else:
        assert canonical_repr(normalize(value)) == vector["repr"]


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
    data = {"reviewers": {"codex": False}}
    materialize_defaults(schema, data)
    assert data == {"reviewers": {"codex": False}}


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


NEW_TEMPLATES = {
    "arch-check.no-language-section":
        "architecture/index.yaml: a language section is required (one of python, typescript)",
    "arch-check.root-undeclared": "model element {element}: top-level elements must be declared language roots",
    "arch-check.root-missing": "model has no root element for declared language {language}",
    "arch-check.metadata-on-root": "model element {element}: language roots may not carry metadata",
    "c4.relation-outside-root": "relation {src} -> {dst} outside every language root",
    "c4.view-unscoped": "view {view} is not scoped to a language root",
    "c4.view-scope-unknown": "view {view} is scoped to {root}, which is not a language root",
    "claims-exist.unit-ambiguous": "claims-exist: {node} claims {unit}, which is ambiguous: {candidates}",
    "claims-exist.child-ambiguous": "claims-exist: element {element} maps to {unit}, which is ambiguous: {candidates}",
    "enforced-tags.unknown-language": "enforced-tags: {doc} tags undeclared language {language!r}",
    "twin.unavailable":
        "the {language} twin (living-architecture {version}) is not reachable; install it with: {install}",
    "twin.facts-invalid":
        "the {language} twin (living-architecture {version}) returned invalid facts; reinstall it with: {install}",
    "twin.forward-refused": "refusing to forward to the {language} twin from a forwarded process (LA_FORWARDED=1)",
    "twin.not-native": "{language} facts are served only by the {language} twin",
    "conventions.ts-import-after-code":
        "static import after other module-level statements; move it to the top of the file",
    "conventions.ts-require-not-top": "require() call outside module scope; use a top-level import or require",
    "conventions.ts-composite-assert":
        "composite `expect(... && ...)` or `assert(... && ...)`; split into separate assertions",
    "conventions.ts-raises-single-throw":
        "`toThrow`/`rejects` assertion makes {calls} calls that can throw; move all but the call under test outside it",
    "conventions.not-utf8": "not valid UTF-8",
    "conventions.unknown-extension": "check-conventions: unknown extension, skipped: {path}",
    "count-comments.unknown-extension": "count-comments: unknown extension, skipped: {path}",
    "typecheck.header": "la-typecheck: checking {language} with {command}",
    "typecheck.new-error": "{file}({line},{col}): error {code}: {message}",
    "typecheck.count": "{file}({line},{col}): error {code}: {message} (baseline {baseline}, now {now})",
    "typecheck.new-errors": "la-typecheck: {language}: {count} new error(s) not in {baseline}",
    "typecheck.shrink": "la-typecheck: {language}: {count} fixed error(s) removed from {baseline}",
    "typecheck.write": "la-typecheck: {language}: wrote {baseline}",
    "typecheck.skip": "la-typecheck: {language}: {baseline} exists, skipped",
    "typecheck.refusal": "la-typecheck: every applicable language already has a baseline; nothing written",
    "typecheck.not-found": "la-typecheck: {language}: {command} not found in {local_bin} or on PATH",
    "typecheck.no-languages":
        "la-typecheck: nothing to check (no language is configured or has source files and a root marker)",
    "typecheck.not-git": "la-typecheck: not inside a git repository",
    "typecheck.global-diagnostic": "la-typecheck: {language}: the checker reported an error without a file",
    "typecheck.checker-failed": "la-typecheck: {language}: {command} exited {code} without a parsable diagnostic",
    "typecheck.baseline-invalid": "la-typecheck: {language}: {baseline} is malformed",
    "typecheck.not-native": "{language} type checks run only in the {language} twin",
    "typecheck.error": "la-typecheck: {error}",
}


@pytest.mark.parametrize(("template_id", "text"), NEW_TEMPLATES.items())
def test_registry_template_text(template_id: str, text: str) -> None:
    assert _shared_yaml("findings.yaml")["findings"].get(template_id) == text


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


PYTHON_ONLY = {"dr-refactor", "dr-compliance", "dr-mock-lint"}


def test_manifest_declares_native_languages() -> None:
    commands = _shared_yaml("cli.yaml")["commands"]
    native = {name: spec["native"] for name, spec in commands.items() if "native" in spec}
    assert native == {name: ["python"] for name in PYTHON_ONLY}


def _option(command: str, name: str) -> dict:
    [option] = [o for o in _shared_yaml("cli.yaml")["commands"][command]["options"] if o["name"] == name]
    return option


@pytest.mark.parametrize(
    ("command", "name", "type_", "choices"),
    [
        ("la-doctor", "--twin", "flag", None),
        ("la-arch-check", "--language", "string", ["python", "typescript"]),
        ("la-arch-check", "--emit", "string", ["facts"]),
        ("la-check-conventions", "--language", "string", ["python", "typescript"]),
        ("la-check-conventions", "--emit", "string", ["facts"]),
        ("la-typecheck", "--language", "string", ["python", "typescript"]),
    ],
)
def test_manifest_internal_options(command: str, name: str, type_: str, choices: list[str] | None) -> None:
    option = _option(command, name)
    assert (option["type"], option.get("choices"), option.get("internal")) == (type_, choices, True)


def test_manifest_declares_la_typecheck() -> None:
    spec = _shared_yaml("cli.yaml")["commands"]["la-typecheck"]
    assert "native" not in spec
    assert not spec.get("passthrough")
    assert set(spec["exit"]) == {0, 1, 2}
    write = _option("la-typecheck", "--write-baseline")
    assert (write["type"], write.get("internal")) == ("flag", None)


def test_only_the_twin_options_are_internal() -> None:
    commands = _shared_yaml("cli.yaml")["commands"]
    specs = [*commands.values(), *(sub for spec in commands.values() for sub in spec.get("subcommands", {}).values())]
    internal = {o["name"] for spec in specs for o in spec.get("options", []) if o.get("internal")}
    assert internal == {"--twin", "--language", "--emit", "--top-level"}


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
