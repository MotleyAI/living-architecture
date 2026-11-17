"""The imports a moved symbol's code needs in its destination, computed from the source module's bindings: each import
made absolute and cut to the names the code reads, merged and ordered as rope 1.15 organized them (`__future__`,
standard library, third-party, project; plain imports before `from` imports, then by text)."""

from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path

from living_architecture.refactor.move_edits import File
from living_architecture.refactor.moved_symbol import MovedSymbol
from living_architecture.refactor.static_resolver import ImportItem

_FUTURE = "__future__"
_BUILTINS = frozenset(dir(builtins))


class GuardedImport(Exception):
    """The moved code reads a name the source binds only by the import at `path`:`line`, inside a guard."""

    def __init__(self, path: str, line: int) -> None:
        super().__init__(path, line)
        self.path = path
        self.line = line


class Statement:
    """An import statement: `import` names when `module` is None, else `from module import` names or `*`."""

    def __init__(self, module: str | None, names: list[tuple[str, str | None]], *, star: bool = False) -> None:
        self.module = module
        self.names = names
        self.star = star

    def bound(self, pair: tuple[str, str | None]) -> tuple[str, str]:
        """The name an item binds and the dotted object it binds it to."""
        imported, alias = pair
        if self.module is not None:
            return alias or imported, f"{self.module}.{imported}"
        return (alias, imported) if alias else (imported.split(".")[0], imported.split(".")[0])

    def text(self, names: list[tuple[str, str | None]] | None = None) -> str:
        items = ", ".join(f"{n} as {a}" if a else n for n, a in (self.names if names is None else names))
        if self.star:
            return f"from {self.module} import *"
        return f"from {self.module} import {items}" if self.module is not None else f"import {items}"

    def lines(self, names: list[tuple[str, str | None]]) -> str:
        """The statement holding `names`, an `import` of several names as one line each."""
        if self.module is not None or self.star:
            return self.text(names)
        return "\n".join(self.text([pair]) for pair in names)

    def merge(self, other: Statement) -> bool:
        """Take `other` into this statement as rope's duplicate removal does; whether it was taken."""
        if self.module is not None or other.module is not None:
            if self.module != other.module or self.module is None:
                return False
            if self.star or other.star:
                self.star, self.names = True, []
                return True
            self.names += [pair for pair in other.names if pair not in self.names]
            return True
        if len(self.names) == len(other.names) == 1 and self.names[0][1] is None and other.names[0][1] is None:
            mine, theirs = self.names[0][0], other.names[0][0]
            if mine.startswith(theirs + "."):
                return True
            if theirs.startswith(mine + "."):
                self.names = list(other.names)
                return True
        return self.names == other.names


class Needed:
    """What the destination gains: `__future__` statements, the ordered imports after its leading import block, and the
    imports under `if TYPE_CHECKING:`."""

    def __init__(self, future: list[Statement], regular: list[Statement], checking: list[Statement]) -> None:
        self.future = future
        self.regular = regular
        self.checking = checking


def is_type_checking(stmt: ast.stmt) -> bool:
    """A top-level `if TYPE_CHECKING:` (or `if typing.TYPE_CHECKING:`)."""
    test = stmt.test if isinstance(stmt, ast.If) else None
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


