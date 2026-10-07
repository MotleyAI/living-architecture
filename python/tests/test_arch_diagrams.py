"""c4 diagram generator + parser, and the arch-check's diagrams-fresh check."""

import textwrap
from pathlib import Path

import pytest

from living_architecture import archcheck, c4, cli
from living_architecture.c4.diagrams import _diagrams_map
from living_architecture.contract import check_ids

FIX_CMD = "la-arch-diagrams"
PY_SECTION = "python:\n  root_package: pkg\n"


def arch_only(
    tmp_path: Path, model_text: str, views_text: str | None = None, index_text: str | None = None
) -> Path:
    """Write architecture/model.c4, optional views and an index declaring `python` (plus `index_text`)."""
    (tmp_path / "architecture").mkdir(parents=True)
    (tmp_path / "architecture" / "model.c4").write_text(textwrap.dedent(model_text), encoding="utf-8")
    if views_text is not None:
        (tmp_path / "architecture" / "views.c4").write_text(textwrap.dedent(views_text), encoding="utf-8")
    index = PY_SECTION + textwrap.dedent(index_text or "")
    (tmp_path / "architecture" / "index.yaml").write_text(index, encoding="utf-8")
    return tmp_path


def view_by_id(views, view_id: str):
    return next(v for v in views if v.id == view_id)


def edge_tuples(view):
    return [(e.src, e.dst, e.legacy) for e in view.edges]


# --------------------------------------------------------------------------- parse_model

BASIC_MODEL = """
specification {
  element system
  element node
  element bucket {
    #virtual
  }
  tag virtual
  tag legacy
}
model {
  python = system 'Python' {
    a = node 'Node A'
    b = node 'Node B'
    c = bucket 'Bucket C'
    a -> b
    b -> a #legacy
    a -> c
  }
}
"""


def test_parse_model_elements_in_declaration_order(tmp_path):
    mp = c4.parse_model(arch_only(tmp_path, BASIC_MODEL))
    assert [e.id for e in mp.elements] == ["python", "python.a", "python.b", "python.c"]
    assert [e.title for e in mp.elements] == ["Python", "Node A", "Node B", "Bucket C"]
    assert mp.findings == []


def test_parse_model_virtual_kind_flag(tmp_path):
    mp = c4.parse_model(arch_only(tmp_path, BASIC_MODEL))
    assert {e.id: e.virtual for e in mp.elements} == {
        "python": False,
        "python.a": False,
        "python.b": False,
        "python.c": True,
    }


def test_parse_model_relations_and_legacy(tmp_path):
    mp = c4.parse_model(arch_only(tmp_path, BASIC_MODEL))
    assert [(r.src, r.dst, r.legacy) for r in mp.relations] == [
        ("python.a", "python.b", False),
        ("python.b", "python.a", True),
        ("python.a", "python.c", False),
    ]


