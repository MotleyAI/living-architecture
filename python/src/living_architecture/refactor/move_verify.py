"""The resolver comparison of a Python move: the project as the move would leave it, built in a temporary directory,
must resolve every name as the project as read does."""

from __future__ import annotations

import ast
import os
import shutil
import tempfile
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import message
from living_architecture.refactor.locators import RefactorError
from living_architecture.refactor.move_project import MoveProject
from living_architecture.refactor.moved_symbol import MovedSymbol
from living_architecture.refactor.static_resolver import Module, Scope, Value, node_key
from living_architecture.refactor.writer import FileMove, FileWrite, apply

# A value in the form that compares across a move: "?" (unknown), else a tuple led by its kind.
Canonical = tuple[str | int, ...] | str
# A read: its value, the attributes read past it, and its order against the module's top-level bindings.
Key = tuple[Canonical, str, str]
# Where a read is written: line, column, text.
Site = tuple[int, int, str]
# A read as the comparison expects it: the file it was read in, its key and its site.
Entry = tuple[str, Key, Site]
Final = Callable[[str], str]
Difference = tuple[str, int, str]

_TYPE_CHECKING: Canonical = ("typing", "TYPE_CHECKING")
_ALL = "__all__"


class Fingerprint(BaseModel):
    """What one file resolves to: its reads counted by key and where each is written, its top-level names, and its
    literal `__all__`."""

    model_config = ConfigDict(frozen=True)

    reads: Counter[Key]
    sites: dict[Key, list[Site]]
    names: dict[str, Canonical]
    exports: set[str] | None


class Moved(BaseModel):
    """The declaration a `move-symbol` moves, on one side of the move: in `file`, found by its `keys` before the move
    and by `name` after it (`keys` None); `dest` is the file it ends in."""

    model_config = ConfigDict(frozen=True)

    file: str
    keys: frozenset[str] | None
    name: str
    dest: str


def _same(rel: str) -> str:
    return rel


def _top(module: Module, scope: Scope) -> bool:
    """`scope` is the module's own, or an annotation scope directly under it."""
    return scope is module.scope or (scope.kind == "annotation" and scope.parent is module.scope)


def _deferred(scope: Scope | None) -> bool:
    """`scope` is, or lies in, a function."""
    while scope is not None:
        if scope.kind == "function":
            return True
        scope = scope.parent
    return False


def _position(node: ast.AST) -> tuple[int, int]:
    return getattr(node, "lineno", 0), getattr(node, "col_offset", 0)


def _prefixes(node: ast.expr) -> list[ast.expr] | None:
    """The chain's prefixes from its root name outward; None when its innermost receiver is no name."""
    chain = [node]
    while isinstance(chain[0], ast.Attribute):
        chain.insert(0, chain[0].value)
    return chain if isinstance(chain[0], ast.Name) else None


def _chains(module: Module) -> Iterator[tuple[list[ast.expr], Scope, bool]]:
    """Every maximal name or attribute chain read, with its scope and whether an annotation reads it."""
    binder = module.binder
    found: list[tuple[ast.expr, Scope, bool]] = [(node, scope, False) for node, scope in binder.loads]
    for expr, scope in binder.annotations:
        found += [(n, scope, True) for n in ast.walk(expr)
                  if isinstance(n, ast.Attribute) or (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load))]
    inner = {id(node.value) for node, _, _ in found if isinstance(node, ast.Attribute)}
    for node, scope, annotated in found:
        chain = None if id(node) in inner else _prefixes(node)
        if chain is not None:
            yield chain, scope, annotated


class _Bound:
    """Where a module's top-level names are first bound outside any function."""

    def __init__(self, module: Module) -> None:
        binder = module.binder
        self.first: dict[str, tuple[int, int]] = {}
        for scope, name, node in binder.bound:
            if scope.owner(name) is module.scope and not _deferred(scope):
                self.first[name] = min(self.first.get(name, _position(node)), _position(node))
        self.star = min((_position(node) for node in binder.star_nodes), default=None)

    def before(self, name: str, at: tuple[int, int]) -> bool:
        first = self.first.get(name)
        return (first is not None and first < at) or (self.star is not None and self.star < at)


