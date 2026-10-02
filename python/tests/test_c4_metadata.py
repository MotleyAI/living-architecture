"""The `.c4` parser's `metadata { }` blocks, and `la-arch-diagrams` on them."""

import textwrap
from pathlib import Path

import pytest

from living_architecture import c4, cli

SPEC = "specification {\n  element node\n}\n"


def parse(tmp_path: Path, model_body: str) -> c4.ModelParse:
    model_dir = tmp_path / "architecture" / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "m.c4").write_text(SPEC + "model {\n" + textwrap.dedent(model_body) + "}\n", encoding="utf-8")
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
    assert parents(mp) == {"api": None, "api.handlers": "api", "api.routes": "api", "core": None}
    assert metadata(mp)["api"] == {"package": "pkg.api"}
    assert mp.findings == []
    assert mp.metadata_findings == []


def test_element_without_metadata_has_none(tmp_path):
    mp = parse(tmp_path, "api = node 'API'\n")
    assert metadata(mp) == {"api": {}}


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
    assert metadata(mp)["api"] == {"package": "pkg.api", "claims": ["pkg.util", "pkg.misc"]}
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
    assert metadata(split) == metadata(one_line) == {"api": {"claims": ["pkg.a", "pkg.b"]}}
    assert split.findings == []
    assert split.metadata_findings == []


def test_one_line_element_with_several_keys(tmp_path):
    mp = parse(tmp_path, "api = node 'API' { metadata { package 'pkg.api'  specs ['api'] } }\ncore = node 'Core'\n")
    assert metadata(mp) == {"api": {"package": "pkg.api", "specs": ["api"]}, "core": {}}
    assert parents(mp) == {"api": None, "core": None}
    assert mp.findings == []


def test_metadata_values_may_contain_braces_and_comment_markers(tmp_path):
    mp = parse(tmp_path, "api = node 'API' {\n  metadata {\n    arc42 'docs/{x}//y.md' // trailing comment\n  }\n}\n")
    assert metadata(mp)["api"] == {"arc42": "docs/{x}//y.md"}
    assert mp.findings == []


def test_parser_records_metadata_on_nested_elements(tmp_path):
    mp = parse(tmp_path, "api = node 'API' {\n  handlers = node 'H' {\n    metadata {\n      package 'x'\n    }\n  }\n}\n")
    assert metadata(mp) == {"api": {}, "api.handlers": {"package": "x"}}
    assert mp.metadata_findings == []


def test_parser_records_an_empty_block_as_present(tmp_path):
    mp = parse(tmp_path, "api = node 'API' {\n  metadata {\n  }\n  handlers = node 'H'\n}\n")
    assert {e.id: e.has_metadata for e in mp.elements} == {"api": True, "api.handlers": False}
    assert metadata(mp)["api"] == {}


# --------------------------------------------------------------------------- malformed blocks


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ("    package 'pkg.api'\n    package 'pkg.other'\n", ["element api has malformed metadata: package 'pkg.other'"]),
        ('    package "pkg.api"\n', ['element api has malformed metadata: package "pkg.api"']),
        ("    package pkg.api\n", ["element api has malformed metadata: package pkg.api"]),
        ("    claims ['a', ]\n", ["element api has malformed metadata: claims ['a', ]"]),
        ("    claims ['a' 'b']\n", ["element api has malformed metadata: claims ['a' 'b']"]),
        ("    package\n", ["element api has malformed metadata: package"]),
    ],
    ids=["repeated-key", "double-quoted", "unquoted", "trailing-comma", "missing-comma", "no-value"],
)
def test_malformed_line_is_one_metadata_finding(tmp_path, block, expected):
    mp = parse(tmp_path, "api = node 'API' {\n  metadata {\n" + block + "  }\n  handlers = node 'H'\n}\ncore = node 'Core'\n")
    assert mp.metadata_findings == expected
    assert mp.findings == []
    assert parents(mp) == {"api": None, "api.handlers": "api", "core": None}


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
    assert mp.metadata_findings == ["element api has malformed metadata: metadata {"]
    assert mp.findings == []
    assert parents(mp) == {"api": None, "api.handlers": "api", "core": None}


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
    assert mp.metadata_findings[0].startswith("element api has malformed metadata: ")
    assert mp.findings == []
    assert parents(mp) == {"api": None, "api.handlers": "api", "core": None}