class _Origin:
    """The source module as the moved code reads it."""

    def __init__(self, origin: File, moved: MovedSymbol) -> None:
        self.file = origin
        self.moved = moved
        start, end = moved.region
        self.read = list(dict.fromkeys(
            node.id for node, scope in origin.names
            if start <= origin.offset(node) < end and node.id != moved.name and scope.resolving(node.id) is origin.top
        ))
        self.tree_body = origin.source.tree.body if origin.source.tree is not None else []

    def _checked(self, item: ImportItem) -> bool:
        guard = item.guard
        return guard is not None and any(guard is s for s in self.tree_body) and is_type_checking(guard) and any(
            item.stmt is s for s in getattr(guard, "body", [])
        )

    def classify(self) -> tuple[set[str], set[str], set[str], list[str]]:
        """The read names bound by a top-level import, by a `TYPE_CHECKING` import, by any other binding (in binding
        order), and by none; `GuardedImport` for a name bound only by an import under another guard."""
        imported: set[str] = set()
        checking: set[str] = set()
        unbound: set[str] = set()
        defined: list[str] = []
        top = self.file.top
        for name in self.read:
            nodes = self.file.bound[top].get(name, [])
            items = [(node, item) for node in nodes if (item := self.file.item(node)) is not None and item.scope is top]
            if any(item.guard is None for _, item in items):
                imported.add(name)
            elif items and len(items) == len(nodes) and all(self._checked(item) for _, item in items):
                checking.add(name)
            elif items:
                guarded = next((item for _, item in items if not self._checked(item)), items[0][1])
                raise GuardedImport(self.file.rel, guarded.stmt.lineno)
            elif nodes:
                defined.append(name)
            else:
                unbound.add(name)
        order = {name: i for i, (_, name, _) in reversed(list(enumerate(self.file.binder.bound)))}
        defined.sort(key=lambda n: order.get(n, 0))
        return imported, checking, unbound, defined

    def statements(self, names: set[str], *, checking: bool) -> list[Statement]:
        """The source's top-level imports (or those under `if TYPE_CHECKING:`) binding `names` to what their last
        binding does, made absolute and cut to them, in source order."""
        out: list[Statement] = []
        top = self.file.top
        last = {name: self.file.obj(nodes[-1]) for name, nodes in self.file.bound[top].items() if name in names}
        for stmt, scope, guard in self.file.binder.imports:
            in_block = guard is not None
            if scope is not top or in_block != checking:
                continue
            if checking and not self._checked(self.file.binder.import_items[id(stmt.names[0])]):
                continue
            if isinstance(stmt, ast.Import):
                found = Statement(None, [(a.name, a.asname) for a in stmt.names])
            else:
                module = self.file.binder.from_module(stmt)
                if module is None or module == _FUTURE or stmt.names[0].name == "*":
                    continue
                found = Statement(module, [(a.name, a.asname) for a in stmt.names])
            found.names = [pair for pair in found.names if found.bound(pair)[0] in names and found.bound(pair)[1] == last[found.bound(pair)[0]]]
            if found.names:
                out.append(found)
        return out


def _merged(statements: list[Statement]) -> list[Statement]:
    kept: list[Statement] = []
    for stmt in statements:
        if not any(earlier.merge(stmt) for earlier in kept):
            kept.append(stmt)
    return kept


def _category(origin: File, stmt: Statement, folder: Path) -> int:
    """0 `__future__`, 1 standard library, 2 third-party, 3 the project."""
    name = stmt.module if stmt.module is not None else stmt.names[0][0]
    if origin.project.layout.find_module(name, folder, python_path=False) is not None:
        return 3
    if name == _FUTURE:
        return 0
    return 1 if name.split(".")[0] in sys.stdlib_module_names else 2


def ordered(origin: File, statements: list[Statement], new: str) -> list[Statement]:
    folder = (origin.project.root / origin.rel).parent
    kept = [s for s in _merged(statements) if (s.names or s.star) and s.module != new]
    return sorted(kept, key=lambda s: (_category(origin, s, folder), s.module is not None, s.text()))


def _stars(origin: _Origin, unbound: set[str]) -> list[Statement]:
    """Each name a first-party star import of the source binds, imported by name; when a name stays unexplained, each
    star import the resolver cannot list, as it is."""
    file = origin.file
    resolver = file.project.resolver
    out: list[Statement] = []
    unlisted: list[str] = []
    explained: set[str] = set()
    for stmt, scope, guard in file.binder.imports:
        if scope is not file.top or guard is not None or not isinstance(stmt, ast.ImportFrom) or stmt.names[0].name != "*":
            continue
        module = file.binder.from_module(stmt)
        if module is None:
            continue
        if resolver.load(module) is None:
            unlisted.append(module)
            continue
        names = [n for n in sorted(unbound) if resolver.star_values(module, n)]
        explained.update(names)
        out += [Statement(module, [(n, None)]) for n in names]
    if any(n not in explained and n not in _BUILTINS for n in unbound):
        out += [Statement(module, [], star=True) for module in unlisted]
    return out


def needed_imports(origin: File, moved: MovedSymbol, old: str, new: str) -> Needed:
    """The imports the code of `moved` (in module `old`) needs in module `new`."""
    reader = _Origin(origin, moved)
    imported, checking, unbound, defined = reader.classify()
    regular = reader.statements(imported, checking=False)
    if defined:
        regular.append(Statement(old, [(n, None) for n in defined]))
    regular += _stars(reader, unbound)
    future = [
        Statement(_FUTURE, [(a.name, a.asname) for a in stmt.names])
        for stmt, scope, guard in origin.binder.imports
        if isinstance(stmt, ast.ImportFrom) and stmt.module == _FUTURE and scope is origin.top and guard is None
    ]
    return Needed(future, ordered(origin, regular, new), ordered(origin, reader.statements(checking, checking=True), new))