def _order(module: Module, scope: Scope, root: ast.Name, annotated: bool, bound: _Bound) -> str:
    if annotated:
        return "annotation"
    if _deferred(scope):
        return "deferred"
    if scope.resolving(root.id) is not module.scope:
        return "local"
    return "bound" if bound.before(root.id, _position(root)) else "not-yet"


def _ordinals(module: Module) -> dict[str, int]:
    """Each module-level declaration's index among those of its name, by position."""
    binder = module.binder
    top = sorted((_position(node), key) for key, node in binder.decls.items() if _top(module, binder.enclosing[key]))
    seen: Counter[str] = Counter()
    found: dict[str, int] = {}
    for _, key in top:
        name = _declared(binder.decls[key])
        found[key] = seen[name]
        seen[name] += 1
    return found


def _declared(node: ast.AST) -> str:
    return str(getattr(node, "name", None) or getattr(node, "id", ""))


def _written(chain: list[ast.expr]) -> str:
    """The chain as source text."""
    return ".".join(node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "") for node in chain)


class _Side:
    """One side of a move: `project`, with each file's fingerprint and each value's canonical form."""

    def __init__(self, project: MoveProject, final: Final = _same, moved: Moved | None = None) -> None:
        self.project = project
        self.final = final
        self.moved = moved
        self._ordinals: dict[int, dict[str, int]] = {}
        self._files: dict[int, str | None] = {}
        self._modules: dict[str, Canonical] = {}
        self._prints: dict[str, Fingerprint] = {}

    def rel(self, path: Path | None) -> str | None:
        """The file at `path`, symlinks followed, relative to the project root; None outside it."""
        resolved = path.resolve() if path is not None else None
        if resolved is None or not resolved.is_relative_to(self.project.root):
            return None
        return resolved.relative_to(self.project.root).as_posix()

    def _file(self, module: Module) -> str | None:
        if id(module) not in self._files:
            self._files[id(module)] = self.rel(module.path)
        return self._files[id(module)]

    def canonical(self, value: Value) -> Canonical:
        if value is None:
            return "?"
        if value[0] == "module":
            return self._module(value[1])
        if value[0] == "decl":
            return self._decl(value)
        return value

    def _module(self, dotted: str) -> Canonical:
        if dotted not in self._modules:
            found = self.project.folders(dotted)
            rel = self.rel(found[0]) if found is not None else None
            self._modules[dotted] = ("module", self.final(rel) if rel is not None else dotted)
        return self._modules[dotted]

    def _decl(self, value: Value) -> Canonical:
        found = self.project.resolver.declaration(value)
        if found is None:
            return ("opaque", str(value))
        module, node = found
        key, name = node_key(node), _declared(node)
        if not _top(module, module.binder.enclosing[key]):
            return ("local", name)
        rel = self._file(module)
        if rel is None:
            return ("opaque", str(value))
        moved = self.moved
        if moved is not None and rel == moved.file and (name == moved.name if moved.keys is None else key in moved.keys):
            return ("decl", moved.dest, name, "moved")
        if id(module) not in self._ordinals:
            self._ordinals[id(module)] = _ordinals(module)
        return ("decl", self.final(rel), name, self._ordinals[id(module)][key])

    def agreed(self, values: list[Value]) -> Canonical:
        """The one canonical value every binding has, else "?"."""
        found = {self.canonical(value) for value in values}
        return found.pop() if len(found) == 1 else "?"

    def _values(self, module: Module, scope: Scope, expr: ast.expr) -> list[Value]:
        """The value of each binding behind `expr`; an attribute of a module is read from that module's own bindings,
        and one only a module-level `__getattr__` answers has no value."""
        resolver = self.project.resolver
        if not isinstance(expr, ast.Attribute):
            return resolver.values(module, scope, expr)
        base = self._values(module, scope, expr.value)
        first = base[0] if base else None
        if first is None or first[0] != "module" or any(value != first for value in base):
            return [None]
        target = resolver.load(first[1])
        found = resolver.module_values(target, expr.attr) if target is not None else []
        if not found and target is not None and target.scope.bindings.get("__getattr__"):
            return [None]
        return found or [resolver.member(first[1], expr.attr)]

    def _read(self, module: Module, scope: Scope, chain: list[ast.expr]) -> tuple[Canonical, str]:
        """The canonical value of the chain's longest prefix that resolves, and the attributes after it."""
        attrs = _written(chain[1:]).split(".") if len(chain) > 1 else []
        for count in range(len(chain) - 1, -1, -1):
            value = self.agreed(self._values(module, scope, chain[count]))
            if value != "?":
                return value, ".".join(attrs[count:])
        root = chain[0]
        assert isinstance(root, ast.Name)
        kind = "opaque" if self.project.resolver.values(module, scope, root) else "unbound"
        return (kind, root.id), ".".join(attrs)

    def _reads(self, module: Module) -> Iterator[tuple[Key, Site]]:
        bound = _Bound(module)
        for chain, scope, annotated in _chains(module):
            root = chain[0]
            assert isinstance(root, ast.Name)
            value, tail = self._read(module, scope, chain)
            if value != _TYPE_CHECKING:
                line, col = _position(root)
                yield (value, tail, _order(module, scope, root, annotated, bound)), (line, col, _written(chain))

    def _names(self, module: Module) -> dict[str, Canonical]:
        resolver = self.project.resolver
        return {name: self.agreed(resolver.module_values(module, name))
                for name, bindings in module.scope.bindings.items() if bindings}

    def fingerprint(self, rel: str) -> Fingerprint:
        """File `rel`'s fingerprint; the file parses."""
        if rel not in self._prints:
            module = self.project.module(rel)
            assert module is not None
            sites: dict[Key, list[Site]] = {}
            for key, site in self._reads(module):
                sites.setdefault(key, []).append(site)
            reads = Counter({key: len(found) for key, found in sites.items()})
            self._prints[rel] = Fingerprint(reads=reads, sites=sites, names=self._names(module),
                                            exports=module.all_names)
        return self._prints[rel]


