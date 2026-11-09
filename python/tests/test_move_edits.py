"""Python moves edit only at references: rule classification, token-level import edits, positions, removal."""

from pathlib import Path

import pytest

from living_architecture.cli import dr_refactor as main
from living_architecture.contract import message
from living_architecture.refactor.move_edits import leading_block_end, relative_module

MODULE_PROJECT = {
    "pkg/__init__.py": "",
    "pkg/sql/__init__.py": "",
    "pkg/sql/client.py": "X = 1\n",
    "pkg/sql/dialects.py": "D = 1\n",
    "pkg/database/__init__.py": "",
}
SYMBOL_PROJECT = {
    "pkg/__init__.py": "",
    "pkg/a.py": "def f() -> int:\n    return 1\n\n\ndef g() -> int:\n    return 2\n",
    "pkg/b.py": "",
}


def _write(root: Path, files: dict[str, str | bytes]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return root


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _move_module(root: Path, *flags: str) -> int:
    return main(["--project", str(root), *flags, "move-module", "--module", str(root / "pkg/sql/client.py"),
                 "--dest", str(root / "pkg/database")])


def _move_f(root: Path, *flags: str) -> int:
    return main(["--project", str(root), *flags, "move-symbol", "--file", str(root / "pkg/a.py"), "--name", "f",
                 "--dest", str(root / "pkg/b.py")])


@pytest.mark.parametrize(
    ("importer", "target", "expected"),
    [
        ("pkg.sql", "pkg.database", "..database"),
        ("pkg.database", "pkg.sql", "..sql"),
        ("pkg.database", "pkg.sql.dialects", "..sql.dialects"),
        ("pkg.sql", "pkg.sql", "."),
        ("pkg.sql", "pkg.sql.dialects", ".dialects"),
        ("pkg", "pkg.database", ".database"),
        ("pkg.sql", "pkg", ".."),
        ("pkg.database.sql", "pkg.api", "...api"),
        ("other", "pkg.sql", "pkg.sql"),
        ("pkg.sql", "other", "other"),
    ],
)
def test_relative_module(importer: str, target: str, expected: str) -> None:
    assert relative_module(importer, target) == expected


@pytest.mark.parametrize(
    ("source", "head"),
    [
        ("import a\nimport b\n\nx = 1\n", "import a\nimport b\n"),
        ("import a\n# note\nimport b\nx = 1\n", "import a\n# note\nimport b\n"),
        ("from a import (\n    b,\n)\nx = 1\n", "from a import (\n    b,\n)\n"),
        ('"""Doc."""\n\nx = 1\n', '"""Doc."""\n'),
        ('"""Doc."""\nfrom __future__ import annotations\n\nx = 1\n', '"""Doc."""\nfrom __future__ import annotations\n'),
        ('import pytest\n\nyaml = pytest.importorskip("yaml")\nimport yaml.constructor\n', "import pytest\n"),
        ("x = 1\nimport a\n", ""),
        ("", ""),
    ],
    ids=["block", "comment-inside", "parenthesized", "docstring-only", "future-only", "gate", "no-leading-block", "empty"],
)
def test_leading_block_end(source: str, head: str) -> None:
    assert leading_block_end(source) == len(head)


MODULE_IMPORT_EDITS = [
    pytest.param(
        "from pkg.sql import client, dialects\nimport os\n",
        "from pkg.sql import dialects\nfrom pkg.database import client\nimport os\n",
        id="first-name",
    ),
    pytest.param(
        "from pkg.sql import dialects, client\nimport os\n",
        "from pkg.sql import dialects\nfrom pkg.database import client\nimport os\n",
        id="last-name",
    ),
    pytest.param(
        "from pkg.sql import client as c, dialects\nimport os\n",
        "from pkg.sql import dialects\nfrom pkg.database import client as c\nimport os\n",
        id="alias-kept",
    ),
    pytest.param(
        "from pkg.sql import (dialects, client,)\n",
        "from pkg.sql import (dialects,)\nfrom pkg.database import client\n",
        id="trailing-comma",
    ),
    pytest.param(
        "from pkg.sql import (\n    dialects, client,  # both\n)\n",
        "from pkg.sql import (\n    dialects,  # both\n)\nfrom pkg.database import client\n",
        id="shared-line-keeps-comment",
    ),
    pytest.param(
        "from pkg.sql import (\n    client,  # moved\n    dialects,  # kept\n)\n",
        "from pkg.sql import (\n    dialects,  # kept\n)\nfrom pkg.database import client\n",
        id="own-line-takes-comment",
    ),
    pytest.param(
        "from pkg.sql import dialects, client; import os\n",
        "from pkg.sql import dialects; import os\nfrom pkg.database import client\n",
        id="semicolon-tail",
    ),
    pytest.param(
        "from pkg.sql import dialects, \\\n    client\nimport os\n",
        "from pkg.sql import dialects\nfrom pkg.database import client\nimport os\n",
        id="backslash",
    ),
    pytest.param(
        b"from pkg.sql import dialects, client\r\nimport os\r\n",
        b"from pkg.sql import dialects\r\nfrom pkg.database import client\r\nimport os\r\n",
        id="crlf",
    ),
    pytest.param(
        "import os\nfrom pkg.sql import dialects, client",
        "import os\nfrom pkg.sql import dialects\nfrom pkg.database import client",
        id="no-final-newline",
    ),
    pytest.param(
        "def use() -> int:\n    from pkg.sql import dialects, client\n\n    return client.X + dialects.D\n",
        "def use() -> int:\n    from pkg.sql import dialects\n    from pkg.database import client\n\n"
        "    return client.X + dialects.D\n",
        id="indented",
    ),
    pytest.param(
        'x = "é😀"; from pkg.sql import dialects, client\n',
        'x = "é😀"; from pkg.sql import dialects\nfrom pkg.database import client\n',
        id="non-ascii-before",
    ),
    pytest.param(
        'import pkg.sql.client\n\ns = "é😀"; v = pkg.sql.client.X\n',
        'import pkg.database.client\n\ns = "é😀"; v = pkg.database.client.X\n',
        id="non-ascii-dotted-use",
    ),
    pytest.param(
        "import pkg.sql as s\n\n\ndef use() -> int:\n    return s.client.X\n",
        "import pkg.database.client\n\n\ndef use() -> int:\n    return pkg.database.client.X\n",
        id="implicit-package-attribute",
    ),
]


@pytest.mark.parametrize(("before", "after"), MODULE_IMPORT_EDITS)
def test_move_module_edits_only_the_reference(tmp_path: Path, before: str | bytes, after: str | bytes) -> None:
    root = _write(tmp_path, {**MODULE_PROJECT, "use.py": before})
    assert _move_module(root, "--apply") == 0
    expected = after if isinstance(after, bytes) else after.encode()
    assert (root / "use.py").read_bytes() == expected


@pytest.mark.parametrize(
    ("init", "moved_init"),
    [
        ("from . import client\n", "from ..database import client\n"),
        ("from . import client as _client\n\nclient = _client\n", "from ..database import client as _client\n\nclient = _client\n"),
    ],
    ids=["by-import", "by-assignment"],
)
def test_explicit_package_binding_keeps_the_use(tmp_path: Path, init: str, moved_init: str) -> None:
    use = "import pkg.sql as s\n\n\ndef use() -> int:\n    return s.client.X\n"
    root = _write(tmp_path, {**MODULE_PROJECT, "pkg/sql/__init__.py": init, "use.py": use})
    assert _move_module(root, "--apply") == 0
    assert (root / "use.py").read_text() == use
    assert (root / "pkg/sql/__init__.py").read_text() == moved_init


SYMBOL_IMPORTER_EDITS = [
    pytest.param(
        "import pkg.a\n\n\ndef use() -> int:\n    return pkg.a.f()\n",
        "import pkg.b\n\n\ndef use() -> int:\n    return pkg.b.f()\n",
        id="dotted-sole-use",
    ),
    pytest.param(
        "import pkg.a\nx = 1\nimport json\n\n\ndef use() -> int:\n    return pkg.a.f() + pkg.a.g() + x + len(json.__name__)\n",
        "import pkg.a\nimport pkg.b\nx = 1\nimport json\n\n\ndef use() -> int:\n"
        "    return pkg.b.f() + pkg.a.g() + x + len(json.__name__)\n",
        id="dotted-surviving-use",
    ),
    pytest.param(
        "import pkg.a as pa\nx = 1\nimport pkg.b\n\n\ndef use() -> int:\n    return pa.f() + x\n",
        "x = 1\nimport pkg.b\n\n\ndef use() -> int:\n    return pkg.b.f() + x\n",
        id="scope-already-binds-dest",
    ),
    pytest.param(
        "from pkg import a\n\n\ndef use() -> int:\n    return a.f()\n",
        "import pkg.b\n\n\ndef use() -> int:\n    return pkg.b.f()\n",
        id="module-from-package",
    ),
]


@pytest.mark.parametrize(("before", "after"), SYMBOL_IMPORTER_EDITS)
def test_move_symbol_importer_edits(tmp_path: Path, before: str, after: str) -> None:
    root = _write(tmp_path, {**SYMBOL_PROJECT, "use.py": before})
    assert _move_f(root, "--apply") == 0
    assert (root / "use.py").read_text() == after


def test_source_import_used_only_by_moved_code_is_removed(tmp_path: Path) -> None:
    source = (
        "import os\nimport sys\n\nVERSION = sys.version\nimport json\n\n\n"
        "def f() -> str:\n    return os.sep\n\n\ndef g() -> str:\n    return json.__name__\n"
    )
    root = _write(tmp_path, {**SYMBOL_PROJECT, "pkg/a.py": source})
    assert _move_f(root, "--apply") == 0
    assert (root / "pkg/a.py").read_text() == (
        "import sys\n\nVERSION = sys.version\nimport json\n\n\ndef g() -> str:\n    return json.__name__\n"
    )
    assert (root / "pkg/b.py").read_text() == "import os\n\n\ndef f() -> str:\n    return os.sep\n"


SOURCE_REMAINING_USE = [
    pytest.param(
        '"""Doc."""\nfrom __future__ import annotations\n\nimport sys\n\nX = 1\nimport json\n\n\n'
        'def f() -> str:\n    return "f"\n\n\ndef g() -> str:\n    return f() + sys.platform + json.__name__\n',
        '"""Doc."""\nfrom __future__ import annotations\n\nimport sys\nfrom pkg.b import f\n\nX = 1\nimport json\n\n\n'
        "def g() -> str:\n    return f() + sys.platform + json.__name__\n",
        id="after-leading-block",
    ),
    pytest.param(
        '"""Doc."""\n\n\ndef f() -> str:\n    return "f"\n\n\ndef g() -> str:\n    return f()\n',
        '"""Doc."""\nfrom pkg.b import f\n\n\ndef g() -> str:\n    return f()\n',
        id="after-docstring",
    ),
    pytest.param(
        'import pytest\n\nyaml = pytest.importorskip("yaml")\nimport yaml.constructor\n\n\n'
        'def f() -> str:\n    return "f"\n\n\ndef g() -> str:\n    return f() + str(yaml.constructor)\n',
        'import pytest\nfrom pkg.b import f\n\nyaml = pytest.importorskip("yaml")\nimport yaml.constructor\n\n\n'
        "def g() -> str:\n    return f() + str(yaml.constructor)\n",
        id="before-gate",
    ),
    pytest.param(
        '__all__ = ["g", "f"]\n\n\ndef f() -> str:\n    return "f"\n\n\ndef g() -> str:\n    return "g"\n',
        '__all__ = ["g"]\n\n\ndef g() -> str:\n    return "g"\n',
        id="all-entry",
    ),
]


@pytest.mark.parametrize(("before", "after"), SOURCE_REMAINING_USE)
def test_move_symbol_source_edits(tmp_path: Path, before: str, after: str) -> None:
    root = _write(tmp_path, {**SYMBOL_PROJECT, "pkg/a.py": before})
    assert _move_f(root, "--apply") == 0
    assert (root / "pkg/a.py").read_text() == after


def test_destination_binding_the_same_module_gets_no_import(tmp_path: Path) -> None:
    root = _write(tmp_path, {
        **SYMBOL_PROJECT,
        "pkg/a.py": "import os\n\n\ndef f() -> str:\n    return os.sep\n",
        "pkg/b.py": "import sys\nimport os\n\nX = os.sep\nimport json\n",
    })
    assert _move_f(root, "--apply") == 0
    dest = (root / "pkg/b.py").read_text()
    assert dest.startswith("import sys\nimport os\n\nX = os.sep\nimport json\n")
    assert dest.count("import os") == 1
    assert "def f() -> str:" in dest


@pytest.mark.parametrize("flags", [(), ("--apply",)], ids=["dry-run", "apply"])
@pytest.mark.parametrize(
    ("dest", "name"),
    [('"""Dest."""\n\nos = "not a module"\n', "os"), ('"""Dest."""\n\nf = "taken"\n', "f")],
    ids=["needed-import", "moved-name"],
)
def test_name_conflict_is_refused_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flags: tuple[str, ...], dest: str, name: str
) -> None:
    root = _write(tmp_path, {
        **SYMBOL_PROJECT,
        "pkg/a.py": "import os\n\n\ndef f() -> str:\n    return os.sep\n",
        "pkg/b.py": dest,
    })
    before = _tree(root)
    assert _move_f(root, *flags) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == message("refactor.name-conflict", name=name, path="pkg/b.py", line=3) + "\n"
    assert _tree(root) == before
