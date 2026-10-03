"""Contract helpers beyond the shared vectors: normalization, validation output, data accessors."""

import datetime as dt

import pytest

from living_architecture.contract import (
    canonical_repr,
    language,
    manifest,
    message,
    normalize,
    render_template,
    script_path,
    validate,
)


def test_normalize_maps_yaml_extras_onto_normalized_types() -> None:
    assert normalize(dt.date(2026, 1, 2)) == "2026-01-02"
    assert normalize((1, "a")) == [1, "a"]
    assert normalize({"d": dt.date(2026, 1, 2)}) == {"d": "2026-01-02"}


def test_canonical_repr_rejects_unnormalized_values() -> None:
    value = dt.date(2026, 1, 2)
    with pytest.raises(TypeError):
        canonical_repr(value)


def test_plain_placeholder_renders_non_strings_as_repr() -> None:
    assert render_template("{a} {b} {c}", {"a": 3, "b": None, "c": [1, "x"]}) == "3 None [1, 'x']"


def test_doubled_braces_are_literal() -> None:
    assert render_template("{{x}} {y}", {"y": 1}) == "{x} 1"


def test_message_renders_a_registry_template() -> None:
    assert message("arch-check.summary", count=2) == "arch_check: 2 finding(s)"


def test_validate_names_the_key_path() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "object", "properties": {"b": {"type": "integer"}}}}}
    [error] = validate(schema, {"a": {"b": "x"}})
    assert error.startswith("a.b: ")


def test_validate_valid_is_empty() -> None:
    assert validate({"type": "object"}, {}) == []


@pytest.mark.parametrize("command", sorted(n for n, s in manifest().items() if "script" in s))
def test_every_shim_script_is_bundled(command: str) -> None:
    assert script_path(manifest()[command]["script"]).is_file()


def test_python_language_facts() -> None:
    python = language("python")
    assert python["source_extensions"] == [".py"]
    assert python["comment_prefix"] == "#"


def test_typescript_language_facts() -> None:
    typescript = language("typescript")
    assert typescript["source_extensions"] == [".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]
    assert typescript["test_globs"] == [
        "**/*.test.*", "**/*.spec.*", "**/__tests__/**/*", "**/__mocks__/**/*", "**/tests/**/*", "**/test/**/*",
    ]


@pytest.mark.parametrize(
    ("name", "runner", "install"),
    [
        ("python", "uvx --from living-architecture==0.2.1", "uv tool install living-architecture==0.2.1"),
        ("typescript", "npx -y -p living-architecture@0.2.1", "npm install -g living-architecture@0.2.1"),
    ],
)
def test_twin_runner_and_install_commands(name: str, runner: str, install: str) -> None:
    facts = language(name)
    rendered = (render_template(facts["runner"], {"version": "0.2.1"}), render_template(facts["install"], {"version": "0.2.1"}))
    assert rendered == (runner, install)
