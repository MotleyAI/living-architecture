"""Contract helpers beyond the shared vectors: normalization, validation output, data accessors."""

import datetime as dt
import re

import pytest

from living_architecture.contract import (
    canonical_repr,
    config_file,
    findings,
    language,
    local_config_file,
    manifest,
    message,
    normalize,
    render_template,
    schema,
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


def test_validate_resolves_a_cross_file_ref() -> None:
    local = schema("living-architecture.local")
    assert validate(local, {"tracker": "github", "reviewers": {"codex": False}}) == []
    [enum_error] = validate(local, {"tracker": "jira"})
    assert enum_error.startswith("tracker: ")
    [type_error] = validate(local, {"reviewers": {"codex": "yes"}})
    assert type_error.startswith("reviewers.codex: ")


def test_validate_keeps_each_schema_apart_after_a_cross_file_ref() -> None:
    main = schema("living-architecture")
    assert validate(schema("living-architecture.local"), {"tracker": "none"}) == []
    assert validate(main, {"openspec": False}) == []
    assert validate(schema("living-architecture.local"), {"openspec": False}) != []


def test_config_file_names() -> None:
    assert (config_file(), local_config_file()) == ("living-architecture.yaml", "living-architecture.local.yaml")


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


# ---- string-named members: checks, registry forms and templates


@pytest.mark.parametrize(
    ("name", "checks"),
    [
        ("python", ["untyped-def", "unannotated-attr", "explicit-any", "mock", "rope-walk", "attr-blindspot",
                    "string-blindspot"]),
        ("typescript", ["tsconfig", "explicit-any", "untyped-def", "mock", "attr-blindspot", "string-blindspot"]),
    ],
)
def test_string_blindspot_is_a_check_of_both_languages(name: str, checks: list[str]) -> None:
    assert language(name)["compliance_checks"] == checks


def _python_form(call: str) -> dict[str, object]:
    [form] = [f for f in language("python")["string_member_calls"] if f["call"] == call]
    return form


def test_hasattr_is_silent_and_getattr_names_its_default_position() -> None:
    assert _python_form("hasattr").get("silent") is True
    assert _python_form("getattr").get("default") == 2
    others = [f for f in language("python")["string_member_calls"] if f["call"] not in ("hasattr", "getattr")]
    assert [f["call"] for f in others if "silent" in f or "default" in f] == []
    assert "silent" not in _python_form("getattr")
    assert "default" not in _python_form("hasattr")


def test_name_decorators_are_the_pydantic_field_decorators() -> None:
    assert language("python").get("name_decorators") == [
        {"call": "pydantic.field_validator", "module": "pydantic.functional_validators", "qualname": "field_validator"},
        {"call": "pydantic.field_serializer", "module": "pydantic.functional_serializers", "qualname": "field_serializer"},
    ]


def test_name_reads_are_the_pydantic_field_name_attributes_with_their_shapes() -> None:
    assert language("python").get("name_reads") == [
        {"attribute": "model_fields", "module": "pydantic.main", "qualname": "BaseModel.model_fields",
         "shapes": ["subscript", "get", "in"]},
        {"attribute": "model_fields_set", "module": "pydantic.main", "qualname": "BaseModel.model_fields_set",
         "shapes": ["in"]},
    ]


def test_name_class_values_are_slots_and_match_args_with_their_shapes() -> None:
    assert language("python").get("name_class_values") == [
        {"name": "__slots__", "shapes": ["element", "string", "key"]},
        {"name": "__match_args__", "shapes": ["element"]},
    ]


def _placeholders(template_id: str) -> set[str]:
    return set(re.findall(r"\{([a-z_]+)(?:!r)?\}", findings().get(template_id, "")))


@pytest.mark.parametrize(
    ("template_id", "placeholders"),
    [
        ("compliance.string-blindspot", {"path", "line", "site", "receiver", "type", "attr"}),
        ("compliance.string-blindspot-silent", {"path", "line", "site", "receiver", "type", "attr"}),
        ("refactor.unverified-read", {"path", "line", "name", "old", "source_path", "source_line"}),
        ("compliance.attr-required", {"check"}),
    ],
)
def test_string_named_member_templates_take_their_placeholders(template_id: str, placeholders: set[str]) -> None:
    assert template_id in findings()
    assert _placeholders(template_id) == placeholders


SITE = {"path": "pkg/m.py", "receiver": "x", "type": "Any", "attr": "columns"}


@pytest.mark.parametrize(
    ("template_id", "values", "rendered"),
    [
        ("compliance.string-blindspot", {**SITE, "line": 14, "site": "getattr(x, 'columns')"},
         "pkg/m.py:14: string-blindspot: getattr(x, 'columns') — x is Any, so a rename of .columns is unverifiable"),
        ("compliance.string-blindspot-silent", {**SITE, "line": 18, "site": "getattr(x, 'columns', …)"},
         ("pkg/m.py:18: string-blindspot: getattr(x, 'columns', …) — x is Any, so a rename of .columns is unverifiable"
          " and a miss raises no error")),
        ("refactor.unverified-read",
         {"path": "pkg/m.py", "line": 31, "name": "SECTIONS", "old": "columns", "source_path": "pkg/m.py", "source_line": 20},
         ("pkg/m.py:31: unverified-read: SECTIONS holds 'columns', rewritten at pkg/m.py:20; this read is not proven to"
          " name the renamed member")),
        ("compliance.attr-required", {"check": "string-blindspot"}, "--select string-blindspot needs --attr NAME"),
        ("compliance.attr-unselected", {}, "--attr needs attr-blindspot or string-blindspot among the selected checks"),
    ],
    ids=["string-blindspot", "string-blindspot-silent", "unverified-read", "attr-required", "attr-unselected"],
)
def test_string_named_member_templates_render_the_approved_lines(
    template_id: str, values: dict[str, object], rendered: str
) -> None:
    assert template_id in findings()
    assert message(template_id, **values) == rendered


def test_the_new_kinds_are_printed_after_path_and_line() -> None:
    kinds = {m.group(1) for text in findings().values() if (m := re.match(r"\{path\}:\{line\}: ([a-z-]+):", text))}
    assert {"string-blindspot", "unverified-read"} <= kinds


def test_attr_help_names_both_attribute_checks() -> None:
    [option] = [o for o in manifest()["dr-compliance"]["options"] if o["name"] == "--attr"]
    assert {"attr-blindspot", "string-blindspot"} <= set(re.findall(r"[a-z]+-[a-z]+", option["help"]))
