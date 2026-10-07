"""The `.c4` parser's `metadata { }` blocks, and `la-arch-diagrams` on them."""

import textwrap
from pathlib import Path

import pytest

from living_architecture import c4, cli

SPEC = "specification {\n  element system\n  element node\n}\n"
PY_INDEX = "python:\n  root_package: pkg\n"


def parse(tmp_path: Path, model_body: str) -> c4.ModelParse:
    """Parse `model_body` as the children of the `python` root."""
    (tmp_path / "architecture").mkdir(parents=True, exist_ok=True)
    (tmp_path / "architecture" / "index.yaml").write_text(PY_INDEX, encoding="utf-8")
    body = textwrap.indent(textwrap.dedent(model_body), "    ")
    (tmp_path / "architecture" / "model.c4").write_text(
        SPEC + "model {\n  python = system 'Python' {\n" + body + "  }\n}\n", encoding="utf-8"
    )
    return c4.parse_model(tmp_path)


def parents(mp: c4.ModelParse) -> dict[str, str | None]:
    return {e.id: e.parent for e in mp.elements}


def metadata(mp: c4.ModelParse) -> dict[str, dict]:
    return {e.id: e.metadata for e in mp.elements}


# --------------------------------------------------------------------------- well-formed blocks


@pytest.mark.parametrize(
    "body",
    [
        """\
        api = node 'API' {
          metadata {
            package 'pkg.api'
          }
          handlers = node 'Handlers'
          routes = node 'Routes'
        }
        core = node 'Core'
        """,
        """\
        api = node 'API' {
          handlers = node 'Handlers'
          metadata {
            package 'pkg.api'
          }
          routes = node 'Routes'
        }
        core = node 'Core'
        """,
        """\
        api = node 'API' {
          handlers = node 'Handlers'
          routes = node 'Routes'
          metadata {
            package 'pkg.api'
          }
        }
        core = node 'Core'
        """,
    ],
    ids=["before", "between", "after"],
)
def test_metadata_block_keeps_the_nesting(tmp_path, body):
    mp = parse(tmp_path, body)
    assert parents(mp) == {
        "python": None,
        "python.api": "python",
        "python.api.handlers": "python.api",
        "python.api.routes": "python.api",
        "python.core": "python",
    }
    assert metadata(mp)["python.api"] == {"package": "pkg.api"}
    assert mp.findings == []
    assert mp.metadata_findings == []


def test_element_without_metadata_has_none(tmp_path):
    mp = parse(tmp_path, "api = node 'API'\n")
    assert metadata(mp) == {"python": {}, "python.api": {}}


def test_strings_and_arrays(tmp_path):
    mp = parse(
        tmp_path,
        """\
        api = node 'API' {
          metadata {
            package 'pkg.api'
            claims ['pkg.util', 'pkg.misc']
          }
        }
        """,
    )
    assert metadata(mp)["python.api"] == {"package": "pkg.api", "claims": ["pkg.util", "pkg.misc"]}
    assert mp.findings == []


def test_multi_line_array_reads_like_one_line(tmp_path):
    one_line = parse(tmp_path / "a", "api = node 'API' {\n  metadata {\n    claims ['pkg.a', 'pkg.b']\n  }\n}\n")
    split = parse(
        tmp_path / "b",
        """\
        api = node 'API' {
          metadata {
            claims [
              'pkg.a',
              'pkg.b'
            ]
          }
        }
        """,
    )
    assert metadata(split) == metadata(one_line) == {"python": {}, "python.api": {"claims": ["pkg.a", "pkg.b"]}}
    assert split.findings == []
    assert split.metadata_findings == []


def test_one_line_element_with_several_keys(tmp_path):
    mp = parse(tmp_path, "api = node 'API' { metadata { package 'pkg.api'  specs ['api'] } }\ncore = node 'Core'\n")
    assert metadata(mp) == {"python": {}, "python.api": {"package": "pkg.api", "specs": ["api"]}, "python.core": {}}
    assert parents(mp) == {"python": None, "python.api": "python", "python.core": "python"}
    assert mp.findings == []


def test_metadata_values_may_contain_braces_and_comment_markers(tmp_path):
    mp = parse(tmp_path, "api = node 'API' {\n  metadata {\n    arc42 'docs/{x}//y.md' // trailing comment\n  }\n}\n")
    assert metadata(mp)["python.api"] == {"arc42": "docs/{x}//y.md"}
    assert mp.findings == []


def test_parser_records_metadata_on_nested_elements(tmp_path):
    mp = parse(tmp_path, "api = node 'API' {\n  handlers = node 'H' {\n    metadata {\n      package 'x'\n    }\n  }\n}\n")
    assert metadata(mp) == {"python": {}, "python.api": {}, "python.api.handlers": {"package": "x"}}
    assert mp.metadata_findings == []


def test_parser_records_an_empty_block_as_present(tmp_path):
    mp = parse(tmp_path, "api = node 'API' {\n  metadata {\n  }\n  handlers = node 'H'\n}\n")
    assert {e.id: e.has_metadata for e in mp.elements} == {"python": False, "python.api": True, "python.api.handlers": False}
    assert metadata(mp)["python.api"] == {}


# --------------------------------------------------------------------------- malformed blocks

