"""The project a Python move reads: its layout, each file read once, module names and the static resolver."""

from __future__ import annotations

from pathlib import Path

from living_architecture.contract import message
from living_architecture.refactor.locators import RefactorError, project_rel
from living_architecture.refactor.patch_targets import SourceFolders
from living_architecture.refactor.python_project import ProjectLayout, Snapshot
from living_architecture.refactor.routing import language_files
from living_architecture.refactor.static_resolver import Module, Resolver

_INIT = "__init__.py"


class MoveProject:
    """The project at `root` as one move reads it."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.layout = ProjectLayout(self.root)
        self.snapshot = Snapshot(self.root)
        self.folders = SourceFolders([*self.layout.source_folders(), self.root])
        self.resolver = Resolver(self.folders, self._read)
        self._roots = {"", *self.layout.source_rels}
        self._modules: dict[str, Module | None] = {}
        self._files: list[str] | None = None

    def _read(self, path: Path) -> str:
        resolved = path.resolve()
        if resolved.is_relative_to(self.root):
            return self.snapshot.text(resolved.relative_to(self.root).as_posix())
        return path.read_text(encoding="utf-8")

    def rel(self, path: str) -> str:
        """`path` relative to the project (`""` for its root); `refactor.outside-project` when outside."""
        rel = project_rel(self.root, path)
        return "" if rel == "." else rel

    def destination(self, path: str, *, folder: bool) -> str:
        """`--dest` as an existing directory (`folder`) or file of the project."""
        resolved = Path(path).resolve()
        if resolved.is_relative_to(self.root) and not (resolved.is_dir() if folder else resolved.is_file()):
            raise RefactorError(message("refactor.destination-missing", path=path))
        return self.rel(path)

    def files(self) -> list[str]:
        """The project's Python files that decode, by path."""
        if self._files is None:
            rels = [p.relative_to(self.root).as_posix() for p in language_files(self.root, "python")]
            self._files = sorted(rel for rel in rels if self.snapshot.undecodable(rel) is None)
        return self._files

    def dotted(self, rel: str) -> str:
        """The module name of file or directory `rel`: through packages, and through directories without
        `__init__.py` (namespace packages) up to a source folder."""
        if rel in self._roots:
            return ""
        segments = rel.split("/")
        if segments[-1] == _INIT:
            segments = segments[:-1]
        elif segments[-1].endswith(".py"):
            segments[-1] = segments[-1][:-3]
        name, folder = [segments[-1]], segments[:-1]
        while folder:
            here = "/".join(folder)
            if here in self._roots and not (self.root / here / _INIT).is_file():
                break
            name.insert(0, folder[-1])
            folder = folder[:-1]
        return ".".join(name)

    def names(self, rel: str) -> list[str]:
        """Every module name file or package `rel` is imported under: `dotted` first, then one per other source folder
        holding it."""
        path = (self.root / rel).resolve()
        target = path / _INIT if path.is_dir() else path
        found = [self.dotted(rel)]
        for folder in self.folders.folders:
            base = folder.resolve()
            if not path.is_relative_to(base) or path == base:
                continue
            name = ".".join(path.relative_to(base).with_suffix("").parts) if path.suffix == ".py" else ".".join(
                path.relative_to(base).parts)
            name = name.removesuffix(".__init__")
            hit = self.folders.file(name) if all(p.isidentifier() for p in name.split(".")) else None
            if hit is not None and hit[0] == target and name not in found:
                found.append(name)
        return found

    def package(self, rel: str) -> str:
        """The package relative imports in file `rel` start from."""
        dotted = self.dotted(rel)
        return dotted if Path(rel).name == _INIT else dotted.rpartition(".")[0]

    def module(self, rel: str) -> Module | None:
        """File `rel`'s static model, registered with the resolver under its module name; None when it does not
        parse."""
        if rel not in self._modules:
            source = self.snapshot.source(rel)
            found: Module | None = None
            if source.tree is not None:
                dotted = self.dotted(rel)
                found = Module(source.tree, dotted.split("."), Path(rel).name == _INIT, self.root / rel)
                self.resolver.modules.setdefault(dotted, found)
            self._modules[rel] = found
        return self._modules[rel]