def test_parse_model_child_gets_fqn_id_and_parent(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        p = node 'P' {
          kid = node 'K'
        }
        q = node 'Q'
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert {e.id: e.parent for e in mp.elements} == {
        "python": None,
        "python.p": "python",
        "python.p.kid": "python.p",
        "python.q": "python",
    }
    assert mp.findings == []


def test_parse_model_same_leaf_name_under_two_parents_legal(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        p = node 'P' {
          kid = node 'K1'
        }
        q = node 'Q' {
          kid = node 'K2'
        }
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert {e.id for e in mp.elements} == {"python", "python.p", "python.p.kid", "python.q", "python.q.kid"}
    assert mp.findings == []


def test_parse_model_duplicate_child_in_same_parent_is_finding(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        p = node 'P' {
          kid = node 'K'
          kid = node 'K again'
        }
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert mp.findings == ["duplicate element python.p.kid"]


def test_parse_model_dotted_relation_endpoints(tmp_path):
    model = """
    specification { element system  element node  tag legacy }
    model {
      python = system 'Python' {
        p = node 'P' {
          kid = node 'K'
        }
        q = node 'Q'
        p.kid -> q #legacy
        q -> p.kid
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert [(r.src, r.dst, r.legacy) for r in mp.relations] == [
        ("python.p.kid", "python.q", True),
        ("python.q", "python.p.kid", False),
    ]
    assert mp.findings == []


def test_parse_model_unknown_dotted_endpoint_is_finding(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        p = node 'P' {
          kid = node 'K'
        }
        q = node 'Q'
        p.ghost -> q
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert mp.findings == ["relation python.p.ghost -> python.q has unknown endpoint python.p.ghost"]


def test_parse_model_local_child_name_endpoint_is_finding(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        p = node 'P' {
          kid = node 'K'
        }
        q = node 'Q'
        kid -> q
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert mp.findings == ["relation python.kid -> python.q has unknown endpoint python.kid"]


def test_parse_model_unrecognized_model_line_is_finding(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        a = node 'A'
        total garbage here
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert mp.findings


def test_parse_model_unrecognized_specification_line_is_finding(tmp_path):
    model = """
    specification {
      element system
      element node
      total junk here
    }
    model {
      python = system 'Python' {
        a = node 'A'
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert mp.findings


def test_parse_model_relation_in_element_body_is_finding(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        a = node 'A' {
          a -> b
        }
        b = node 'B'
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert mp.findings == ["relation a -> b inside element body python.a"]
    assert mp.relations == []


def test_parse_model_duplicate_element_is_finding(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        a = node 'A'
        a = node 'A again'
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert mp.findings == ["duplicate element python.a"]


def test_parse_model_duplicate_relation_is_finding(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        a = node 'A'
        b = node 'B'
        a -> b
        a -> b
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert mp.findings == ["duplicate relation python.a -> python.b"]


def test_parse_model_unknown_relation_endpoint_is_finding(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        a = node 'A'
        a -> ghost
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert mp.findings == ["relation python.a -> python.ghost has unknown endpoint python.ghost"]


def test_parse_model_undeclared_kind_is_finding(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        a = widget 'A'
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert mp.findings == ["element python.a has undeclared kind widget"]


def test_parse_model_brace_in_title_does_not_corrupt_nesting(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        a = node 'Has } a brace'
        b = node 'B'
        a -> b
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert [e.id for e in mp.elements] == ["python", "python.a", "python.b"]
    assert [(r.src, r.dst) for r in mp.relations] == [("python.a", "python.b")]
    assert mp.findings == []


def test_parse_model_comment_brace_is_ignored(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        a = node 'A'
        // a stray } in a comment
        b = node 'B'
        a -> b
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert [e.id for e in mp.elements] == ["python", "python.a", "python.b"]
    assert mp.findings == []


def test_parse_model_element_trailing_content_is_finding(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        a = node 'A' unexpected junk
        b = node 'B'
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert any("unexpected junk" in f for f in mp.findings)


def test_parse_model_non_virtual_spec_tag_is_finding(tmp_path):
    model = """
    specification {
      element system
      element node {
        #bogus
      }
    }
    model { python = system 'Python' { a = node 'A' } }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert any("bogus" in f for f in mp.findings)


def test_parse_model_spec_element_trailing_content_is_finding(tmp_path):
    model = """
    specification {
      element system
      element node oops
    }
    model { python = system 'Python' { a = node 'A' } }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert any("oops" in f for f in mp.findings)


def test_parse_model_double_hash_virtual_is_finding(tmp_path):
    model = """
    specification {
      element system
      element bucket {
        ##virtual
      }
    }
    model { python = system 'Python' { a = bucket 'A' } }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert any("##virtual" in f for f in mp.findings)
    assert {e.id: e.virtual for e in mp.elements} == {"python": False, "python.a": False}


# --------------------------------------------------------------------------- language roots

TWO_ROOTS_INDEX = "typescript:\n  root_package: src\n"


def test_root_prefixed_endpoint_inside_a_root_is_unknown(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        api = node 'API'
        core = node 'Core'
        python.api -> core
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model))
    assert mp.findings == ["relation python.python.api -> python.core has unknown endpoint python.python.api"]


def test_same_local_ids_under_two_roots_are_two_relations(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        api = node 'API'
        core = node 'Core'
        api -> core
      }
      typescript = system 'TypeScript' {
        api = node 'API'
        core = node 'Core'
        api -> core
      }
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model, index_text=TWO_ROOTS_INDEX))
    assert [(r.src, r.dst) for r in mp.relations] == [
        ("python.api", "python.core"),
        ("typescript.api", "typescript.core"),
    ]
    assert mp.findings == []


def test_relation_outside_every_root_is_a_finding_and_not_recorded(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        api = node 'API'
      }
      typescript = system 'TypeScript' {
        web = node 'Web'
      }
      python.api -> typescript.web
    }
    """
    mp = c4.parse_model(arch_only(tmp_path, model, index_text=TWO_ROOTS_INDEX))
    assert mp.findings == ["relation python.api -> typescript.web outside every language root"]
    assert mp.relations == []


# --------------------------------------------------------------------------- parse_views (ids are root-local)

CHAIN_MODEL = """
specification { element system  element node }
model {
  python = system 'Python' {
    x = node 'X'
    y = node 'Y'
    z = node 'Z'
    x -> y
    y -> z
    z -> x
  }
}
"""

STAR_MODEL = """
specification { element system  element node }
model {
  python = system 'Python' {
    x = node 'X'
    y = node 'Y'
    z = node 'Z'
    x -> y
    x -> z
    y -> z
  }
}
"""

CHILD_MODEL = """
specification { element system  element node }
model {
  python = system 'Python' {
    p = node 'P' {
      kid = node 'K'
    }
    q = node 'Q'
    p -> q
  }
}
"""


def parsed_view(tmp_path, model_text, views_text, view_id):
    root = arch_only(tmp_path, model_text, views_text)
    vp = c4.parse_views(root, c4.parse_model(root))
    return view_by_id(vp.views, view_id), vp.findings


def test_parse_views_include_star(tmp_path):
    v, findings = parsed_view(tmp_path, BASIC_MODEL, "views { view v of python { title 'V' include * } }", "v")
    assert v.node_ids == ["a", "b", "c"]
    assert edge_tuples(v) == [("a", "b", False), ("b", "a", True), ("a", "c", False)]
    assert findings == []


def test_parse_views_star_shows_children_to_depth(tmp_path):
    v, _ = parsed_view(tmp_path, CHILD_MODEL, "views { view v of python { title 'V' include * } }", "v")
    assert v.node_ids == ["p", "p.kid", "q"]
    assert edge_tuples(v) == [("p", "q", False)]


def test_parse_views_include_listed_edges_among_only(tmp_path):
    v, _ = parsed_view(tmp_path, BASIC_MODEL, "views { view v of python { title 'V' include a, b } }", "v")
    assert v.node_ids == ["a", "b"]
    assert edge_tuples(v) == [("a", "b", False), ("b", "a", True)]


def test_parse_views_src_star_predicate(tmp_path):
    v, _ = parsed_view(tmp_path, CHAIN_MODEL, "views { view v of python { title 'V' include x, x -> * } }", "v")
    assert v.node_ids == ["x", "y"]
    assert edge_tuples(v) == [("x", "y", False)]


def test_parse_views_star_dst_predicate(tmp_path):
    v, _ = parsed_view(tmp_path, CHAIN_MODEL, "views { view v of python { title 'V' include x, * -> x } }", "v")
    assert v.node_ids == ["x", "z"]
    assert edge_tuples(v) == [("z", "x", False)]


def test_parse_views_focus_excludes_neighbor_to_neighbor_edges(tmp_path):
    v, _ = parsed_view(tmp_path, STAR_MODEL, "views { view v of python { title 'V' include x, x -> * } }", "v")
    assert v.node_ids == ["x", "y", "z"]
    assert edge_tuples(v) == [("x", "y", False), ("x", "z", False)]
    assert ("y", "z", False) not in edge_tuples(v)


def test_parse_views_stable_dedup_on_repeated_includes(tmp_path):
    views = """
    views {
      view v of python {
        title 'V'
        include x, x -> *
        include x
        include x -> *
      }
    }
    """
    v, _ = parsed_view(tmp_path, STAR_MODEL, views, "v")
    assert v.node_ids == ["x", "y", "z"]
    assert edge_tuples(v) == [("x", "y", False), ("x", "z", False)]


def test_parse_views_multiline_union_equals_single_line(tmp_path):
    views = """
    views {
      view oneline of python { title 'T' include x, x -> * }
      view multiline of python {
        title 'T'
        include x
        include x -> *
      }
    }
    """
    root = arch_only(tmp_path, CHAIN_MODEL, views)
    vp = c4.parse_views(root, c4.parse_model(root))
    one = view_by_id(vp.views, "oneline")
    multi = view_by_id(vp.views, "multiline")
    assert multi.node_ids == one.node_ids
    assert edge_tuples(multi) == edge_tuples(one)


def test_parse_views_unknown_id_is_finding(tmp_path):
    _, findings = parsed_view(tmp_path, CHAIN_MODEL, "views { view v of python { title 'V' include ghost } }", "v")
    assert any("ghost" in f for f in findings)


def test_parse_views_local_child_name_is_finding(tmp_path):
    _, findings = parsed_view(tmp_path, CHILD_MODEL, "views { view v of python { title 'V' include kid } }", "v")
    assert any("kid" in f for f in findings)


def test_parse_views_child_fqn_is_finding(tmp_path):
    _, findings = parsed_view(tmp_path, CHILD_MODEL, "views { view v of python { title 'V' include p.kid } }", "v")
    assert any("p.kid" in f for f in findings)


def test_parse_views_root_prefixed_include_is_finding(tmp_path):
    _, findings = parsed_view(tmp_path, CHILD_MODEL, "views { view v of python { title 'V' include python.p } }", "v")
    assert any("python.p" in f for f in findings)


def test_parse_views_unknown_predicate_anchor_is_finding(tmp_path):
    _, findings = parsed_view(tmp_path, CHAIN_MODEL, "views { view v of python { title 'V' include ghost -> * } }", "v")
    assert any("ghost" in f for f in findings)


def test_parse_views_child_predicate_anchor_is_finding(tmp_path):
    _, findings = parsed_view(tmp_path, CHILD_MODEL, "views { view v of python { title 'V' include p.kid -> * } }", "v")
    assert any("p.kid" in f for f in findings)


def test_parse_views_unsupported_predicate_is_finding(tmp_path):
    _, findings = parsed_view(tmp_path, CHAIN_MODEL, "views { view v of python { title 'V' include x -> y } }", "v")
    assert findings


def test_parse_views_star_to_star_is_finding(tmp_path):
    _, findings = parsed_view(tmp_path, CHAIN_MODEL, "views { view v of python { title 'V' include * -> * } }", "v")
    assert findings


def test_parse_views_unrecognized_line_is_finding(tmp_path):
    views = """
    views {
      view v of python {
        title 'V'
        include *
        bogus directive
      }
    }
    """
    _, findings = parsed_view(tmp_path, CHAIN_MODEL, views, "v")
    assert findings


def test_parse_views_duplicate_view_id_is_finding(tmp_path):
    views = """
    views {
      view dup of python { title 'One' include * }
      view dup of python { title 'Two' include * }
    }
    """
    root = arch_only(tmp_path, CHAIN_MODEL, views)
    vp = c4.parse_views(root, c4.parse_model(root))
    assert any("dup" in f for f in vp.findings)


def test_parse_views_unscoped_view_is_finding(tmp_path):
    root = arch_only(tmp_path, CHAIN_MODEL, "views { view landscape { include * } }")
    vp = c4.parse_views(root, c4.parse_model(root))
    assert "view landscape is not scoped to a language root" in vp.findings


def test_parse_views_scope_on_a_non_root_is_finding(tmp_path):
    root = arch_only(tmp_path, CHILD_MODEL, "views { view v of python.p { title 'V' include * } }")
    vp = c4.parse_views(root, c4.parse_model(root))
    assert "view v is scoped to python.p, which is not a language root" in vp.findings


# --------------------------------------------------------------------------- mermaid emission

EMIT_VIEWS = """
views {
  view whole of python {
    title 'Whole thing'
    include *
  }
  view focus of python {
    title 'A focus'
    include a, a -> *
  }
}
"""


def render(root: Path, view_id: str) -> str:
    """The mermaid block `la-arch-diagrams` writes for `view_id`."""
    doc = root / "architecture" / "d.arc42.md"
    doc.write_text(f"<!-- likec4:{view_id} -->\n<!-- /likec4:{view_id} -->\n", encoding="utf-8")
    index = root / "architecture" / "index.yaml"
    diagrams = f"diagrams:\n  architecture/d.arc42.md: [{view_id}]\n"
    index.write_text(index.read_text(encoding="utf-8") + diagrams, encoding="utf-8")
    c4.generate(root)
    return between(doc.read_text(encoding="utf-8"), view_id)[1:-1]


def test_render_mermaid_shapes_edges_and_legend(tmp_path):
    root = arch_only(tmp_path, BASIC_MODEL, EMIT_VIEWS)
    expected = "\n".join(
        [
            "```mermaid",
            "flowchart TD",
            "  %% whole: Whole thing",
            '  a["Node A"]',
            '  b["Node B"]',
            '  c("Bucket C")',
            "  a --> b",
            "  b -.-> a",
            "  a --> c",
            "```",
            "*Dashed arrows: legacy edges slated to die.*",
        ]
    )
    assert render(root, "whole") == expected


def test_render_mermaid_no_legend_when_no_legacy_edge(tmp_path):
    root = arch_only(tmp_path, BASIC_MODEL, EMIT_VIEWS)
    expected = "\n".join(
        [
            "```mermaid",
            "flowchart TD",
            "  %% focus: A focus",
            '  a["Node A"]',
            '  b["Node B"]',
            '  c("Bucket C")',
            "  a --> b",
            "  a --> c",
            "```",
        ]
    )
    assert render(root, "focus") == expected


def test_render_mermaid_escapes_double_quote_in_title(tmp_path):
    model = """
    specification { element system  element node }
    model {
      python = system 'Python' {
        x = node 'Say "hi"'
      }
    }
    """
    root = arch_only(tmp_path, model, "views { view v of python { title 'V' include * } }")
    expected = "\n".join(
        [
            "```mermaid",
            "flowchart TD",
            "  %% v: V",
            '  x["Say #quot;hi#quot;"]',
            "```",
        ]
    )
    assert render(root, "v") == expected


# --------------------------------------------------------------------------- fixture repo for generate + diagrams-fresh

PYPROJECT = """
[tool.poetry]
name = "fixture"
"""

INDEX_BASE = """
python:
  root_package: pkg
legacy_arrows: {baseline: 1}
cross_cutting_specs:
  queries: {touches: [python.core, python.engine]}
"""

DIAGRAMS_ONE = "diagrams:\n  architecture/system.arc42.md: [land]\n"
INDEX = INDEX_BASE + DIAGRAMS_ONE

MODEL = """
specification {
  element system
  element node
  tag legacy
}
model {
  python = system 'Python' {
    core = node 'Core' {
      metadata {
        package 'pkg.core'
      }
    }
    engine = node 'Engine' {
      metadata {
        package 'pkg.engine'
        arc42 'architecture/engine.arc42.md'
      }
    }
    core -> engine #legacy
    engine -> core
  }
}
"""

VIEWS = """
views {
  view land of python {
    title 'Landscape'
    include *
  }
}
"""

SYSTEM_MD = """
# System

1. One law. [enforced: arch_check:model-truth]
2. Soft rule. [review]

## Diagrams

<!-- likec4:land -->
<!-- /likec4:land -->
"""

SYSTEM_MD_NO_MARKERS = """
# System

1. One law. [enforced: arch_check:model-truth]
2. Soft rule. [review]
"""

ENGINE_MD = "# engine\n"


def index_with(diagrams_block: str) -> str:
    return INDEX_BASE + diagrams_block


def make_repo(
    tmp_path: Path,
    *,
    regenerate: bool = True,
    index: str = INDEX,
    model: str = MODEL,
    views: str = VIEWS,
    system_md: str = SYSTEM_MD,
    engine_md: str = ENGINE_MD,
) -> Path:
    root = tmp_path / "repo"
    files = {
        "pyproject.toml": PYPROJECT,
        "architecture/index.yaml": index,
        "architecture/model.c4": model,
        "architecture/views.c4": views,
        "architecture/system.arc42.md": system_md,
        "architecture/engine.arc42.md": engine_md,
        "openspec/specs/queries/foo/spec.md": "# spec\n",
        "pkg/__init__.py": "",
        "pkg/core/__init__.py": "",
        "pkg/core/a.py": "from pkg.engine import b\n",
        "pkg/engine/__init__.py": "",
        "pkg/engine/b.py": "import pkg.core\n",
    }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")
    if regenerate:
        c4.generate(root)
    return root


def fresh_findings(root: Path) -> list[str]:
    return [f for f in archcheck.run_checks(root) if f.startswith("diagrams-fresh:")]


def between(text: str, view_id: str) -> str:
    return text.split(f"<!-- likec4:{view_id} -->", 1)[1].split(f"<!-- /likec4:{view_id} -->", 1)[0]


# --------------------------------------------------------------------------- generate / marker rewriting


def test_generate_fills_empty_markers(tmp_path):
    root = make_repo(tmp_path, regenerate=False)
    doc = root / "architecture" / "system.arc42.md"
    assert "flowchart TD" not in doc.read_text(encoding="utf-8")
    c4.generate(root)
    text = doc.read_text(encoding="utf-8")
    assert "flowchart TD" in text
    assert "core -.-> engine" in text
    assert "engine --> core" in text
    assert "*Dashed arrows: legacy edges slated to die.*" in text


def test_generate_preserves_surrounding_bytes(tmp_path):
    root = make_repo(tmp_path, regenerate=False)
    doc = root / "architecture" / "system.arc42.md"
    before = doc.read_bytes()
    open_m, close_m = b"<!-- likec4:land -->", b"<!-- /likec4:land -->"
    pre, post = before.split(open_m)[0], before.split(close_m)[1]
    c4.generate(root)
    after = doc.read_bytes()
    assert after.split(open_m)[0] == pre
    assert after.split(close_m)[1] == post


def test_generate_reports_changed_doc_then_is_idempotent(tmp_path):
    root = make_repo(tmp_path, regenerate=False)
    changed = c4.generate(root)
    assert any("system.arc42.md" in c for c in changed)
    assert c4.generate(root) == []


def test_generate_writes_lf_newlines(tmp_path):
    root = make_repo(tmp_path, regenerate=True)
    assert b"\r" not in (root / "architecture" / "system.arc42.md").read_bytes()


VIEWS_TWO = """
views {
  view land of python {
    title 'Landscape'
    include *
  }
  view cview of python {
    title 'Core view'
    include core, core -> *
  }
}
"""

SYSTEM_MD_TWO = """
# System

1. One law. [enforced: arch_check:model-truth]
2. Soft rule. [review]

## Diagrams

<!-- likec4:land -->
<!-- /likec4:land -->

<!-- likec4:cview -->
<!-- /likec4:cview -->
"""


def test_generate_fills_correct_block_per_view(tmp_path):
    index = index_with("diagrams:\n  architecture/system.arc42.md: [land, cview]\n")
    root = make_repo(tmp_path, regenerate=True, index=index, views=VIEWS_TWO, system_md=SYSTEM_MD_TWO)
    text = (root / "architecture" / "system.arc42.md").read_text(encoding="utf-8")
    assert "%% land: Landscape" in between(text, "land")
    assert "%% cview: Core view" in between(text, "cview")
    assert "%% cview" not in between(text, "land")
    assert "%% land" not in between(text, "cview")


def test_generate_errors_on_missing_marker(tmp_path):
    root = make_repo(tmp_path, regenerate=False, system_md=SYSTEM_MD_NO_MARKERS)
    with pytest.raises(ValueError) as exc:
        c4.generate(root)
    assert "land" in str(exc.value)


def test_generate_errors_on_duplicate_markers(tmp_path):
    dup = SYSTEM_MD + "\n<!-- likec4:land -->\n<!-- /likec4:land -->\n"
    root = make_repo(tmp_path, regenerate=False, system_md=dup)
    with pytest.raises(ValueError):
        c4.generate(root)


def test_generate_errors_on_open_without_close(tmp_path):
    system_md = SYSTEM_MD_NO_MARKERS + "\n<!-- likec4:land -->\n"
    root = make_repo(tmp_path, regenerate=False, system_md=system_md)
    with pytest.raises(ValueError):
        c4.generate(root)


def test_generate_errors_on_close_without_open(tmp_path):
    system_md = SYSTEM_MD_NO_MARKERS + "\n<!-- /likec4:land -->\n"
    root = make_repo(tmp_path, regenerate=False, system_md=system_md)
    with pytest.raises(ValueError):
        c4.generate(root)


def test_generate_aborts_when_model_has_findings(tmp_path):
    bad_model = MODEL.replace("    engine -> core\n", "    engine -> core\n    total garbage here\n")
    root = make_repo(tmp_path, regenerate=False, model=bad_model)
    with pytest.raises(ValueError) as exc:
        c4.generate(root)
    assert "total garbage here" in str(exc.value)


def test_generate_raises_on_missing_diagrams_block(tmp_path):
    root = make_repo(tmp_path, regenerate=False, index=INDEX_BASE, system_md=SYSTEM_MD_NO_MARKERS)
    with pytest.raises(ValueError) as exc:
        c4.generate(root)
    assert "diagrams block" in str(exc.value)


def test_generate_rejects_path_traversal_doc_key(tmp_path):
    index = index_with("diagrams:\n  architecture/../evil.arc42.md: [land]\n")
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    with pytest.raises(ValueError) as exc:
        c4.generate(root)
    assert "must be an architecture" in str(exc.value)


def test_main_prints_changed_files(tmp_path, capsys):
    root = make_repo(tmp_path, regenerate=False)
    rc = cli.la_arch_diagrams(["--root", str(root)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "system.arc42.md" in out


def test_main_reports_errors_without_traceback(tmp_path, capsys):
    root = make_repo(tmp_path, regenerate=False)
    (root / "architecture" / "index.yaml").write_text(PY_SECTION, encoding="utf-8")
    assert cli.la_arch_diagrams(["--root", str(root)]) == 1
    assert "no diagrams block" in capsys.readouterr().err


# --------------------------------------------------------------------------- diagrams-fresh through run_checks


def test_diagrams_fresh_in_check_ids():
    assert "diagrams-fresh" in check_ids()


def test_diagrams_fresh_healthy_has_no_findings(tmp_path):
    assert fresh_findings(make_repo(tmp_path)) == []


def test_diagrams_fresh_stale_content_flagged_with_fix_command(tmp_path):
    root = make_repo(tmp_path)
    doc = root / "architecture" / "system.arc42.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace('core["Core"]', 'core["Cor"]'), encoding="utf-8")
    findings = fresh_findings(root)
    assert findings
    assert any(FIX_CMD in f for f in findings)


def test_diagrams_fresh_model_edit_without_regen_flagged(tmp_path):
    root = make_repo(tmp_path)
    model = root / "architecture" / "model.c4"
    model.write_text(model.read_text(encoding="utf-8").replace("core = node 'Core'", "core = node 'Kore'"), encoding="utf-8")
    findings = fresh_findings(root)
    assert findings
    assert any(FIX_CMD in f for f in findings)


def test_diagrams_fresh_title_only_view_edit_flagged(tmp_path):
    root = make_repo(tmp_path)
    views = root / "architecture" / "views.c4"
    views.write_text(views.read_text(encoding="utf-8").replace("title 'Landscape'", "title 'Land'"), encoding="utf-8")
    findings = fresh_findings(root)
    assert findings
    assert any(FIX_CMD in f for f in findings)


def test_diagrams_fresh_missing_marker_flagged(tmp_path):
    root = make_repo(tmp_path, regenerate=False, system_md=SYSTEM_MD_NO_MARKERS)
    assert any("land" in f for f in fresh_findings(root))


def test_diagrams_fresh_orphan_opening_marker_flagged(tmp_path):
    root = make_repo(tmp_path, engine_md="# engine\n\n<!-- likec4:land -->\n")
    assert fresh_findings(root)


def test_diagrams_fresh_orphan_closing_marker_flagged(tmp_path):
    root = make_repo(tmp_path, engine_md="# engine\n\n<!-- /likec4:land -->\n")
    assert fresh_findings(root)


def test_diagrams_fresh_duplicate_marker_pair_flagged(tmp_path):
    dup = SYSTEM_MD + "\n<!-- likec4:land -->\n<!-- /likec4:land -->\n"
    root = make_repo(tmp_path, regenerate=False, system_md=dup)
    assert any("land" in f for f in fresh_findings(root))


def test_diagrams_fresh_mapped_view_missing_flagged(tmp_path):
    root = make_repo(tmp_path, regenerate=False, index=INDEX.replace("[land]", "[ghost]"))
    assert any("ghost" in f for f in fresh_findings(root))


def test_diagrams_fresh_mapped_doc_missing_flagged(tmp_path):
    index = index_with("diagrams:\n  architecture/ghost.arc42.md: [land]\n")
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert any("ghost.arc42.md" in f for f in fresh_findings(root))


def test_diagrams_fresh_schema_value_not_a_list_flagged(tmp_path):
    index = index_with("diagrams:\n  architecture/system.arc42.md: land\n")
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert fresh_findings(root)


def test_diagrams_fresh_schema_non_arc42_key_flagged(tmp_path):
    index = index_with("diagrams:\n  docs/foo.md: [land]\n")
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert any("docs/foo.md" in f for f in fresh_findings(root))


def test_diagrams_fresh_schema_empty_list_flagged(tmp_path):
    index = index_with("diagrams:\n  architecture/system.arc42.md: []\n")
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert fresh_findings(root)


def test_diagrams_fresh_schema_duplicate_view_in_list_flagged(tmp_path):
    index = index_with("diagrams:\n  architecture/system.arc42.md: [land, land]\n")
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert fresh_findings(root)


def test_diagrams_fresh_schema_non_string_entry_flagged(tmp_path):
    index = index_with("diagrams:\n  architecture/system.arc42.md: [123]\n")
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert fresh_findings(root)


def test_diagrams_fresh_schema_empty_view_id_flagged(tmp_path):
    index = index_with("diagrams:\n  architecture/system.arc42.md: ['']\n")
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert fresh_findings(root)


def test_diagrams_fresh_schema_malformed_container_flagged(tmp_path):
    root = make_repo(tmp_path, regenerate=False, index=index_with("diagrams: [a, b]\n"), system_md=SYSTEM_MD_NO_MARKERS)
    assert fresh_findings(root)


def test_diagrams_fresh_parse_error_is_finding_other_checks_still_run(tmp_path):
    bad_views = """
    views {
      view land of python {
        title 'L'
        include ghost -> ghost
      }
    }
    """
    root = make_repo(tmp_path, regenerate=False, views=bad_views)
    (root / "pkg" / "extra.py").write_text("", encoding="utf-8")  # independent failure
    findings = archcheck.run_checks(root)  # must not raise
    assert any(f.startswith("diagrams-fresh:") for f in findings)
    assert any(f.startswith("claims-exactly-once:") for f in findings)


def test_diagrams_fresh_missing_diagrams_block_flagged(tmp_path):
    root = make_repo(tmp_path, regenerate=False, index=INDEX_BASE, system_md=SYSTEM_MD_NO_MARKERS)
    assert any("diagrams block" in f for f in fresh_findings(root))


def test_diagrams_fresh_path_traversal_key_flagged(tmp_path):
    index = index_with("diagrams:\n  architecture/../evil.arc42.md: [land]\n")
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert any("must be an architecture" in f for f in fresh_findings(root))


@pytest.mark.parametrize("content", [None, "", "- a\n- b\n", "just a scalar\n"])
def test_diagrams_map_fails_closed_without_raising(tmp_path, content):
    arch_dir = tmp_path / "architecture"
    arch_dir.mkdir(parents=True)
    if content is not None:
        (arch_dir / "index.yaml").write_text(content, encoding="utf-8")
    assert isinstance(_diagrams_map(tmp_path), str)  # a reason string, never a raise


def test_diagrams_fresh_crlf_block_is_stale(tmp_path):
    root = make_repo(tmp_path)
    doc = root / "architecture" / "system.arc42.md"
    doc.write_bytes(doc.read_bytes().replace(b"\n", b"\r\n"))
    assert any("stale" in f for f in fresh_findings(root))


def test_diagrams_fresh_whitespace_variant_marker_flagged(tmp_path):
    root = make_repo(tmp_path)
    doc = root / "architecture" / "system.arc42.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\n<!--  likec4:land -->\n", encoding="utf-8")
    assert any("land" in f for f in fresh_findings(root))


# --------------------------------------------------------------------------- view depth, roll-up, subgraphs

CHILD_VIEW_MODEL = """
specification { element system  element node  tag legacy }
model {
  python = system 'Python' {
    p = node 'P' {
      kid = node 'Kid'
      kid2 = node 'Kid two'
    }
    q = node 'Q'
    r = node 'R'
    p.kid -> q #legacy
    p.kid2 -> q
    p.kid -> p.kid2
    q -> r
  }
}
"""

DEPTH_MODEL = """
specification { element system  element node }
model {
  python = system 'Python' {
    p = node 'P' {
      kid = node 'Kid' {
        grand = node 'Grand' {
          leaf = node 'Leaf'
        }
      }
    }
    q = node 'Q'
    p.kid.grand.leaf -> q
  }
}
"""

ONE_VIEW = "views { view v of python { title 'V' include * } }"

STYLING_PREFIXES = ("classDef", "class ", "style ", "direction ")


def structural(text: str) -> list[str]:
    """Mermaid lines minus styling/layout directives — the styling pass may tune those freely."""
    return [line for line in text.splitlines() if not line.strip().startswith(STYLING_PREFIXES)]


def depth_view(tmp_path, model_text, index_text, view_id):
    root = arch_only(tmp_path, model_text, ONE_VIEW, index_text=index_text)
    vp = c4.parse_views(root, c4.parse_model(root))
    return view_by_id(vp.views, view_id)


def test_view_depth_default_shows_three_levels(tmp_path):
    v, findings = parsed_view(tmp_path, DEPTH_MODEL, ONE_VIEW, "v")
    assert v.node_ids == ["p", "p.kid", "p.kid.grand", "q"]
    assert edge_tuples(v) == [("p.kid.grand", "q", False)]
    assert findings == []


def test_view_depth_override_collapses_children(tmp_path):
    v = depth_view(tmp_path, DEPTH_MODEL, "view_depth:\n  v: 2\n", "v")
    assert v.node_ids == ["p", "p.kid", "q"]
    assert edge_tuples(v) == [("p.kid", "q", False)]


def test_view_depth_one_reduces_to_node_level(tmp_path):
    v = depth_view(tmp_path, DEPTH_MODEL, "view_depth:\n  v: 1\n", "v")
    assert v.node_ids == ["p", "q"]
    assert edge_tuples(v) == [("p", "q", False)]


def test_rollup_dedupes_and_drops_self_edges(tmp_path):
    v = depth_view(tmp_path, CHILD_VIEW_MODEL, "view_depth:\n  v: 1\n", "v")
    assert v.node_ids == ["p", "q", "r"]
    assert edge_tuples(v) == [("p", "q", False), ("q", "r", False)]


def test_rollup_dashed_iff_all_contributors_legacy(tmp_path):
    model = CHILD_VIEW_MODEL.replace("    p.kid2 -> q\n", "    p.kid2 -> q #legacy\n")
    v = depth_view(tmp_path, model, "view_depth:\n  v: 1\n", "v")
    assert edge_tuples(v) == [("p", "q", True), ("q", "r", False)]


def test_listed_include_expands_children_and_scopes_edges(tmp_path):
    v, _ = parsed_view(tmp_path, CHILD_VIEW_MODEL, "views { view v of python { title 'V' include p, q } }", "v")
    assert v.node_ids == ["p", "p.kid", "p.kid2", "q"]
    assert edge_tuples(v) == [("p.kid", "q", True), ("p.kid2", "q", False), ("p.kid", "p.kid2", False)]


def test_focus_src_predicate_matches_by_top_ancestor(tmp_path):
    v, _ = parsed_view(tmp_path, CHILD_VIEW_MODEL, "views { view v of python { title 'V' include r, p -> * } }", "v")
    assert set(v.node_ids) == {"r", "p", "p.kid", "p.kid2", "q"}
    assert set(edge_tuples(v)) == {("p.kid", "q", True), ("p.kid2", "q", False), ("p.kid", "p.kid2", False)}


def test_focus_dst_predicate_matches_by_top_ancestor(tmp_path):
    v, _ = parsed_view(tmp_path, CHILD_VIEW_MODEL, "views { view v of python { title 'V' include r, * -> q } }", "v")
    assert set(v.node_ids) == {"r", "p", "p.kid", "p.kid2", "q"}
    assert set(edge_tuples(v)) == {("p.kid", "q", True), ("p.kid2", "q", False)}


FOCUS_SUBTREE_MODEL = """
specification { element system  element node }
model {
  python = system 'Python' {
    p = node 'P' {
      kid = node 'Kid'
      kid2 = node 'Kid two'
    }
    q = node 'Q'
    q -> p.kid
  }
}
"""


def test_focus_predicate_pulls_ancestor_chain_not_whole_subtree(tmp_path):
    # `q -> *` matches only q -> p.kid; it pulls p.kid + its ancestor p, never the unrelated p.kid2.
    v, findings = parsed_view(tmp_path, FOCUS_SUBTREE_MODEL, "views { view v of python { title 'V' include q, q -> * } }", "v")
    assert set(v.node_ids) == {"q", "p", "p.kid"}
    assert "p.kid2" not in v.node_ids
    assert edge_tuples(v) == [("q", "p.kid", False)]
    assert findings == []


def test_render_mermaid_subgraphs_golden(tmp_path):
    root = arch_only(tmp_path, CHILD_VIEW_MODEL, ONE_VIEW)
    expected = [
        "```mermaid",
        "flowchart TD",
        "  %% v: V",
        '  subgraph p["P"]',
        '    p__kid["Kid"]',
        '    p__kid2["Kid two"]',
        "  end",
        '  q["Q"]',
        '  r["R"]',
        "  p__kid -.-> q",
        "  p__kid2 --> q",
        "  p__kid --> p__kid2",
        "  q --> r",
        "```",
        "*Dashed arrows: legacy edges slated to die.*",
    ]
    assert structural(render(root, "v")) == expected


def test_render_mermaid_nested_subgraphs_golden(tmp_path):
    root = arch_only(tmp_path, DEPTH_MODEL, ONE_VIEW)
    expected = [
        "```mermaid",
        "flowchart TD",
        "  %% v: V",
        '  subgraph p["P"]',
        '    subgraph p__kid["Kid"]',
        '      p__kid__grand["Grand"]',
        "    end",
        "  end",
        '  q["Q"]',
        "  p__kid__grand --> q",
        "```",
    ]
    assert structural(render(root, "v")) == expected


def test_render_mermaid_subgraph_view_has_classdef_styling(tmp_path):
    root = arch_only(tmp_path, CHILD_VIEW_MODEL, ONE_VIEW)
    assert any(line.strip().startswith("classDef") for line in render(root, "v").splitlines())


def test_render_collapsed_view_matches_classic_emission(tmp_path):
    root = arch_only(tmp_path, DEPTH_MODEL, ONE_VIEW, index_text="view_depth:\n  v: 1\n")
    expected = "\n".join(
        [
            "```mermaid",
            "flowchart TD",
            "  %% v: V",
            '  p["P"]',
            '  q["Q"]',
            "  p --> q",
            "```",
        ]
    )
    assert render(root, "v") == expected


MODEL_WITH_CHILD = """
specification {
  element system
  element node
  tag legacy
}
model {
  python = system 'Python' {
    core = node 'Core' {
      metadata {
        package 'pkg.core'
      }
      query = node 'Query'
    }
    engine = node 'Engine' {
      metadata {
        package 'pkg.engine'
        arc42 'architecture/engine.arc42.md'
      }
    }
    core.query -> engine #legacy
    engine -> core
  }
}
"""


def test_generate_fills_subgraph_blocks(tmp_path):
    root = make_repo(tmp_path, regenerate=False, model=MODEL_WITH_CHILD)
    c4.generate(root)
    text = (root / "architecture" / "system.arc42.md").read_text(encoding="utf-8")
    assert 'subgraph core["Core"]' in text
    assert 'core__query["Query"]' in text
    assert "core__query -.-> engine" in text
    assert "engine --> core" in text
    assert c4.generate(root) == []


def test_diagrams_fresh_child_model_healthy(tmp_path):
    assert fresh_findings(make_repo(tmp_path, model=MODEL_WITH_CHILD)) == []


def test_diagrams_fresh_child_edit_without_regen_flagged(tmp_path):
    root = make_repo(tmp_path, model=MODEL_WITH_CHILD)
    model = root / "architecture" / "model.c4"
    model.write_text(
        model.read_text(encoding="utf-8").replace("query = node 'Query'", "query = node 'Q2'"), encoding="utf-8"
    )
    findings = fresh_findings(root)
    assert findings
    assert any(FIX_CMD in f for f in findings)


def test_view_depth_non_integer_is_finding(tmp_path):
    index = INDEX + "view_depth:\n  land: fish\n"
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert any("view_depth" in f for f in archcheck.run_checks(root))


def test_view_depth_unknown_view_id_is_finding(tmp_path):
    index = INDEX + "view_depth:\n  ghost: 2\n"
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert any("ghost" in f for f in archcheck.run_checks(root))


def test_view_depth_zero_is_finding(tmp_path):
    index = INDEX + "view_depth:\n  land: 0\n"
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert any("view_depth" in f for f in archcheck.run_checks(root))


def test_view_depth_negative_is_finding(tmp_path):
    index = INDEX + "view_depth:\n  land: -1\n"
    root = make_repo(tmp_path, regenerate=False, index=index, system_md=SYSTEM_MD_NO_MARKERS)
    assert any("view_depth" in f for f in archcheck.run_checks(root))


def test_generate_raises_on_malformed_view_depth(tmp_path):
    index = INDEX + "view_depth:\n  land: fish\n"
    root = make_repo(tmp_path, regenerate=False, index=index)
    with pytest.raises(ValueError):
        c4.generate(root)


# --------------------------------------------------------------------------- parser consolidation (task 2.1)


def test_arch_check_dropped_regex_parser():
    for symbol in ("_ELEMENT_RE", "_RELATION_RE", "_parse_elements", "_parse_relations"):
        assert not hasattr(archcheck, symbol)


def test_model_truth_missing_finding_names_module_witness(tmp_path):
    root = make_repo(tmp_path, regenerate=False, model=MODEL.replace("    engine -> core\n", ""))
    assert (
        "model-truth: measured runtime edge python.engine -> python.core is missing from the model"
        " (import pkg.engine.b -> pkg.core)"
    ) in archcheck.run_checks(root)


# --------------------------------------------------------------------------- scoped views

WRAPPED_MODEL = """
specification {
  element system
  element node
  tag legacy
}
model {
  python = system 'Python' {
    core = node 'Core' {
      query = node 'Query' {
        deep = node 'Deep'
      }
    }
    engine = node 'Engine'
    store = node 'Store'
    core.query.deep -> engine #legacy
    engine -> core
    store -> engine
  }
}
"""

WRAPPED_VIEWS = """
views {
  view land of python {
    title 'Landscape'
    include *
  }
  view cview of python {
    title 'Core view'
    include core, core -> *
  }
}
"""

# The same model and views unwrapped (no root, unscoped views), as rendered before roots existed.
UNWRAPPED_DOC = """# S

<!-- likec4:land -->
```mermaid
flowchart TD
  %% land: Landscape
  subgraph core["Core"]
    subgraph core__query["Query"]
      core__query__deep["Deep"]
    end
  end
  engine["Engine"]
  store["Store"]
  core__query__deep -.-> engine
  engine --> core
  store --> engine
  classDef leaf fill:none;
  class core__query__deep,engine,store leaf;
```
*Dashed arrows: legacy edges slated to die.*
<!-- /likec4:land -->

<!-- likec4:cview -->
```mermaid
flowchart TD
  %% cview: Core view
  subgraph core["Core"]
    core__query["Query"]
  end
  engine["Engine"]
  core__query -.-> engine
  classDef leaf fill:none;
  class core__query,engine leaf;
```
*Dashed arrows: legacy edges slated to die.*
<!-- /likec4:cview -->
"""


def test_wrapped_model_renders_byte_identically(tmp_path):
    index = "diagrams:\n  architecture/system.arc42.md: [land, cview]\nview_depth:\n  cview: 2\n"
    root = arch_only(tmp_path, WRAPPED_MODEL, WRAPPED_VIEWS, index_text=index)
    doc = root / "architecture" / "system.arc42.md"
    doc.write_text(
        "# S\n\n<!-- likec4:land -->\n<!-- /likec4:land -->\n\n<!-- likec4:cview -->\n<!-- /likec4:cview -->\n",
        encoding="utf-8",
    )
    c4.generate(root)
    assert doc.read_bytes() == UNWRAPPED_DOC.encode("utf-8")


def test_generate_refuses_an_unscoped_view(tmp_path):
    views = VIEWS.replace("view land of python {", "view land {")
    root = make_repo(tmp_path, regenerate=False, views=views)
    with pytest.raises(c4.DiagramsError) as excinfo:
        c4.generate(root)
    assert "view land is not scoped to a language root" in str(excinfo.value).splitlines()