HANDLERS_TREE = {"python": None, "python.api": "python", "python.api.handlers": "python.api", "python.core": "python"}


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ("    package 'pkg.api'\n    package 'pkg.other'\n", ["element python.api has malformed metadata: package 'pkg.other'"]),
        ('    package "pkg.api"\n', ['element python.api has malformed metadata: package "pkg.api"']),
        ("    package pkg.api\n", ["element python.api has malformed metadata: package pkg.api"]),
        ("    claims ['a', ]\n", ["element python.api has malformed metadata: claims ['a', ]"]),
        ("    claims ['a' 'b']\n", ["element python.api has malformed metadata: claims ['a' 'b']"]),
        ("    package\n", ["element python.api has malformed metadata: package"]),
    ],
    ids=["repeated-key", "double-quoted", "unquoted", "trailing-comma", "missing-comma", "no-value"],
)
def test_malformed_line_is_one_metadata_finding(tmp_path, block, expected):
    mp = parse(tmp_path, "api = node 'API' {\n  metadata {\n" + block + "  }\n  handlers = node 'H'\n}\ncore = node 'Core'\n")
    assert mp.metadata_findings == expected
    assert mp.findings == []
    assert parents(mp) == HANDLERS_TREE


def test_second_block_is_one_metadata_finding(tmp_path):
    mp = parse(
        tmp_path,
        """\
        api = node 'API' {
          metadata {
            package 'pkg.api'
          }
          metadata {
            specs ['api']
          }
          handlers = node 'H'
        }
        core = node 'Core'
        """,
    )
    assert mp.metadata_findings == ["element python.api has malformed metadata: metadata {"]
    assert mp.findings == []
    assert parents(mp) == HANDLERS_TREE


def test_unclosed_array_is_one_metadata_finding(tmp_path):
    mp = parse(
        tmp_path,
        """\
        api = node 'API' {
          metadata {
            claims ['pkg.a',
          }
          handlers = node 'H'
        }
        core = node 'Core'
        """,
    )
    assert len(mp.metadata_findings) == 1
    assert mp.metadata_findings[0].startswith("element python.api has malformed metadata: ")
    assert mp.findings == []
    assert parents(mp) == HANDLERS_TREE


def test_duplicate_elements_metadata_is_discarded(tmp_path):
    mp = parse(
        tmp_path,
        "api = node 'API' {\n  metadata {\n    package 'pkg.api'\n  }\n}\n"
        "api = node 'API' {\n  metadata {\n    package 'pkg.other'\n  }\n}\n",
    )
    assert mp.findings == ["duplicate element python.api"]
    assert mp.metadata_findings == []
    assert metadata(mp) == {"python": {}, "python.api": {"package": "pkg.api"}}


def test_malformed_metadata_on_nested_element_names_its_fqn(tmp_path):
    mp = parse(tmp_path, "api = node 'API' {\n  handlers = node 'H' {\n    metadata {\n      package \"x\"\n    }\n  }\n}\n")
    assert mp.metadata_findings == ['element python.api.handlers has malformed metadata: package "x"']
    assert mp.findings == []


# --------------------------------------------------------------------------- la-arch-diagrams

INDEX = "python:\n  root_package: pkg\nlegacy_arrows: {baseline: 0}\ndiagrams:\n  architecture/system.arc42.md: [land]\n"
VIEWS = "views {\n  view land of python {\n    title 'Land'\n    include *\n  }\n}\n"
SYSTEM_MD = "# System\n\n<!-- likec4:land -->\n<!-- /likec4:land -->\n"
PLAIN_MODEL = (
    "model {\n  python = system 'Python' {\n    core = node 'Core' {\n      q = node 'Q'\n    }\n"
    "    engine = node 'Engine'\n    core.q -> engine\n  }\n}\n"
)


def diagrams_repo(tmp_path: Path, model: str) -> Path:
    files = {
        "architecture/index.yaml": INDEX,
        "architecture/views.c4": VIEWS,
        "architecture/system.arc42.md": SYSTEM_MD,
        "architecture/model.c4": SPEC + model,
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path


def test_generate_ignores_well_formed_metadata(tmp_path):
    with_meta = PLAIN_MODEL.replace(
        "    core = node 'Core' {\n", "    core = node 'Core' {\n      metadata {\n        package 'pkg.core'\n        pakage 'x'\n      }\n"
    ).replace("      q = node 'Q'\n", "      q = node 'Q' {\n        metadata {\n          specs ['a']\n        }\n      }\n")
    plain = diagrams_repo(tmp_path / "plain", PLAIN_MODEL)
    meta = diagrams_repo(tmp_path / "meta", with_meta)
    c4.generate(plain)
    c4.generate(meta)
    doc = "architecture/system.arc42.md"
    assert (meta / doc).read_text(encoding="utf-8") == (plain / doc).read_text(encoding="utf-8")


def test_generate_refuses_on_malformed_metadata(tmp_path):
    model = PLAIN_MODEL.replace(
        "    engine = node 'Engine'\n", "    engine = node 'Engine' {\n      metadata {\n        package \"pkg.engine\"\n      }\n    }\n"
    )
    root = diagrams_repo(tmp_path, model)
    with pytest.raises(c4.DiagramsError) as excinfo:
        c4.generate(root)
    assert str(excinfo.value).splitlines()[1:] == ['element python.engine has malformed metadata: package "pkg.engine"']
    assert (root / "architecture" / "system.arc42.md").read_text(encoding="utf-8") == SYSTEM_MD


def test_la_arch_diagrams_exits_1_on_malformed_metadata(tmp_path, capsys):
    model = PLAIN_MODEL.replace(
        "    engine = node 'Engine'\n", "    engine = node 'Engine' {\n      metadata {\n        claims ['a'\n      }\n    }\n"
    )
    root = diagrams_repo(tmp_path, model)
    assert cli.la_arch_diagrams(["--root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "element python.engine has malformed metadata: " in err
    assert "unrecognized model line" not in err