def test_duplicate_elements_metadata_is_discarded(tmp_path):
    mp = parse(
        tmp_path,
        "api = node 'API' {\n  metadata {\n    package 'pkg.api'\n  }\n}\n"
        "api = node 'API' {\n  metadata {\n    package 'pkg.other'\n  }\n}\n",
    )
    assert mp.findings == ["duplicate element api"]
    assert mp.metadata_findings == []
    assert metadata(mp) == {"api": {"package": "pkg.api"}}


def test_malformed_metadata_on_nested_element_names_its_fqn(tmp_path):
    mp = parse(tmp_path, "api = node 'API' {\n  handlers = node 'H' {\n    metadata {\n      package \"x\"\n    }\n  }\n}\n")
    assert mp.metadata_findings == ['element api.handlers has malformed metadata: package "x"']
    assert mp.findings == []


# --------------------------------------------------------------------------- la-arch-diagrams

INDEX = "root_package: pkg\nlegacy_arrows: {baseline: 0}\ndiagrams:\n  architecture/system.arc42.md: [land]\n"
VIEWS = "views {\n  view land {\n    title 'Land'\n    include *\n  }\n}\n"
SYSTEM_MD = "# System\n\n<!-- likec4:land -->\n<!-- /likec4:land -->\n"
PLAIN_MODEL = "model {\n  core = node 'Core' {\n    q = node 'Q'\n  }\n  engine = node 'Engine'\n  core.q -> engine\n}\n"


def diagrams_repo(tmp_path: Path, model: str) -> Path:
    files = {
        "architecture/index.yaml": INDEX,
        "architecture/views.c4": VIEWS,
        "architecture/system.arc42.md": SYSTEM_MD,
        "architecture/model/m.c4": SPEC + model,
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path


def test_generate_ignores_well_formed_metadata(tmp_path):
    with_meta = PLAIN_MODEL.replace(
        "  core = node 'Core' {\n", "  core = node 'Core' {\n    metadata {\n      package 'pkg.core'\n      pakage 'x'\n    }\n"
    ).replace("    q = node 'Q'\n", "    q = node 'Q' {\n      metadata {\n        specs ['a']\n      }\n    }\n")
    plain = diagrams_repo(tmp_path / "plain", PLAIN_MODEL)
    meta = diagrams_repo(tmp_path / "meta", with_meta)
    c4.generate(plain)
    c4.generate(meta)
    doc = "architecture/system.arc42.md"
    assert (meta / doc).read_text(encoding="utf-8") == (plain / doc).read_text(encoding="utf-8")


def test_generate_refuses_on_malformed_metadata(tmp_path):
    model = PLAIN_MODEL.replace("  engine = node 'Engine'\n", "  engine = node 'Engine' {\n    metadata {\n      package \"pkg.engine\"\n    }\n  }\n")
    root = diagrams_repo(tmp_path, model)
    with pytest.raises(c4.DiagramsError) as excinfo:
        c4.generate(root)
    assert str(excinfo.value).splitlines()[1:] == ['element engine has malformed metadata: package "pkg.engine"']
    assert (root / "architecture" / "system.arc42.md").read_text(encoding="utf-8") == SYSTEM_MD


def test_la_arch_diagrams_exits_1_on_malformed_metadata(tmp_path, capsys):
    model = PLAIN_MODEL.replace("  engine = node 'Engine'\n", "  engine = node 'Engine' {\n    metadata {\n      claims ['a'\n    }\n  }\n")
    root = diagrams_repo(tmp_path, model)
    assert cli.la_arch_diagrams(["--root", str(root)]) == 1
    err = capsys.readouterr().err
    assert "element engine has malformed metadata: " in err
    assert "unrecognized model line" not in err