def fingerprint(project: MoveProject, rel: str, final: Final = _same, moved: Moved | None = None) -> Fingerprint:
    """The fingerprint of `project`'s file `rel`, its paths mapped through `final`."""
    return _Side(project, final, moved).fingerprint(rel)


# ---- the project after the move


def _copy(project: MoveProject, root: Path) -> None:
    """Copy the project's directories, Python files and root `pyproject.toml` to `root`, each file the project reads
    as it was read."""
    read = set(project.files())
    copied: set[str] = set()
    for rel, is_dir in project.layout.resources():
        if is_dir:
            (root / rel).mkdir(parents=True, exist_ok=True)
        elif rel in read:
            (root / rel).write_bytes(project.snapshot.data(rel))
            copied.add(rel)
        elif rel.endswith(".py") or rel == "pyproject.toml":
            shutil.copyfile(project.root / rel, root / rel)
    for rel in read - copied:
        _copy_skipped(project, root, rel)


def _copy_skipped(project: MoveProject, root: Path, rel: str) -> None:
    """A file the layout skips: a symlink into the project as one to the same file of the copy, else its bytes."""
    source, target = project.root / rel, root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    resolved = source.resolve()
    if source.is_symlink() and resolved.is_relative_to(project.root):
        os.symlink(root / resolved.relative_to(project.root), target)
    else:
        target.write_bytes(project.snapshot.data(rel))


def _final(moves: list[FileMove]) -> Final:
    def final(rel: str) -> str:
        for move in moves:
            if rel == move.rel or rel.startswith(move.rel + "/"):
                return move.dest + rel[len(move.rel):]
        return rel

    return final


def _share(before: MoveProject, after: MoveProject, written: set[str], final: Final) -> None:
    """Give `after` the parsed module of each file the move neither writes nor moves."""
    for rel in before.files():
        module = before.module(rel) if rel not in written and final(rel) == rel else None
        if module is not None and not (after.root / rel).is_symlink():
            after.adopt(rel, module)


# ---- the comparison


def _entries(rel: str, found: Fingerprint) -> list[Entry]:
    return [(rel, key, site) for key, sites in found.sites.items() for site in sites]


class _Expected:
    """The reads and exports each file must have after the move, from the fingerprints before it."""

    def __init__(self, before: _Side, symbol: tuple[MovedSymbol, str, str] | None) -> None:
        self.before = before
        self.symbol = symbol
        self.inside: list[Entry] = []
        self.outside: list[Entry] = []
        if symbol is not None:
            moved, source, _ = symbol
            text = before.project.snapshot.source(source)
            start, end = moved.region
            for entry in _entries(source, before.fingerprint(source)):
                within = start <= text.line_start(entry[2][0]) < end
                (self.inside if within else self.outside).append(entry)

    def reads(self, rel: str) -> list[Entry]:
        if self.symbol is not None and rel == self.symbol[1]:
            return self.outside
        own = _entries(rel, self.before.fingerprint(rel))
        return own + self.inside if self.symbol is not None and rel == self.symbol[2] else own

    def exports(self, rel: str) -> set[str] | None:
        found = self.before.fingerprint(rel).exports
        if found is not None and self.symbol is not None and rel == self.symbol[1]:
            return found - {self.symbol[0].name}
        return found


