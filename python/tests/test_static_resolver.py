"""la's static resolver: a package's own `from . import x` and a star import of a listed submodule reach the
submodule; a cyclic re-export stays unresolved."""

from __future__ import annotations

from pathlib import Path

import pytest

from living_architecture.refactor.static_resolver import Resolver, Value


def _resolver(root: Path, files: dict[str, str]) -> Resolver:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")

    def finder(dotted: str) -> tuple[Path, bool] | None:
        base = root / dotted.replace(".", "/")
        if (base / "__init__.py").is_file():
            return base / "__init__.py", True
        return (base.with_suffix(".py"), False) if base.with_suffix(".py").is_file() else None

    return Resolver(finder)


@pytest.mark.parametrize(
    ("files", "module", "name", "value"),
    [
        ({"pkg/__init__.py": "from . import old\n", "pkg/old.py": "X = 1\n"}, "pkg", "old", ("module", "pkg.old")),
        ({"pkg/__init__.py": "from pkg import old\n", "pkg/old.py": "X = 1\n"}, "pkg", "old", ("module", "pkg.old")),
        ({"pkg/__init__.py": "from . import gone\n"}, "pkg", "gone", None),
        ({"pkg/__init__.py": "from pkg.a import x\n", "pkg/a.py": "from pkg import x\n", "pkg/x.py": "Y = 1\n"},
         "pkg.a", "x", None),
        ({"pkg/__init__.py": "", "pkg/sub/__init__.py": '__all__ = ["inner"]\n', "pkg/sub/inner.py": "Y = 1\n",
          "use.py": "from pkg.sub import *\n"}, "use", "inner", ("module", "pkg.sub.inner")),
        ({"pkg/__init__.py": "", "pkg/sub/__init__.py": "", "pkg/sub/inner.py": "Y = 1\n",
          "use.py": "from pkg.sub import *\n"}, "use", "inner", None),
        ({"m.py": "from m import x\n", "m/x.py": "Y = 1\n"}, "m", "x", None),
        ({"m.py": '__all__ = ["x"]\n', "m/x.py": "Y = 1\n", "use.py": "from m import *\n"}, "use", "x", None),
    ],
    ids=["own-relative-import", "own-absolute-import", "own-import-of-nothing", "cyclic-reexport", "star-listed-submodule",
         "star-unlisted-submodule",
         "module-shadowing-directory", "star-of-module-shadowing-directory"],
)
def test_a_module_attribute_resolves(tmp_path: Path, files: dict[str, str], module: str, name: str, value: Value) -> None:
    assert _resolver(tmp_path, files).member(module, name) == value
