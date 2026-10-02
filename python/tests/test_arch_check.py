"""arch_check cross-walk checks against tmp-dir repo fixtures."""

import textwrap
from pathlib import Path

import pytest

from living_architecture import archcheck, c4, cli
from living_architecture.contract import check_ids

INDEX = """
root_package: pkg
legacy_arrows: {baseline: 1}
cross_cutting_specs:
  queries: {touches: [core, engine]}
diagrams:
  architecture/system.arc42.md: [land]
"""

MODEL = """
specification {
  element node
  tag legacy
}
model {
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
"""

VIEWS = """
views {
  view land {
    title 'Landscape'
    include *
  }
}
"""

SYSTEM_MD = (
    "# System\n\n1. One law. [enforced: arch_check:model-truth]\n2. Soft rule. [review]\n\n"
    "<!-- likec4:land -->\n<!-- /likec4:land -->\n"
)

BASE_FILES = {
    "architecture/index.yaml": INDEX,
    "architecture/model/pkg.c4": MODEL,
    "architecture/views.c4": VIEWS,
    "architecture/system.arc42.md": SYSTEM_MD,
    "architecture/engine.arc42.md": "# engine\n",
    "openspec/specs/queries/foo/spec.md": "# spec\n",
    "pkg/__init__.py": "",
    "pkg/core/__init__.py": "",
    "pkg/core/a.py": "from pkg.engine import b\n",
    "pkg/engine/__init__.py": "",
    "pkg/engine/b.py": "import pkg.core\n",
}

CHILD_INDEX = """
root_package: pkg
legacy_arrows: {baseline: 1}
cross_cutting_specs:
  queries: {touches: [core, engine]}
diagrams:
  architecture/system.arc42.md: [land]
"""

CHILD_MODEL = """
specification {
  element node
  tag legacy
}
model {
  core = node 'Core' {
    metadata {
      package 'pkg.core'
    }
    query = node 'Query'
    models = node 'Models'
  }
  engine = node 'Engine' {
    metadata {
      package 'pkg.engine'
      arc42 'architecture/engine.arc42.md'
    }
    syntax = node 'Syntax'
  }
  core.query -> engine.syntax #legacy
  core.query -> core.models
  engine -> core
}
"""

CHILD_FILES = {
    "architecture/index.yaml": CHILD_INDEX,
    "architecture/model/pkg.c4": CHILD_MODEL,
    "architecture/views.c4": VIEWS,
    "architecture/system.arc42.md": SYSTEM_MD,
    "architecture/engine.arc42.md": "# engine\n",
    "openspec/specs/queries/foo/spec.md": "# spec\n",
    "pkg/__init__.py": "",
    "pkg/core/__init__.py": "",
    "pkg/core/query.py": "from pkg.engine.syntax import parse\nfrom pkg.core.models import Model\n",
    "pkg/core/models.py": "",
    "pkg/engine/__init__.py": "",
    "pkg/engine/syntax.py": "parse = 1\n",
    "pkg/engine/b.py": "import pkg.core\n",
}

GRAND_INDEX = """
root_package: pkg
legacy_arrows: {baseline: 0}
cross_cutting_specs:
  queries: {touches: [core, engine]}
diagrams:
  architecture/system.arc42.md: [land]
"""

GRAND_MODEL = """
specification {
  element node
  tag legacy
}
model {
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
    syntax = node 'Syntax' {
      deep = node 'Deep'
    }
  }
  core.query -> engine.syntax.deep
  engine -> core
}
"""

GRAND_FILES = {
    "architecture/index.yaml": GRAND_INDEX,
    "architecture/model/pkg.c4": GRAND_MODEL,
    "architecture/views.c4": VIEWS,
    "architecture/system.arc42.md": SYSTEM_MD,
    "architecture/engine.arc42.md": "# engine\n",
    "openspec/specs/queries/foo/spec.md": "# spec\n",
    "pkg/__init__.py": "",
    "pkg/core/__init__.py": "",
    "pkg/core/query.py": "import pkg.engine.syntax.deep\n",
    "pkg/engine/__init__.py": "",
    "pkg/engine/syntax/__init__.py": "",
    "pkg/engine/syntax/deep.py": "",
    "pkg/engine/syntax/shallow.py": "",
    "pkg/engine/b.py": "import pkg.core\n",
}


MODEL_REL = "architecture/model/pkg.c4"
CORE_PKG = "      package 'pkg.core'\n"
ENGINE_ARC42 = "      arc42 'architecture/engine.arc42.md'\n"


def write_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")
    c4.generate(root)  # fill the diagram marker block so the fixture is fresh
    return root


def make_repo(tmp_path: Path) -> Path:
    return write_repo(tmp_path, BASE_FILES)


def make_child_repo(tmp_path: Path, *, index: str = CHILD_INDEX, model: str = CHILD_MODEL) -> Path:
    files = {**CHILD_FILES, "architecture/index.yaml": index, "architecture/model/pkg.c4": model}
    return write_repo(tmp_path, files)


def make_grandchild_repo(tmp_path: Path) -> Path:
    return write_repo(tmp_path, GRAND_FILES)


def findings_for(root: Path, check_id: str) -> list[str]:
    return [f for f in archcheck.run_checks(root) if f.startswith(f"{check_id}:")]


