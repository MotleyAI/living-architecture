"""rope 1.15's project rules, ported verbatim: source folders, module names, module lookup and the PEP-263 coding
cookie, so a rename reads the project as rope did without building a rope project."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from functools import cached_property
from pathlib import Path

_IGNORED = ["*.pyc", "*~", ".ropeproject", ".hg", ".svn", "_svn", ".git", ".tox", ".venv", "venv", ".mypy_cache",
            ".pytest_cache"]
_CODING = b"^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)"


def _realpath(path: str) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def _pattern(pattern: str) -> re.Pattern[str]:
    """rope's `_ResourceMatcher` pattern."""
    body = pattern.replace(".", "\\.").replace("*", "[^/]*").replace("?", "[^/]").replace("//", "/(.*/)?")
    return re.compile("^(.*/)?" + body + "(/.*)?$")


def _parent(rel: str) -> str:
    return "/".join(rel.split("/")[:-1])


def _name(rel: str) -> str:
    return rel.split("/")[-1]


def _is_resource(path: str) -> bool:
    """rope's `get_resource` finds `path`: it exists as a file or a directory."""
    return os.path.exists(path) and (os.path.isfile(path) or os.path.isdir(path))


def _find_in(folder: str, modname: str) -> str | None:
    """rope's `_find_module_in_folder` over real paths: a package directory, else a `.py` module."""
    module = folder
    packages = modname.split(".")
    for pkg in packages[:-1]:
        child = os.path.join(module, pkg)
        if not (os.path.isdir(module) and _is_resource(child)):
            return None
        module = child
    if os.path.isdir(module):
        last = os.path.join(module, packages[-1])
        if _is_resource(last) and os.path.isdir(last):
            return last
        source = last + ".py"
        if _is_resource(source) and not os.path.isdir(source):
            return source
    return None


class ProjectLayout:
    """The project at `root` as rope 1.15 lays it out, configured by `[tool.rope]` in its `pyproject.toml`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.address = _realpath(str(root))
        prefs = self._prefs()
        self._ignored = [_pattern(p) for p in prefs.get("ignored_resources", _IGNORED)]
        self._custom = [p for p in prefs.get("source_folders", []) if isinstance(p, str)]
        self._python_path = [p for p in prefs.get("python_path", []) if isinstance(p, str)]

    def _prefs(self) -> dict[str, list[str]]:
        try:
            data = tomllib.loads(Path(self.address, "pyproject.toml").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            return {}
        table = data.get("tool", {}).get("rope", {})
        return {k: v for k, v in table.items() if isinstance(v, list)} if isinstance(table, dict) else {}

    def path(self, rel: str) -> str:
        """A project resource's real path, as rope builds it."""
        return os.path.join(self.address, *rel.split("/"))

    def _children(self, rel: str) -> list[str]:
        try:
            names = os.listdir(self.path(rel))
        except OSError:
            return []
        out: list[str] = []
        for name in names:
            child = f"{rel}/{name}" if rel else name
            if not _is_resource(self.path(child)):
                continue
            if any(p.match(child) for p in self._ignored) or os.path.islink(self.path(child)):
                continue
            out.append(child)
        return out

    def _is_package(self, rel: str) -> bool:
        init = self.path(f"{rel}/__init__.py" if rel else "__init__.py")
        return _is_resource(init) and not os.path.isdir(init)

    def _find_source_folders(self, rel: str) -> list[str]:
        folders = [c for c in self._children(rel) if os.path.isdir(self.path(c))]
        if any(self._is_package(c) for c in folders):
            return [rel]
        out: list[str] = []
        files = [c for c in self._children(rel) if not os.path.isdir(self.path(c))]
        if any(_name(c).endswith(".py") for c in files):
            out.append(rel)
        for child in [c for c in self._children(rel) if os.path.isdir(self.path(c))]:
            out.extend(self._find_source_folders(child))
        return out

    @cached_property
    def source_rels(self) -> list[str]:
        """The source folders, as project-relative paths (`""` for the root)."""
        custom = [p.strip("/") for p in self._custom if os.path.isdir(self.path(p.strip("/")))]
        return [*custom, *self._find_source_folders("")]

    def source_folders(self) -> list[Path]:
        return [Path(self.path(rel)) for rel in self.source_rels]

    def _rel(self, path: Path) -> str:
        for base in (self.root, Path(self.address)):
            if path.is_relative_to(base):
                rel = path.relative_to(base).as_posix()
                return "" if rel == "." else rel
        raise ValueError(path)

    def modname(self, path: Path) -> str:
        """rope's `libutils.modname` of the project file or folder at `path`."""
        rel = self._rel(path)
        if os.path.isdir(self.path(rel)):
            module_name, folder = _name(rel), _parent(rel)
        elif _name(rel) == "__init__.py":
            module_name, folder = _name(_parent(rel)), _parent(_parent(rel))
        else:
            module_name, folder = _name(rel)[:-3], _parent(rel)
        while folder != _parent(folder) and _is_resource(self.path(f"{folder}/__init__.py" if folder else "__init__.py")):
            module_name = _name(folder) + "." + module_name
            folder = _parent(folder)
        return module_name

    def find_module(self, modname: str, folder: Path | None = None) -> Path | None:
        """rope's `Project.find_module`: the source folders, then the Python path, then `folder`."""
        for rel in self.source_rels:
            found = _find_in(self.path(rel), modname)
            if found is not None:
                return Path(found)
        for src in [*self._python_path, *sys.path]:
            base = _realpath(src)
            if _is_resource(base):
                found = _find_in(base, modname)
                if found is not None:
                    return Path(_realpath(found))
        if folder is not None:
            found = _find_in(os.fspath(folder), modname)
            if found is not None:
                return Path(found)
        return None

    def module_file(self, modname: str) -> Path | None:
        """The file of module `modname`, a package's `__init__.py`; None when it has none."""
        found = self.find_module(modname) if modname else None
        if found is not None and found.is_dir():
            init = found / "__init__.py"
            return init if _is_resource(os.fspath(init)) else None
        return found


def _find_coding(text: bytes) -> str | None:
    try:
        start = text.index(b"coding") + len(b"coding")
        if text[start] not in b"=:":
            return None
        start += 1
        while start < len(text) and chr(text[start]).isspace():
            start += 1
        end = start
        while end < len(text):
            c = text[end]
            if not chr(c).isalnum() and c not in b"-_":
                break
            end += 1
        return text[start:end].decode("utf-8")
    except ValueError:
        return None


def read_str_coding(source: bytes | str) -> str | None:
    """rope's PEP-263 coding cookie of the first two lines; None when there is none."""
    if isinstance(source, bytes):
        lines: list[bytes] = source.split(b"\n", 2)[:2]
        pattern: re.Pattern[bytes] = re.compile(_CODING)
        for line in lines:
            if pattern.match(line):
                return _find_coding(line)
        return None
    text_pattern = re.compile(_CODING.decode("ascii"))
    for text_line in source.split("\n", 2)[:2]:
        if text_pattern.match(text_line):
            return _find_coding(text_line.encode("utf-8"))
    return None