def _bound_earlier(added: Counter[Key], missing: Counter[Key]) -> None:
    """Pair off each read that is now bound with one of the same value that was not yet: no difference."""
    for key in [key for key in added if key[2] == "bound"]:
        was = (key[0], key[1], "not-yet")
        paired = min(added[key], missing[was])
        added.subtract({key: paired})
        missing.subtract({was: paired})
    for counter in (added, missing):
        for key in [key for key, count in counter.items() if count <= 0]:
            del counter[key]


def _read_difference(shown: str, expected: list[Entry], found: Fingerprint) -> Difference | None:
    """The first read counted more often than expected, in the new text; else the first counted less often, in the
    old one."""
    counts = Counter(key for _, key, _ in expected)
    added, missing = found.reads - counts, counts - found.reads
    _bound_earlier(added, missing)
    more = [site for key in added for site in found.sites[key]]
    if more:
        line, _, text = min(more)
        return shown, line, text
    fewer = [(site, rel) for rel, key, site in expected if key in missing]
    if fewer:
        (line, _, text), rel = min(fewer)
        return rel, line, text
    return None


def _first_binding(module: Module, name: str) -> int:
    lines = [_position(node)[0] for scope, bound, node in module.binder.bound
             if bound == name and scope.owner(name) is module.scope]
    return min(lines, default=1)


def _name_difference(shown: str, old: Fingerprint, new: Fingerprint, module: Module) -> Difference | None:
    for name in sorted(old.names.keys() & new.names.keys()):
        if old.names[name] != new.names[name]:
            return shown, _first_binding(module, name), name
    return None


def _all_line(module: Module) -> int:
    """The line of the last top-level `__all__` assignment."""
    line = 1
    for stmt in module.tree.body:
        targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target] if isinstance(stmt, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == _ALL for t in targets):
            line = stmt.lineno
    return line


def _compare(before: _Side, after: _Side, expected: _Expected) -> Difference | None:
    """The first difference between the two sides, files in the order of their paths after the move."""
    project = before.project
    rels = sorted((rel for rel in project.files() if project.module(rel) is not None), key=before.final)
    modules = {rel: after.project.module(before.final(rel)) for rel in rels}
    for rel in rels:
        shown = before.final(rel)
        module = modules[rel]
        if module is None:
            raise RefactorError(message("refactor.unparsable", path=shown))
        new = after.fingerprint(shown)
        found = (_read_difference(shown, expected.reads(rel), new)
                 or _name_difference(shown, before.fingerprint(rel), new, module))
        if found is None and expected.exports(rel) != new.exports:
            found = shown, _all_line(module), _ALL
        if found is not None:
            return found
    return None


def verify(project: MoveProject, symbol: tuple[MovedSymbol, str, str] | None, writes: list[FileWrite],
           moves: list[FileMove]) -> None:
    """`refactor.resolution-changed` when a name would resolve differently once `writes` and `moves` are applied;
    `symbol` is a `move-symbol`'s declaration with its source and destination files."""
    final = _final(moves)
    sides: tuple[Moved, Moved] | tuple[None, None] = (None, None)
    if symbol is not None:
        moved, source, dest = symbol
        sides = (Moved(file=source, keys=frozenset(moved.keys), name=moved.name, dest=dest),
                 Moved(file=dest, keys=None, name=moved.name, dest=dest))
    before = _Side(project, final, sides[0])
    with tempfile.TemporaryDirectory(prefix="la-verify-") as directory:
        root = Path(directory).resolve()
        _copy(project, root)
        apply(root, writes, moves)
        after = MoveProject(root)
        _share(project, after, {write.rel for write in writes}, final)
        found = _compare(before, _Side(after, moved=sides[1]), _Expected(before, symbol))
    if found is not None:
        path, line, name = found
        raise RefactorError(message("refactor.resolution-changed", path=path, line=line, name=name))