def edit(root: Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{rel}: edit target not found: {old!r}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def append(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


# --------------------------------------------------------------------------- node-level fixture (reduction)


def test_healthy_fixture_passes(tmp_path):
    assert archcheck.run_checks(make_repo(tmp_path)) == []


def test_unclaimed_top_level_module(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "extra.py").write_text("", encoding="utf-8")
    assert any("pkg.extra" in f for f in findings_for(root, "claims-exactly-once"))


def test_duplicate_claim(tmp_path):
    root = make_repo(tmp_path)
    edit(root, MODEL_REL, CORE_PKG, CORE_PKG + "      claims ['pkg.engine']\n")
    assert any("pkg.engine" in f for f in findings_for(root, "claims-exactly-once"))


def test_claimed_module_missing_on_disk(tmp_path):
    root = make_repo(tmp_path)
    edit(root, MODEL_REL, CORE_PKG, CORE_PKG + "      claims ['pkg.ghost']\n")
    assert any("pkg.ghost" in f for f in findings_for(root, "claims-exist"))


def test_missing_arc42_file(tmp_path):
    root = make_repo(tmp_path)
    (root / "architecture" / "engine.arc42.md").unlink()
    assert findings_for(root, "arc42-exists")


def test_unknown_touches_node(tmp_path):
    root = make_repo(tmp_path)
    edit(root, "architecture/index.yaml", "[core, engine]", "[core, ghost]")
    assert any("ghost" in f for f in findings_for(root, "spec-mapping"))


def test_unmapped_spec_group(tmp_path):
    root = make_repo(tmp_path)
    extra = root / "openspec" / "specs" / "models" / "bar" / "spec.md"
    extra.parent.mkdir(parents=True)
    extra.write_text("# spec\n", encoding="utf-8")
    assert any("models" in f for f in findings_for(root, "spec-mapping"))


def test_spec_group_without_spec_md(tmp_path):
    root = make_repo(tmp_path)
    (root / "openspec" / "specs" / "queries" / "foo" / "spec.md").unlink()
    assert any("no spec.md" in f for f in findings_for(root, "spec-mapping"))


def test_node_removed_from_model_claims_nothing(tmp_path):
    root = make_repo(tmp_path)
    edit(root, MODEL_REL, "  engine = node 'Engine' {\n    metadata {\n      package 'pkg.engine'\n" + ENGINE_ARC42 + "    }\n  }\n", "")
    edit(root, MODEL_REL, "  core -> engine #legacy\n  engine -> core\n", "")
    assert "claims-exactly-once: top-level pkg.engine is claimed by no node" in archcheck.run_checks(root)


def test_top_level_element_without_metadata_is_a_setup_error(tmp_path):
    root = make_repo(tmp_path)
    edit(root, MODEL_REL, "  core -> engine #legacy\n", "  ghost = node 'Ghost'\n  core -> engine #legacy\n")
    with pytest.raises(archcheck.ArchCheckError, match=r"model element ghost: .*package"):
        archcheck.run_checks(root)


def test_modeled_relation_without_measured_edge(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text("", encoding="utf-8")
    assert any("engine -> core" in f for f in findings_for(root, "model-truth"))


def test_measured_edge_missing_from_model(tmp_path):
    root = make_repo(tmp_path)
    edit(root, "architecture/model/pkg.c4", "  engine -> core\n", "")
    assert any("engine -> core" in f for f in findings_for(root, "model-truth"))


def test_missing_edge_finding_names_module_witness(tmp_path):
    root = make_repo(tmp_path)
    edit(root, "architecture/model/pkg.c4", "  engine -> core\n", "")
    assert (
        "model-truth: measured runtime edge engine -> core is missing from the model"
        " (import pkg.engine.b -> pkg.core)"
    ) in archcheck.run_checks(root)


def test_dead_relation_finding_text_unchanged(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text("", encoding="utf-8")
    assert "model-truth: modeled relation engine -> core has no measured runtime edge" in archcheck.run_checks(root)


def test_type_checking_import_is_not_an_edge(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text(
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import pkg.core\n", encoding="utf-8"
    )
    assert any("engine -> core" in f for f in findings_for(root, "model-truth"))


def test_aliased_typing_type_checking_attr_is_not_an_edge(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text(
        "import typing as t\nif t.TYPE_CHECKING:\n    import pkg.core\n", encoding="utf-8"
    )
    assert any("engine -> core" in f for f in findings_for(root, "model-truth"))


def test_attribute_target_does_not_kill_typing_alias(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text(
        "import typing as t\nt.cache = {}\nif t.TYPE_CHECKING:\n    import pkg.core\n", encoding="utf-8"
    )
    assert any("engine -> core" in f for f in findings_for(root, "model-truth"))


def test_tuple_del_typing_alias_still_measured(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text(
        "import typing as t\ndel (t,)\nif t.TYPE_CHECKING:\n    import pkg.core\n", encoding="utf-8"
    )
    assert findings_for(root, "model-truth") == []


def test_param_shadowed_typing_alias_still_measured(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text(
        "import typing as t\ndef f(t):\n    if t.TYPE_CHECKING:\n        import pkg.core\n", encoding="utf-8"
    )
    assert findings_for(root, "model-truth") == []


@pytest.mark.parametrize(
    "src",
    [
        "import typing as t\ndef f(t):\n    return t\nif t.TYPE_CHECKING:\n    import pkg.core\n",
        "import typing as t\nf = lambda t: t\nif t.TYPE_CHECKING:\n    import pkg.core\n",
        "from typing import TYPE_CHECKING\nclass C:\n    TYPE_CHECKING = False\nif TYPE_CHECKING:\n    import pkg.core\n",
        "from typing import TYPE_CHECKING\nX = [TYPE_CHECKING for TYPE_CHECKING in ()]\nif TYPE_CHECKING:\n    import pkg.core\n",
        (
            "from typing import TYPE_CHECKING\nclass C:\n    TYPE_CHECKING = False\n    def m(self):\n"
            "        if TYPE_CHECKING:\n            import pkg.core\n"
        ),
        "def f():\n    import typing\n    if typing.TYPE_CHECKING:\n        import pkg.core\n",
    ],
    ids=["param", "lambda-param", "class-attr", "comprehension-target", "method-skips-class-scope", "function-local"],
)
def test_nested_scope_binding_keeps_typing_guard(tmp_path, src):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text(src, encoding="utf-8")
    assert any("engine -> core" in f for f in findings_for(root, "model-truth"))


@pytest.mark.parametrize(
    "src",
    [
        "import typing as t\ndef f():\n    global t\n    t = None\nif t.TYPE_CHECKING:\n    import pkg.core\n",
        "from typing import TYPE_CHECKING\nX = [(TYPE_CHECKING := x) for x in ()]\nif TYPE_CHECKING:\n    import pkg.core\n",
        "from typing import TYPE_CHECKING\ndef f(x=(TYPE_CHECKING := 0)):\n    pass\nif TYPE_CHECKING:\n    import pkg.core\n",
        "from typing import TYPE_CHECKING\nclass C:\n    TYPE_CHECKING = False\n    if TYPE_CHECKING:\n        import pkg.core\n",
        "from typing import TYPE_CHECKING\ndef f():\n    TYPE_CHECKING = True\n    if TYPE_CHECKING:\n        import pkg.core\n",
    ],
    ids=["global", "comprehension-walrus", "default-walrus", "class-body", "function-local-rebind"],
)
def test_binding_in_guard_scope_cancels_typing_guard(tmp_path, src):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text(src, encoding="utf-8")
    assert findings_for(root, "model-truth") == []


def test_import_rebound_typing_alias_still_measured(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text(
        "import typing as t\nimport os as t\nif t.TYPE_CHECKING:\n    import pkg.core\n", encoding="utf-8"
    )
    assert findings_for(root, "model-truth") == []


def test_rebound_typing_alias_still_measured(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text(
        "import typing as t\nt = object\nif t.TYPE_CHECKING:\n    import pkg.core\n", encoding="utf-8"
    )
    assert findings_for(root, "model-truth") == []


def test_unrelated_type_checking_attr_still_measured(tmp_path):
    root = make_repo(tmp_path)
    (root / "pkg" / "engine" / "b.py").write_text(
        "import os\nif os.TYPE_CHECKING:\n    import pkg.core\n", encoding="utf-8"
    )
    assert findings_for(root, "model-truth") == []


# --------------------------------------------------------------------------- legacy-arrow ratchet


def test_legacy_count_above_baseline_flagged(tmp_path):
    root = make_repo(tmp_path)
    edit(root, "architecture/index.yaml", "baseline: 1", "baseline: 0")
    assert findings_for(root, "baseline-ratchet")


def test_legacy_count_below_baseline_flagged(tmp_path):
    root = make_repo(tmp_path)
    edit(root, "architecture/index.yaml", "baseline: 1", "baseline: 2")
    assert findings_for(root, "baseline-ratchet")


def test_zero_legacy_zero_baseline_green(tmp_path):
    root = make_repo(tmp_path)
    edit(root, "architecture/model/pkg.c4", " #legacy", "")
    edit(root, "architecture/index.yaml", "baseline: 1", "baseline: 0")
    assert findings_for(root, "baseline-ratchet") == []
    assert findings_for(root, "model-truth") == []


def test_legacy_arrows_missing_is_finding(tmp_path):
    root = make_repo(tmp_path)
    edit(root, "architecture/index.yaml", "legacy_arrows: {baseline: 1}\n", "")
    fs = findings_for(root, "baseline-ratchet")
    assert fs
    assert any("legacy_arrows" in f for f in fs)


def test_legacy_arrows_non_integer_is_finding(tmp_path):
    root = make_repo(tmp_path)
    edit(root, "architecture/index.yaml", "baseline: 1", "baseline: fish")
    fs = findings_for(root, "baseline-ratchet")
    assert fs
    assert any("legacy_arrows" in f for f in fs)


def test_legacy_arrows_negative_is_finding(tmp_path):
    root = make_repo(tmp_path)
    edit(root, "architecture/index.yaml", "baseline: 1", "baseline: -1")
    fs = findings_for(root, "baseline-ratchet")
    assert fs
    assert any("legacy_arrows" in f for f in fs)


# --------------------------------------------------------------------------- node mapping from model metadata

SCENARIO_MODEL = """
specification {
  element node
  element bucket {
    #virtual
  }
}
model {
  api = node 'API' {
    metadata {
      package 'pkg.api'
    }
    handlers = node 'Handlers'
  }
  core = node 'Core' {
    metadata {
      package 'pkg.core'
    }
  }
  store = node 'Store' {
    metadata {
      package 'pkg.store'
    }
  }
  api.handlers -> core
}
"""

SCENARIO_FILES = {
    "architecture/index.yaml": "root_package: pkg\nlegacy_arrows: {baseline: 0}\ndiagrams:\n  architecture/system.arc42.md: [land]\n",
    "architecture/model/pkg.c4": SCENARIO_MODEL,
    "architecture/views.c4": VIEWS,
    "architecture/system.arc42.md": SYSTEM_MD,
    "pkg/__init__.py": "",
    "pkg/api/__init__.py": "",
    "pkg/api/handlers/__init__.py": "from pkg.core import x\nimport pkg.store\n",
    "pkg/core/__init__.py": "x = 1\n",
    "pkg/store/__init__.py": "",
}


def make_scenario_repo(tmp_path: Path, *edits: tuple[str, str], files: dict[str, str] | None = None) -> Path:
    model = SCENARIO_MODEL
    for old, new in edits:
        assert old in model, old
        model = model.replace(old, new)
    return write_repo(tmp_path, {**SCENARIO_FILES, MODEL_REL: model, **(files or {})})


HANDLERS = "    handlers = node 'Handlers'\n"
HANDLERS_TO_STORE = (
    "model-truth: measured runtime edge api.handlers -> store is missing from the model"
    " (import pkg.api.handlers -> pkg.store)"
)


def test_node_mapping_read_from_metadata(tmp_path):
    files = {
        "architecture/index.yaml": "root_package: pkg\nlegacy_arrows: {baseline: 0}\ndiagrams:\n  architecture/system.arc42.md: [land]\n",
        MODEL_REL: "specification { element node }\nmodel {\n  api = node 'API' { metadata { package 'pkg.api'  specs ['api'] } }\n}\n",
        "architecture/views.c4": VIEWS,
        "architecture/system.arc42.md": SYSTEM_MD,
        "openspec/specs/api/spec.md": "# spec\n",
        "pkg/__init__.py": "",
        "pkg/api/__init__.py": "",
    }
    assert archcheck.run_checks(write_repo(tmp_path, files)) == []


def test_virtual_node_maps_buckets(tmp_path):
    root = make_scenario_repo(
        tmp_path,
        ("  api.handlers -> core\n", "  legacy = bucket 'Legacy' {\n    metadata {\n      packages ['pkg.old']\n    }\n  }\n  api.handlers -> core\n"),
        files={"pkg/old.py": "import pkg.core\n"},
    )
    assert archcheck.run_checks(root) == [
        HANDLERS_TO_STORE,
        "model-truth: measured runtime edge legacy -> core is missing from the model (import pkg.old -> pkg.core)",
    ]


def test_multi_line_claims_read_like_one_line(tmp_path):
    one_line = make_scenario_repo(tmp_path / "one", ("      package 'pkg.core'\n", "      package 'pkg.core'\n      claims ['pkg.a', 'pkg.b']\n"))
    split = make_scenario_repo(
        tmp_path / "split", ("      package 'pkg.core'\n", "      package 'pkg.core'\n      claims [\n        'pkg.a',\n        'pkg.b'\n      ]\n")
    )
    assert archcheck.run_checks(split) == archcheck.run_checks(one_line)
    assert "claims-exist: core claims pkg.b, which does not exist on disk" in archcheck.run_checks(split)


def test_no_model_files_means_no_nodes(tmp_path):
    root = make_scenario_repo(tmp_path)
    (root / MODEL_REL).unlink()
    fs = findings_for(root, "claims-exactly-once")
    assert fs == [f"claims-exactly-once: top-level pkg.{unit} is claimed by no node" for unit in ("api", "core", "store")]


def test_model_child_governed_with_no_index_entry(tmp_path):
    root = make_scenario_repo(tmp_path)
    assert "handlers" not in (root / "architecture" / "index.yaml").read_text(encoding="utf-8")
    assert archcheck.run_checks(root) == [
        HANDLERS_TO_STORE
    ]


def test_model_child_governs_license(tmp_path):
    root = make_scenario_repo(tmp_path)
    assert archcheck.license(root=root, src="pkg.api.handlers", dst="pkg.core")
    assert not archcheck.license(root=root, src="pkg.api.handlers", dst="pkg.store")
    assert not archcheck.license(root=root, src="pkg.api", dst="pkg.core")


def test_grandchild_governed(tmp_path):
    root = make_scenario_repo(
        tmp_path,
        (HANDLERS, "    handlers = node 'Handlers' {\n      x = node 'X'\n    }\n"),
        files={"pkg/api/handlers/__init__.py": "from pkg.core import x\n", "pkg/api/handlers/x.py": "import pkg.store\n"},
    )
    assert archcheck.run_checks(root) == [
        ("model-truth: measured runtime edge api.handlers.x -> store is missing from the model"
        " (import pkg.api.handlers.x -> pkg.store)")
    ]


def test_model_child_missing_on_disk(tmp_path, capsys):
    root = make_scenario_repo(tmp_path, ("      package 'pkg.core'\n    }\n", "      package 'pkg.core'\n    }\n    inner = node 'Inner'\n"))
    assert "claims-exist: element core.inner maps to pkg.core.inner, which does not exist on disk" in findings_for(
        root, "claims-exist"
    )
    assert cli.la_arch_check(["--root", str(root)]) == 1
    assert "core.inner" in capsys.readouterr().out


def test_grandchild_missing_on_disk(tmp_path):
    root = make_scenario_repo(tmp_path, (HANDLERS, "    handlers = node 'Handlers' {\n      y = node 'Y'\n    }\n"))
    assert findings_for(root, "claims-exist") == [
        "claims-exist: element api.handlers.y maps to pkg.api.handlers.y, which does not exist on disk"
    ]


def test_child_collides_with_another_nodes_claim(tmp_path):
    root = make_scenario_repo(tmp_path, ("      package 'pkg.core'\n", "      package 'pkg.core'\n      claims ['pkg.api.handlers']\n"))
    assert (
        "claims-exactly-once: element api.handlers (pkg.api.handlers) collides with declared unit pkg.api.handlers"
        in findings_for(root, "claims-exactly-once")
    )


def test_collision_names_the_first_overlapping_unit_in_sorted_order(tmp_path):
    root = make_scenario_repo(
        tmp_path,
        ("      package 'pkg.core'\n", "      package 'pkg.core'\n      claims ['pkg.api.handlers.z', 'pkg.api.handlers']\n"),
        files={"pkg/api/handlers/z.py": ""},
    )
    collides = [f for f in findings_for(root, "claims-exactly-once") if "collides" in f]
    assert collides == [
        "claims-exactly-once: element api.handlers (pkg.api.handlers) collides with declared unit pkg.api.handlers"
    ]


def test_own_claims_are_collision_candidates_but_own_package_is_not(tmp_path):
    root = make_scenario_repo(tmp_path, ("      package 'pkg.api'\n", "      package 'pkg.api'\n      claims ['pkg.api.handlers']\n"))
    assert [f for f in findings_for(root, "claims-exactly-once") if "collides" in f] == [
        "claims-exactly-once: element api.handlers (pkg.api.handlers) collides with declared unit pkg.api.handlers"
    ]


def test_descendants_of_one_node_do_not_collide(tmp_path):
    root = make_scenario_repo(
        tmp_path,
        (HANDLERS, "    handlers = node 'Handlers' {\n      x = node 'X'\n    }\n"),
        files={"pkg/api/handlers/x.py": ""},
    )
    assert findings_for(root, "claims-exactly-once") == []
    assert findings_for(root, "claims-exist") == []


def test_virtual_node_containing_elements_yields_one_finding(tmp_path):
    root = make_scenario_repo(
        tmp_path,
        ("  api.handlers -> core\n", ("  misc = bucket 'Misc' {\n    metadata {\n      packages ['pkg.misc']\n    }\n"
                                       "    x = node 'X'\n    y = node 'Y'\n  }\n  api.handlers -> core\n")),
        files={"pkg/misc/__init__.py": "", "pkg/misc/x.py": ""},
    )
    assert findings_for(root, "claims-exist") == ["claims-exist: virtual node misc may not contain elements"]
    assert findings_for(root, "claims-exactly-once") == []


def test_elements_under_a_virtual_node_map_to_no_unit(tmp_path):
    root = make_scenario_repo(
        tmp_path,
        ("  api.handlers -> core\n", ("  misc = bucket 'Misc' {\n    metadata {\n      packages ['pkg.misc']\n    }\n"
                                       "    x = node 'X'\n  }\n  api.handlers -> core\n  misc.x -> core\n")),
        files={"pkg/misc/__init__.py": "", "pkg/misc/x.py": "import pkg.core\n"},
    )
    assert findings_for(root, "model-truth") == [
        HANDLERS_TO_STORE,
        "model-truth: measured runtime edge misc -> core is missing from the model (import pkg.misc.x -> pkg.core)",
        "model-truth: modeled relation misc.x -> core has no measured runtime edge",
    ]
    assert not archcheck.license(root=root, src="pkg.misc.x", dst="pkg.core")


def test_virtual_kind_element_nested_under_precise_node_maps_by_convention(tmp_path):
    root = make_scenario_repo(tmp_path, (HANDLERS, "    handlers = bucket 'Handlers'\n"))
    assert archcheck.run_checks(root) == [
        HANDLERS_TO_STORE
    ]


def test_duplicate_claim_attributes_to_the_first_node_in_model_order(tmp_path):
    root = make_repo(tmp_path)
    edit(root, MODEL_REL, CORE_PKG, CORE_PKG + "      claims ['pkg.shared']\n")
    edit(root, MODEL_REL, ENGINE_ARC42, ENGINE_ARC42 + "      claims ['pkg.shared']\n")
    edit(root, MODEL_REL, "  engine -> core\n", "")
    (root / "pkg" / "engine" / "b.py").write_text("", encoding="utf-8")
    (root / "pkg" / "shared.py").write_text("import pkg.core.a\n", encoding="utf-8")
    assert findings_for(root, "claims-exactly-once") == ["claims-exactly-once: pkg.shared claimed by both core and engine"]
    assert findings_for(root, "model-truth") == []
    assert archcheck.license(root=root, src="pkg.shared", dst="pkg.core.a")


def test_model_child_units_resolve_under_source_root(tmp_path):
    files = {(f"src/{rel}" if rel.startswith("pkg/") else rel): text for rel, text in SCENARIO_FILES.items()}
    files["architecture/index.yaml"] = "source_root: src\n" + SCENARIO_FILES["architecture/index.yaml"]
    root = write_repo(tmp_path, files)
    assert findings_for(root, "claims-exist") == []
    assert findings_for(root, "model-truth") == [
        HANDLERS_TO_STORE
    ]


# --------------------------------------------------------------------------- malformed node metadata (setup errors)


@pytest.mark.parametrize(
    ("old", "new", "pattern"),
    [
        (CORE_PKG, "      arc42 'architecture/engine.arc42.md'\n", r"model element core: .*package"),
        (CORE_PKG, CORE_PKG + "      pakage 'pkg.core'\n", r"model element core: .*pakage"),
        (CORE_PKG, CORE_PKG + "      claims 'pkg.engine'\n", r"model element core: .*claims"),
        (CORE_PKG, CORE_PKG + "      specs 'queries'\n", r"model element core: .*specs"),
        (ENGINE_ARC42, "      arc42 ['architecture/engine.arc42.md']\n", r"model element engine: .*arc42"),
        (CORE_PKG, CORE_PKG + "      packages ['pkg.core']\n", r"model element core: .*packages"),
        (CORE_PKG, CORE_PKG + "      virtual 'true'\n", r"model element core: .*virtual"),
    ],
    ids=["no-package", "unknown-key", "scalar-claims", "scalar-specs", "list-arc42", "packages-on-precise", "virtual-key"],
)
def test_metadata_schema_violation_is_a_setup_error(tmp_path, old, new, pattern):
    root = make_repo(tmp_path)
    edit(root, MODEL_REL, old, new)
    with pytest.raises(archcheck.ArchCheckError, match=pattern):
        archcheck.run_checks(root)


VIRTUAL_MODEL = SCENARIO_MODEL.replace(
    "  api.handlers -> core\n", "  misc = bucket 'Misc' {\n    metadata {\n      packages ['pkg.misc']\n    }\n  }\n  api.handlers -> core\n"
)


@pytest.mark.parametrize(
    ("new", "key"),
    [("      package 'pkg.misc'\n", "package"), ("      packages ['pkg.misc']\n      claims ['pkg.misc']\n", "claims")],
    ids=["package", "claims"],
)
def test_precise_keys_on_a_virtual_node_are_a_setup_error(tmp_path, new, key):
    model = VIRTUAL_MODEL.replace("      packages ['pkg.misc']\n", new)
    root = write_repo(tmp_path, {**SCENARIO_FILES, MODEL_REL: model, "pkg/misc/__init__.py": ""})
    with pytest.raises(archcheck.ArchCheckError, match=rf"model element misc: .*'?{key}'?"):
        archcheck.run_checks(root)


def test_virtual_node_needs_no_metadata(tmp_path):
    model = VIRTUAL_MODEL.replace("    metadata {\n      packages ['pkg.misc']\n    }\n", "")
    root = write_repo(tmp_path, {**SCENARIO_FILES, MODEL_REL: model})
    assert findings_for(root, "claims-exist") == []
    assert findings_for(root, "claims-exactly-once") == []


@pytest.mark.parametrize("body", ["        package 'pkg.core.query'\n", ""], ids=["with-keys", "empty"])
def test_metadata_on_a_nested_element_is_a_setup_error(tmp_path, body):
    model = CHILD_MODEL.replace("    query = node 'Query'\n", f"    query = node 'Query' {{\n      metadata {{\n{body}      }}\n    }}\n")
    root = make_child_repo(tmp_path, model=model)
    with pytest.raises(archcheck.ArchCheckError) as excinfo:
        archcheck.run_checks(root)
    assert str(excinfo.value) == "model element core.query: nested elements may not carry metadata"


@pytest.mark.parametrize(
    ("old", "new", "error"),
    [
        (CORE_PKG, CORE_PKG + "      package 'pkg.other'\n", "element core has malformed metadata: package 'pkg.other'"),
        (CORE_PKG + "    }\n", CORE_PKG + "    }\n    metadata {\n      claims ['pkg.x']\n    }\n", "element core has malformed metadata: metadata {"),
        (CORE_PKG, '      package "pkg.core"\n', 'element core has malformed metadata: package "pkg.core"'),
        (CORE_PKG, CORE_PKG + "      claims ['pkg.engine'\n", "element core has malformed metadata: "),
        (CORE_PKG, CORE_PKG + "      claims ['pkg.engine', ]\n", "element core has malformed metadata: "),
    ],
    ids=["repeated-key", "second-block", "double-quoted", "unclosed-array", "trailing-comma"],
)
def test_malformed_metadata_is_a_setup_error(tmp_path, old, new, error):
    root = make_repo(tmp_path)
    edit(root, MODEL_REL, old, new)
    with pytest.raises(archcheck.ArchCheckError) as excinfo:
        archcheck.run_checks(root)
    assert error in str(excinfo.value)


def test_metadata_problems_are_reported_together_in_model_order(tmp_path):
    root = make_repo(tmp_path)
    edit(root, MODEL_REL, ENGINE_ARC42, ENGINE_ARC42 + "      colour 'red'\n")
    edit(root, MODEL_REL, CORE_PKG, CORE_PKG + "      pakage 'pkg.core'\n")
    with pytest.raises(archcheck.ArchCheckError) as excinfo:
        archcheck.run_checks(root)
    message = str(excinfo.value)
    assert "; " in message
    assert message.index("model element core: ") < message.index("model element engine: ")
    assert "pakage" in message
    assert "colour" in message


def test_every_kind_of_metadata_problem_is_joined_in_model_order(tmp_path):
    model = CHILD_MODEL.replace(CORE_PKG, CORE_PKG + "      package 'pkg.other'\n").replace(
        "    query = node 'Query'\n", "    query = node 'Query' {\n      metadata {\n        package 'pkg.core.query'\n      }\n    }\n"
    ).replace(ENGINE_ARC42, ENGINE_ARC42 + "      pakage 'pkg.engine'\n")
    root = make_child_repo(tmp_path)
    (root / MODEL_REL).write_text(model, encoding="utf-8")
    with pytest.raises(archcheck.ArchCheckError) as excinfo:
        archcheck.run_checks(root)
    parts = str(excinfo.value).split("; ")
    assert parts[:2] == [
        "element core has malformed metadata: package 'pkg.other'",
        "model element core.query: nested elements may not carry metadata",
    ]
    assert len(parts) == 3
    assert parts[2].startswith("model element engine: ")
    assert "pakage" in parts[2]


def test_malformed_metadata_exits_2_naming_the_element(tmp_path, capsys):
    root = make_repo(tmp_path)
    edit(root, MODEL_REL, CORE_PKG, CORE_PKG + "      pakage 'pkg.core'\n")
    assert cli.la_arch_check(["--root", str(root)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("arch_check: model element core: ")
    assert "pakage" in captured.err


def test_nodes_in_index_yaml_is_a_setup_error(tmp_path):
    root = make_repo(tmp_path)
    append(root, "architecture/index.yaml", "nodes:\n  core: {package: pkg.core}\n")
    with pytest.raises(archcheck.ArchCheckError, match="nodes"):
        archcheck.run_checks(root)


def test_model_identity_is_not_a_check_id(tmp_path):
    assert "model-identity" not in check_ids()
    root = make_repo(tmp_path)
    append(root, "architecture/system.arc42.md", "3. Identity. [enforced: arch_check:model-identity]\n")
    assert "enforced-tags: system.arc42.md tags unknown enforcement id 'arch_check:model-identity'" in findings_for(
        root, "enforced-tags"
    )


# --------------------------------------------------------------------------- law: attribution


def test_child_healthy_fixture_passes(tmp_path):
    assert archcheck.run_checks(make_child_repo(tmp_path)) == []


def test_grandchild_healthy_fixture_passes(tmp_path):
    assert archcheck.run_checks(make_grandchild_repo(tmp_path)) == []


def test_longest_prefix_attribution(tmp_path):
    root = make_grandchild_repo(tmp_path)
    (root / "pkg" / "core" / "query.py").write_text("import pkg.engine.syntax.shallow\n", encoding="utf-8")
    fs = findings_for(root, "model-truth")
    assert any("measured runtime edge core.query -> engine.syntax is missing" in f for f in fs)
    assert any("modeled relation core.query -> engine.syntax.deep has no measured runtime edge" in f for f in fs)


def test_undeclared_module_attributes_to_its_node(tmp_path):
    root = make_child_repo(tmp_path)
    (root / "pkg" / "engine" / "other.py").write_text("", encoding="utf-8")
    append(root, "pkg/core/query.py", "import pkg.engine.other\n")
    fs = findings_for(root, "model-truth")
    assert any("measured runtime edge core.query -> engine is missing" in f for f in fs)
    assert any("(import pkg.core.query -> pkg.engine.other)" in f for f in fs)


def test_prefix_attribution_respects_segment_boundaries(tmp_path):
    root = make_child_repo(tmp_path)
    (root / "pkg" / "engine" / "syntaxx.py").write_text("", encoding="utf-8")
    append(root, "pkg/core/models.py", "import pkg.engine.syntaxx\n")
    fs = findings_for(root, "model-truth")
    assert any("core.models -> engine is missing" in f for f in fs)
    assert not any("core.models -> engine.syntax is missing" in f for f in fs)


def test_relative_imports_resolve(tmp_path):
    root = make_child_repo(tmp_path)
    (root / "pkg" / "core" / "query.py").write_text(
        "from ..engine.syntax import parse\nfrom .models import Model\nfrom . import models\n", encoding="utf-8"
    )
    assert findings_for(root, "model-truth") == []


def test_from_package_import_submodule_measures_both_edges(tmp_path):
    root = make_child_repo(tmp_path)
    append(root, "pkg/core/models.py", "from pkg.engine import syntax\n")
    fs = findings_for(root, "model-truth")
    assert any("core.models -> engine is missing" in f for f in fs)
    assert any("core.models -> engine.syntax is missing" in f for f in fs)


def test_reexported_attribute_resolves_like_the_submodule(tmp_path):
    root = make_child_repo(tmp_path)
    (root / "pkg" / "engine" / "__init__.py").write_text("syntax = 1\n", encoding="utf-8")
    append(root, "pkg/core/models.py", "from pkg.engine import syntax\n")
    assert any("core.models -> engine.syntax is missing" in f for f in findings_for(root, "model-truth"))


def test_type_checking_exclusion_at_child_level(tmp_path):
    root = make_child_repo(tmp_path)
    (root / "pkg" / "core" / "query.py").write_text(
        "from typing import TYPE_CHECKING\nfrom pkg.core.models import Model\n"
        "if TYPE_CHECKING:\n    from pkg.engine.syntax import parse\n",
        encoding="utf-8",
    )
    assert any(
        "modeled relation core.query -> engine.syntax has no measured runtime edge" in f
        for f in findings_for(root, "model-truth")
    )


def test_root_init_exempt(tmp_path):
    root = make_child_repo(tmp_path)
    (root / "pkg" / "__init__.py").write_text("from pkg.engine.syntax import parse\n", encoding="utf-8")
    assert findings_for(root, "model-truth") == []


# --------------------------------------------------------------------------- law: coverage


def test_sibling_child_edge_needs_arrow(tmp_path):
    model = CHILD_MODEL.replace("  core.query -> core.models\n", "")
    root = make_child_repo(tmp_path, model=model)
    fs = findings_for(root, "model-truth")
    assert any("measured runtime edge core.query -> core.models is missing" in f for f in fs)
    assert any("(import pkg.core.query -> pkg.core.models)" in f for f in fs)


def test_ancestor_descendant_edges_internal(tmp_path):
    root = make_child_repo(tmp_path)
    append(root, "pkg/core/query.py", "import pkg.core\n")
    (root / "pkg" / "core" / "util.py").write_text("import pkg.core.query\n", encoding="utf-8")
    append(root, "pkg/engine/__init__.py", "from pkg.engine import syntax as _syntax\n")
    assert findings_for(root, "model-truth") == []


def test_parent_arrow_covers_child_cross_node_edges(tmp_path):
    root = make_child_repo(tmp_path)
    append(root, "pkg/engine/b.py", "import pkg.core.query\nimport pkg.core.models\n")
    assert findings_for(root, "model-truth") == []


def test_specific_and_parent_arrows_both_live(tmp_path):
    model = CHILD_MODEL.replace("  engine -> core\n", "  engine -> core\n  engine -> core.query\n")
    root = make_child_repo(tmp_path, model=model)
    append(root, "pkg/engine/b.py", "import pkg.core.query\n")
    assert findings_for(root, "model-truth") == []


def test_fully_shadowed_arrow_is_dead(tmp_path):
    model = CHILD_MODEL.replace("  engine -> core\n", "  engine -> core\n  engine -> core.query\n")
    root = make_child_repo(tmp_path, model=model)
    (root / "pkg" / "engine" / "b.py").write_text("import pkg.core.query\n", encoding="utf-8")
    fs = findings_for(root, "model-truth")
    assert len(fs) == 1
    assert "modeled relation engine -> core is fully shadowed" in fs[0]


def test_incomparable_covers_both_live(tmp_path):
    model = CHILD_MODEL.replace(
        "  core.query -> engine.syntax #legacy\n", "  core.query -> engine\n  core -> engine.syntax\n"
    )
    index = CHILD_INDEX.replace("baseline: 1", "baseline: 0")
    root = make_child_repo(tmp_path, index=index, model=model)
    assert findings_for(root, "model-truth") == []
    assert findings_for(root, "baseline-ratchet") == []


def test_dead_child_arrow_flagged(tmp_path):
    model = CHILD_MODEL.replace("  engine -> core\n", "  engine -> core\n  core.models -> engine.syntax\n")
    root = make_child_repo(tmp_path, model=model)
    assert any(
        "modeled relation core.models -> engine.syntax has no measured runtime edge" in f
        for f in findings_for(root, "model-truth")
    )


def test_internal_arrow_rejected_and_does_not_license_sibling(tmp_path):
    # A parent->child arrow is internal: it must be flagged and must NOT cover the sibling edge.
    model = CHILD_MODEL.replace("  core.query -> core.models\n", "  core -> core.models\n")
    root = make_child_repo(tmp_path, model=model)
    fs = findings_for(root, "model-truth")
    assert any("core -> core.models" in f and "ancestor or descendant" in f for f in fs)
    assert any("measured runtime edge core.query -> core.models is missing" in f for f in fs)


def test_internal_arrow_not_licensed_by_license_helper(tmp_path):
    model = CHILD_MODEL.replace("  core.query -> core.models\n", "  core -> core.models\n")
    root = make_child_repo(tmp_path, model=model)
    assert not archcheck.license(root=root, src="pkg.core.query", dst="pkg.core.models")


def test_child_path_colliding_with_claim_flagged(tmp_path):
    model = CHILD_MODEL.replace(ENGINE_ARC42, ENGINE_ARC42 + "      claims ['pkg.core.query']\n")
    root = make_child_repo(tmp_path, model=model)
    assert any("collides" in f and "pkg.core.query" in f for f in findings_for(root, "claims-exactly-once"))


def test_child_path_nested_under_claim_flagged(tmp_path):
    """A claim nested inside a model child's subtree also splits it across nodes."""
    model = CHILD_MODEL.replace(ENGINE_ARC42, ENGINE_ARC42 + "      claims ['pkg.core.query.helpers']\n")
    root = make_child_repo(tmp_path, model=model)
    assert any("collides" in f and "pkg.core.query" in f for f in findings_for(root, "claims-exactly-once"))


# --------------------------------------------------------------------------- license helper


def test_license_helper_child_fixture(tmp_path):
    root = make_child_repo(tmp_path)
    assert archcheck.license(root=root, src="pkg.core.query", dst="pkg.engine.syntax")
    assert not archcheck.license(root=root, src="pkg.core.models", dst="pkg.engine.syntax")
    assert not archcheck.license(root=root, src="pkg.core.query", dst="pkg.engine.b")
    assert archcheck.license(root=root, src="pkg.engine.b", dst="pkg.core.query")
    assert archcheck.license(root=root, src="pkg.engine.syntax", dst="pkg.core.models")


# --------------------------------------------------------------------------- enforced-tags


def test_unknown_enforced_tag(tmp_path):
    root = make_repo(tmp_path)
    append(root, "architecture/system.arc42.md", "3. Rule. [enforced: nonsense]\n")
    assert any("nonsense" in f for f in findings_for(root, "enforced-tags"))


def test_contract_ids_no_longer_valid_enforcement(tmp_path):
    root = make_repo(tmp_path)
    append(root, "architecture/system.arc42.md", "3. Old law. [enforced: layers]\n")
    assert any("layers" in f for f in findings_for(root, "enforced-tags"))


def test_known_enforced_tag_forms_accepted(tmp_path):
    root = make_repo(tmp_path)
    append(
        root,
        "architecture/system.arc42.md",
        "3. A. [enforced: arch_check:model-truth]\n4. B. [enforced: test:tests/test_x.py]\n",
    )
    assert findings_for(root, "enforced-tags") == []


def append_principles(root: Path, lines: str) -> None:
    append(root, "architecture/system.arc42.md", lines)


def test_malformed_enforced_tag_flagged(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Rule. [enforced]\n")
    assert any("malformed" in f for f in findings_for(root, "enforced-tags"))


def test_malformed_review_tag_flagged(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Rule. [review: ABC-1869]\n")
    assert any("malformed" in f and "review" in f for f in findings_for(root, "enforced-tags"))


def test_malformed_target_tag_flagged(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Rule. [target ABC-1841]\n")
    assert any("malformed" in f and "target" in f for f in findings_for(root, "enforced-tags"))


def test_target_tag_id_must_match_issue_key_pattern(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Rule. [target: 1841]\n")
    assert any("1841" in f for f in findings_for(root, "enforced-tags"))


def test_valid_target_tag_accepted(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Planned. [target: ABC-1841]\n")
    assert findings_for(root, "enforced-tags") == []


def test_untagged_principle_item_flagged(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Naked rule.\n")
    assert any("status tag" in f for f in findings_for(root, "enforced-tags"))


def test_indented_untagged_principle_item_flagged(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "  3. Indented naked rule.\n")
    assert any("status tag" in f for f in findings_for(root, "enforced-tags"))


def test_three_space_numbered_line_is_continuation(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Rule with nested steps. [review]\n   1. nested step\n")
    assert findings_for(root, "enforced-tags") == []


def test_indented_sibling_item_is_not_continuation(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "\n   3. Tagged rule. [review]\n   4. Naked sibling.\n")
    assert any("status tag" in f and "4" in f for f in findings_for(root, "enforced-tags"))


def test_tag_spanning_lines_is_malformed(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Rule. [enforced: test:tests/a.py\ntest:tests/b.py]\n")
    assert any("malformed" in f for f in findings_for(root, "enforced-tags"))


def test_mixed_tags_on_one_item_legal(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Broadcast clause. [review] Mode-axis clause. [target: ABC-1841]\n")
    assert findings_for(root, "enforced-tags") == []


def test_tag_on_continuation_line_accepted(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Wrapped rule\n   over two lines. [review]\n")
    assert findings_for(root, "enforced-tags") == []


def test_malformed_tags_in_prose_flagged(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "\nProse note. [review: X]\nAnother note. [target 123]\n")
    fs = findings_for(root, "enforced-tags")
    assert any("malformed" in f and "review" in f for f in fs)
    assert any("malformed" in f and "target" in f for f in fs)


def test_malformed_tag_is_not_status_coverage(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. A. [review: ABC-1869]\n4. B. [target ABC-1841]\n")
    assert sum("status tag" in f for f in findings_for(root, "enforced-tags")) == 2


def test_tag_on_next_item_does_not_cover_previous(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Naked rule.\n4. Tagged rule. [review]\n")
    fs = findings_for(root, "enforced-tags")
    assert sum("status tag" in f for f in fs) == 1
    assert any("status tag" in f and "3" in f for f in fs)


def test_invalid_target_id_is_not_status_coverage(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Rule. [target: 1841]\n")
    assert any("status tag" in f for f in findings_for(root, "enforced-tags"))


def test_unknown_enforced_id_is_not_status_coverage(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Rule. [enforced: nonsense]\n")
    assert any("status tag" in f for f in findings_for(root, "enforced-tags"))


def test_empty_test_id_is_not_status_coverage(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Rule. [enforced: test:]\n")
    assert any("status tag" in f for f in findings_for(root, "enforced-tags"))


def test_fenced_code_blocks_ignored(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "\n```text\n3. not a principle\n[target 999]\n```\n")
    assert findings_for(root, "enforced-tags") == []


def test_tilde_fenced_code_blocks_ignored(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "\n~~~text\n3. not a principle\n[target 999]\n~~~\n")
    assert findings_for(root, "enforced-tags") == []


def test_longer_fence_swallows_inner_backtick_fence(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "\n````md\n```\n3. not a principle\n[target 999]\n````\n")
    assert findings_for(root, "enforced-tags") == []


def test_fence_line_with_info_string_is_not_a_closer(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "\n```\n```python\n3. not a principle\n[target 999]\n```\n")
    assert findings_for(root, "enforced-tags") == []


def test_orphan_arc42_file_flagged(tmp_path):
    root = make_repo(tmp_path)
    (root / "architecture" / "rogue.arc42.md").write_text("# rogue\n", encoding="utf-8")
    assert any("rogue" in f for f in findings_for(root, "arc42-exists"))


def test_cross_cutting_arc42_file_accepted(tmp_path):
    root = make_repo(tmp_path)
    (root / "architecture" / "semantics.arc42.md").write_text("# semantics\n", encoding="utf-8")
    append(root, "architecture/index.yaml", "cross_cutting_arc42: [architecture/semantics.arc42.md]\n")
    assert findings_for(root, "arc42-exists") == []


def test_cross_cutting_arc42_missing_file_flagged(tmp_path):
    root = make_repo(tmp_path)
    append(root, "architecture/index.yaml", "cross_cutting_arc42: [architecture/ghost.arc42.md]\n")
    assert any("ghost" in f for f in findings_for(root, "arc42-exists"))


# --------------------------------------------------------------------------- repo config + CLI


def test_root_package_is_required(tmp_path):
    root = make_repo(tmp_path)
    edit(root, "architecture/index.yaml", "root_package: pkg\n", "")
    with pytest.raises(archcheck.ArchCheckError, match="root_package"):
        archcheck.run_checks(root)


def test_custom_issue_key_pattern(tmp_path):
    root = make_repo(tmp_path)
    (root / "living-architecture.yaml").write_text("issue_key_pattern: 'PROJ-\\d+'\n", encoding="utf-8")
    append_principles(root, "3. Planned. [target: PROJ-7]\n4. Other. [target: ABC-1841]\n")
    fs = findings_for(root, "enforced-tags")
    assert len([f for f in fs if "does not match issue_key_pattern" in f]) == 1
    assert any("ABC-1841" in f for f in fs)
    assert not any("PROJ-7" in f for f in fs)


def test_default_issue_key_pattern_rejects_lowercase(tmp_path):
    root = make_repo(tmp_path)
    append_principles(root, "3. Planned. [target: abc-12]\n")
    assert any("abc-12" in f for f in findings_for(root, "enforced-tags"))


def test_main_ok(tmp_path, capsys):
    root = make_repo(tmp_path)
    assert cli.la_arch_check(["--root", str(root)]) == 0
    assert "arch_check: OK" in capsys.readouterr().out


def test_main_findings(tmp_path, capsys):
    root = make_repo(tmp_path)
    append_principles(root, "3. Naked rule.\n")
    assert cli.la_arch_check(["--root", str(root)]) == 1
    assert "1 finding(s)" in capsys.readouterr().out


def test_main_broken_setup(tmp_path, capsys):
    root = make_repo(tmp_path)
    (root / "living-architecture.yaml").write_text("nope: 1\n", encoding="utf-8")
    assert cli.la_arch_check(["--root", str(root)]) == 2
    assert "nope" in capsys.readouterr().err


def test_main_without_index(tmp_path, capsys):
    assert cli.la_arch_check(["--root", str(tmp_path)]) == 2
    assert "index.yaml" in capsys.readouterr().err


# --------------------------------------------------------------------------- index schema + source_root


@pytest.mark.parametrize(
    ("old", "new", "named"),
    [
        ("legacy_arrows:", "bogus_key: 1\nlegacy_arrows:", "bogus_key"),
        ("legacy_arrows:", "nodes: {}\nlegacy_arrows:", "nodes"),
    ],
)
def test_index_schema_violation_is_a_setup_error(tmp_path, old, new, named):
    root = make_repo(tmp_path)
    edit(root, "architecture/index.yaml", old, new)
    with pytest.raises(archcheck.ArchCheckError, match=named):
        archcheck.run_checks(root)


def test_index_not_a_mapping_is_a_setup_error(tmp_path):
    root = make_repo(tmp_path)
    (root / "architecture" / "index.yaml").write_text("- root_package\n", encoding="utf-8")
    with pytest.raises(archcheck.ArchCheckError, match="mapping"):
        archcheck.run_checks(root)


def test_layout_defaults_source_root_to_repo_root(tmp_path):
    (tmp_path / "pkg").mkdir()
    layout = archcheck.resolve_layout(tmp_path, {"root_package": "pkg"})
    assert layout.source_root == tmp_path


def test_layout_resolves_source_root_under_the_repo(tmp_path):
    (tmp_path / "python" / "src" / "pkg").mkdir(parents=True)
    layout = archcheck.resolve_layout(tmp_path, {"root_package": "pkg", "source_root": "python/src"})
    assert layout.source_root == tmp_path / "python" / "src"
    assert layout.repo_root == tmp_path


@pytest.mark.parametrize("value", ["", "/abs", "a/../b", "missing"])
def test_layout_rejects_invalid_source_root(tmp_path, value):
    (tmp_path / "b" / "pkg").mkdir(parents=True)
    with pytest.raises(archcheck.ArchCheckError, match="source_root"):
        archcheck.resolve_layout(tmp_path, {"root_package": "pkg", "source_root": value})


@pytest.mark.parametrize(
    ("index", "error"),
    [
        ({"root_package": "/abs"}, "root_package '/abs' must be a relative path"),
        ({"root_package": "../pkg"}, "root_package '../pkg' must not contain '..'"),
        ({"root_package": "pkg/"}, "root_package 'pkg/' must not have empty or '.' segments"),
        ({"root_package": "."}, "root_package '.' must not have empty or '.' segments"),
        ({"root_package": "./pkg"}, "root_package './pkg' must not have empty or '.' segments"),
        ({"root_package": "a//b"}, "root_package 'a//b' must not have empty or '.' segments"),
        ({"root_package": "escape"}, "root_package 'escape' resolves outside source_root '.'"),
        ({"root_package": "link", "source_root": "src"}, "root_package 'link' resolves outside source_root 'src'"),
        ({"root_package": "file.py"}, "root_package 'file.py' is not a directory under source_root '.'"),
        ({"root_package": "missing"}, "root_package 'missing' is not a directory under source_root '.'"),
        ({"root_package": "loop"}, "root_package 'loop' is not a directory under source_root '.'"),
        ({"root_package": "p\x00"}, "root_package 'p\\x00' is not a directory under source_root '.'"),
        ({"root_package": "pkg", "source_root": "s\x00"}, "source_root 's\\x00' is not a directory"),
    ],
    ids=["absolute", "parent-segment", "trailing-slash", "dot", "dot-prefix", "empty-segment", "symlink-escape", "outside-source-root", "file", "missing", "symlink-loop", "nul", "source-root-nul"],
)
def test_layout_rejects_invalid_root_package(tmp_path, index, error):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "pkg").mkdir()
    (repo / "file.py").write_text("", encoding="utf-8")
    (repo / "escape").symlink_to(tmp_path)
    (repo / "src" / "link").symlink_to(repo / "pkg")
    (repo / "loop").symlink_to("loop")
    with pytest.raises(archcheck.ArchCheckError) as excinfo:
        archcheck.resolve_layout(repo, index)
    assert str(excinfo.value) == f"architecture/index.yaml: {error}"
