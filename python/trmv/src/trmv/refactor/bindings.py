"""A rename's names re-resolved over its edits: the declarations each identifier of a renamed or new name means
before and after, by Python's own scoping, with star imports and forward-reference strings."""

from __future__ import annotations

import ast
import bisect
import builtins
import re
from collections import defaultdict
from collections.abc import Callable, Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from deterministic_refactor.refactor.locators import cannot_rename
from deterministic_refactor.refactor.move_edits import NameConflict
from deterministic_refactor.refactor.python_source import SourceFile, nfkc
from deterministic_refactor.refactor.static_resolver import Module, Scope
from deterministic_refactor.refactor.text_edits import TextEdit, apply_edits, merge_edits

# A declaration or an occurrence: a project-relative path and a character offset in the code before the rename.
Site = tuple[str, int]
# A character range of a source.
Span = tuple[int, int]
# The declarations a name means, each with the site a finding names for it (a star import's, for its names).
Meaning = dict[Site, Site]

_BUILTINS = frozenset(dir(builtins))
_PREFIX = re.compile(r"[rRuU]?('''|\"\"\"|'|\")")
_STAR = re.compile(r"(?<!\w)import[\s\\]*\*")


def may_name(pattern: re.Pattern[str], text: str) -> bool:
    """`text` may spell a name `pattern` matches: it does, or it holds a non-ASCII character NFKC may fold onto one."""
    return not text.isascii() or pattern.search(text) is not None


def _builtin(name: str) -> Site:
    return (f"<builtins>.{name}", -1)


def _word(source: SourceFile, node: ast.AST, word: str) -> int | None:
    """The offset of the first whole identifier in `node`'s span that spells `word`."""
    start = source.offset(getattr(node, "lineno", 1), getattr(node, "col_offset", 0))
    end = source.offset(getattr(node, "end_lineno", None) or 1, getattr(node, "end_col_offset", None) or 0)
    found = source.word(start, end, word)
    return None if found is None else found[0]


def bound_at(source: SourceFile, node: ast.AST, name: str) -> int | None:
    """The offset of the identifier with which `node` binds `name`."""
    span = source.name_span(node)
    return span[0] if span is not None else _word(source, node, name)


def _is_literal(expr: ast.expr) -> bool:
    return (isinstance(expr, ast.Name) and expr.id == "Literal") or (isinstance(expr, ast.Attribute) and expr.attr == "Literal")


def _forward_reference(source: SourceFile, node: ast.Constant) -> tuple[SourceFile, int] | None:
    """A string annotation as a source of its own, with its offset in `source`; None for any string whose text is not
    exactly its value."""
    start, end = source.span(node)
    text = source.text[start:end]
    match = _PREFIX.match(text)
    if match is None or not text.endswith(match.group(1)):
        return None
    inner = text[match.end() : len(text) - len(match.group(1))]
    if inner != node.value:
        return None
    parsed = SourceFile(Path(), inner.strip())
    return (parsed, start + match.end() + len(inner) - len(inner.lstrip())) if parsed.tree is not None else None


def _annotation_names(source: SourceFile, expr: ast.AST, base: int = 0) -> Iterator[tuple[str, int]]:
    """Each name an annotation reads, string annotations included and `Literal` values left out."""
    if isinstance(expr, ast.Name):
        yield expr.id, base + source.span(expr)[0]
    elif isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        found = _forward_reference(source, expr)
        if found is not None and found[0].tree is not None:
            for stmt in found[0].tree.body:
                yield from _annotation_names(found[0], stmt, base + found[1])
    elif isinstance(expr, ast.Subscript) and _is_literal(expr.value):
        yield from _annotation_names(source, expr.value, base)
    else:
        for child in ast.iter_child_nodes(expr):
            yield from _annotation_names(source, child, base)


class Occurrence:
    """An identifier of a checked name: its offset, the scope it is resolved in and whether it binds."""

    __slots__ = ("binds", "name", "offset", "scope")

    def __init__(self, name: str, offset: int, scope: Scope, *, binds: bool) -> None:
        self.name, self.offset, self.scope, self.binds = name, offset, scope, binds

    @property
    def read_at(self) -> int | None:
        """The offset a read resolves at; None for a binding."""
        return None if self.binds else self.offset


class _Parsed:
    """A module's scopes, the offsets binding each name in the scope it binds in, its star imports and the
    identifiers of each name; it keeps no syntax tree."""

    def __init__(self, source: SourceFile, tree: ast.Module, parts: list[str], is_package: bool) -> None:
        module = Module(tree, parts, is_package)
        binder = module.binder
        self.scope = module.scope
        self.all_names = module.all_names
        self.sites: defaultdict[tuple[Scope, str], list[int]] = defaultdict(list)
        # Each binding that runs: its name's offset, the offset it runs at and the span its statement evaluates first.
        self.points: defaultdict[tuple[Scope, str], list[tuple[int | None, int, Span | None]]] = defaultdict(list)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        self._named: defaultdict[str, list[Occurrence]] = defaultdict(list)
        for scope, name, node in binder.bound:
            offset = bound_at(source, node, name)
            parent = parents.get(node)
            if not (isinstance(parent, ast.AnnAssign) and parent.value is None):  # an annotation binds nothing
                self.points[(scope.owner(name), name)].append((offset, *_binding_point(source, node, parents)))
            if offset is not None:
                self.sites[(scope.owner(name), name)].append(offset)
                self._named[name].append(Occurrence(name=name, offset=offset, scope=scope, binds=True))
                if isinstance(parent, ast.AugAssign):  # `x += 1` reads `x` before binding it
                    self._named[name].append(Occurrence(name=name, offset=offset, scope=scope, binds=False))
        for node, scope in binder.loads:
            if isinstance(node, ast.Name):
                self._named[node.id].append(Occurrence(name=node.id, offset=source.span(node)[0], scope=scope, binds=False))
        for expr, scope in binder.annotations:
            for n, o in _annotation_names(source, expr):
                self._named[n].append(Occurrence(name=n, offset=o, scope=scope, binds=False))
        self.stars = [(dotted, source.span(node)[0]) for dotted, node in zip(binder.stars, binder.star_nodes, strict=True)]
        self.scopes = binder.scopes
        self.loops = {scope: [_repeated(source, n) for n in _loops(node.body)] for scope, node in binder.class_nodes.items()}

    def may_precede(self, scope: Scope, name: str, at: int) -> bool:
        """A binding of `name` in class `scope` may run before the read at `at`: it is earlier, or in the repeated
        part of a loop holding the read."""
        points = self.points.get((scope, name), [])
        binds = [b for b, _, _ in points if b is not None]
        looped = any(_inside(spans, at) and any(_inside(spans, b) for b in binds) for spans in self.loops.get(scope, []))
        return looped or any(point <= at and not (first and _inside([first], at)) for _, point, first in points)

    def occurrences(self, names: frozenset[str]) -> list[Occurrence]:
        """The identifiers spelled with one of `names`."""
        return [o for name in names for o in self._named.get(name, [])]

    def joined(self, scope: Scope) -> list[Scope]:
        """The scopes a declaration in `scope` shares its scope with: a generic def's or class's own scope and the
        scope of its type parameters."""
        if scope.kind == "annotation":
            return [s for s in self.scopes if s.parent is scope and s.kind in ("function", "class")]
        parent = scope.parent
        return [parent] if parent is not None and parent.kind == "annotation" and scope.kind in ("function", "class") else []


def _loops(body: list[ast.stmt]) -> Iterator[ast.For | ast.AsyncFor | ast.While]:
    """The loop statements of a class body, outside its nested functions and classes."""
    for stmt in body:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if isinstance(stmt, ast.For | ast.AsyncFor | ast.While):
            yield stmt
        for child in ast.iter_child_nodes(stmt):
            if isinstance(child, ast.stmt):
                yield from _loops([child])
            elif isinstance(child, ast.ExceptHandler | ast.match_case):
                yield from _loops(child.body)


def _binding_point(source: SourceFile, node: ast.AST, parents: dict[ast.AST, ast.AST]) -> tuple[int, Span | None]:
    """When a binding has run: the offset it runs at (a target at its own end, targets binding left to right), and
    the span its statement evaluates before any target (reads there never see it)."""
    if isinstance(node, ast.stmt):
        return source.span(node)[1], None
    if isinstance(node, ast.ExceptHandler):
        return source.span(node.body[0])[0], None
    own = source.span(node)[1] if isinstance(node, ast.expr) else None
    current = parents.get(node)
    while current is not None:
        found = _point_at(source, current, own)
        if found is not None:
            return found
        current = parents.get(current)
    return 0, None


def _point_at(source: SourceFile, node: ast.AST, own: int | None) -> tuple[int, Span | None] | None:
    """The binding point an enclosing `node` sets for a binding ending at `own` (None: not an expression)."""
    first = _evaluated_first(node)
    if first is not None:
        return source.span(first)[1] if own is None else own, source.span(first)
    if isinstance(node, ast.match_case):
        # A capture binds as its pattern matches, before the guard.
        return source.offset(node.pattern.end_lineno or node.pattern.lineno, node.pattern.end_col_offset or 0), None
    if isinstance(node, ast.stmt):
        return source.span(node)[1] if own is None else own, None
    return None


def _evaluated_first(node: ast.AST) -> ast.expr | None:
    """What a binding construct evaluates before it binds its targets."""
    if isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign | ast.NamedExpr):
        return node.value
    if isinstance(node, ast.For | ast.AsyncFor):
        return node.iter
    return node.context_expr if isinstance(node, ast.withitem) else None


def _inside(spans: list[Span], offset: int) -> bool:
    return any(start <= offset < end for start, end in spans)


def _repeated(source: SourceFile, loop: ast.For | ast.AsyncFor | ast.While) -> list[tuple[int, int]]:
    """The spans of a loop's repeated part: a `while` statement's condition and body, a `for` statement's target and
    body."""
    head = loop.test if isinstance(loop, ast.While) else loop.target
    return [source.span(head), (source.span(loop.body[0])[0], source.span(loop.body[-1])[1])]


def module_binding(text: str, name: str) -> int | None:
    """The offset of the first module-level binding of `name` in a module's `text`."""
    source = SourceFile(Path(), text)
    if source.tree is None:
        return None
    parsed = _Parsed(source, source.tree, [], False)
    sites = parsed.sites.get((parsed.scope, nfkc(name)))
    return min(sites) if sites else None


def bindings_after(text: str, edits: list[TextEdit], name: str) -> list[int]:
    """The module-level bindings of `name` in a module's `text` after `edits`, by their offsets before them."""
    source = SourceFile(Path(), apply_edits(text, edits))
    if source.tree is None:
        return []
    parsed = _Parsed(source, source.tree, [], False)
    edited = _Edited(edits)
    return sorted(edited.original(offset) for offset in parsed.sites.get((parsed.scope, nfkc(name)), []))


def _module_parts(folders: list[str], rel: str) -> tuple[list[str], bool]:
    """The module path of file `rel` under its source folder, and whether it is a package."""
    folder = max((f for f in folders if not f or rel.startswith(f + "/")), key=len)
    parts = rel[len(folder) + 1 if folder else 0 :].rsplit(".", 1)[0].split("/")
    return (parts[:-1], True) if parts[-1] == "__init__" else (parts, False)


class World:
    """The project's Python modules as one state of the code: `analyse` reads and analyses a module, `origin` maps its
    offsets to sites of the code before the rename; a module outside `edited` is `unchanged`'s."""

    def __init__(self, files: set[str], folders: list[str], analyse: Callable[[str], _Parsed | None],
                 origin: Callable[[str, int], Site], *, unchanged: World | None = None,
                 edited: frozenset[str] = frozenset()) -> None:
        self.files = files
        self.folders = folders
        self.analyse = analyse
        self.origin = origin
        self.unchanged = unchanged
        self.edited = edited
        self._parsed: dict[str, _Parsed | None] = {}

    def find(self, dotted: str | None) -> str | None:
        """The file of module `dotted` in this state, if it is a project module."""
        if dotted is None:
            return None
        path = dotted.replace(".", "/")
        for folder in self.folders:
            base = f"{folder}/{path}" if folder else path
            for rel in (f"{base}/__init__.py", f"{base}.py"):
                if rel in self.files:
                    return rel
        return None

    def parsed(self, rel: str) -> _Parsed | None:
        """`rel` analysed; None when it does not parse (`refactor.cannot-rename` for an edited state)."""
        if self.unchanged is not None and rel not in self.edited:
            return self.unchanged.parsed(rel)
        if rel not in self._parsed:
            self._parsed[rel] = self.analyse(rel)
        return self._parsed[rel]

    def _module_meaning(self, rel: str, name: str, seen: frozenset[str]) -> Meaning:
        parsed = self.parsed(rel)
        if parsed is None:
            return {}
        out: Meaning = {}
        for offset in parsed.sites.get((parsed.scope, name), []):
            site = self.origin(rel, offset)
            out[site] = site
        for dotted, offset in parsed.stars:
            source = self.find(dotted)
            if source is None or source in seen or not self._exports(source, name):
                continue
            star = self.origin(rel, offset)
            out |= dict.fromkeys(self._module_meaning(source, name, seen | {rel}), star)
        return out

    def _exports(self, rel: str, name: str) -> bool:
        parsed = self.parsed(rel)
        if parsed is None:
            return False
        listed = parsed.all_names
        return name in listed if listed is not None else not name.startswith("_")

    def meaning(self, rel: str, scope: Scope, name: str, at: int | None = None) -> Meaning:
        """The declarations `name` means in `scope` of module `rel`, read at offset `at` (None for a binding)."""
        owner = scope.resolving(name)
        if owner.kind == "module":
            return self._global(rel, name)
        parsed = self.parsed(rel)
        assert parsed is not None
        local: Meaning = {(site := self.origin(rel, o)): site for o in parsed.sites.get((owner, name), [])}
        if owner.kind != "class" or at is None:
            return local
        # A class body reads its own binding only once one may have run; else the global, as `LOAD_NAME` does.
        return local | self._global(rel, name) if parsed.may_precede(owner, name, at) else self._global(rel, name)

    def _global(self, rel: str, name: str) -> Meaning:
        found = self._module_meaning(rel, name, frozenset())
        return found or ({_builtin(name): _builtin(name)} if name in _BUILTINS else {})


class _Edited:
    """One file's edits: maps an offset of its edited text to the code before them."""

    def __init__(self, edits: list[TextEdit]) -> None:
        self.edits = sorted(edits, key=lambda e: e.start)
        self.starts: list[int] = []
        delta = 0
        for e in self.edits:
            self.starts.append(e.start + delta)
            delta += len(e.new_text) - (e.end - e.start)

    def original(self, offset: int) -> int:
        i = bisect.bisect_right(self.starts, offset) - 1
        if i < 0:
            return offset
        e, start = self.edits[i], self.starts[i]
        if offset < start + len(e.new_text):
            return e.start + min(offset - start, e.end - e.start)
        return offset - (start - e.start) - (len(e.new_text) - (e.end - e.start))


class EntryEdits(BaseModel):
    """A map entry's edits: those it writes, those `--keep` drops, its new name and, for a retarget, the name its
    rewritten references must mean and the imports of it that it adds."""

    index: int
    new_name: str
    edits: list[TextEdit]
    kept: list[TextEdit] = []
    target: str | None = None
    binds: list[TextEdit] = []


class Conflict(BaseModel):
    """A site a name-conflict finding may name, with the new name it names and the map index of its entry."""

    model_config = ConfigDict(frozen=True)

    site: Site
    name: str
    entry: int


def first_conflicts(conflicts: list[Conflict], source: Callable[[str], SourceFile]) -> dict[int, NameConflict]:
    """Each entry's finding, by entry index: the first of its `conflicts` by path, then offset in the code before
    the rename."""
    first: dict[int, Conflict] = {}
    for c in conflicts:
        if c.entry not in first or c.site < first[c.entry].site:
            first[c.entry] = c
    return {entry: NameConflict(c.name, c.site[0], source(c.site[0]).line(c.site[1])) for entry, c in sorted(first.items())}


class BindingCheck:
    """Re-resolves every identifier of the renamed and new names before and after the edits, in the files whose edits
    can change a name's meaning and their star importers (every file when files move)."""

    def __init__(self, files: list[str], folders: list[str], source: Callable[[str], SourceFile]) -> None:
        self.files = files
        self.folders = folders
        self.source = source
        self.world = World(set(files), folders, self._analyse_before, lambda rel, o: (rel, o))
        self._inert: dict[str, frozenset[Span]] = {}
        self._after: dict[tuple[str, str, tuple[TextEdit, ...]], tuple[_Parsed | None, _Edited]] = {}
        self._importers: dict[str, list[str]] | None = None

    def before(self, rel: str) -> str:
        return self.source(rel).text

    def _analyse_before(self, rel: str) -> _Parsed | None:
        try:
            source = self.source(rel)
        except (OSError, UnicodeDecodeError, LookupError):
            return None
        parts, is_package = _module_parts(self.folders, rel)
        return None if source.tree is None else _Parsed(source, source.tree, parts, is_package)

    def _state(self, rel: str, src: str, edits: tuple[TextEdit, ...]) -> tuple[_Parsed | None, _Edited]:
        """Module `rel` (file `src` before the edits) analysed after `edits`, with its offset mapping; cached by them."""
        key = (rel, src, edits)
        if key not in self._after:
            try:
                source = SourceFile(Path(rel), apply_edits(self.before(src), list(edits)))
            except (OSError, UnicodeDecodeError, LookupError):
                self._after[key] = (None, _Edited(list(edits)))
                return self._after[key]
            if source.tree is None:
                raise cannot_rename()
            parts, is_package = _module_parts(self.folders, rel)
            self._after[key] = (_Parsed(source, source.tree, parts, is_package), _Edited(list(edits)))
        return self._after[key]

    def _inert_spans(self, rel: str) -> frozenset[Span]:
        """The attribute names and call keyword names of `rel`: an edit of one binds nothing."""
        if rel not in self._inert:
            source = self.source(rel)
            nodes: list[ast.AST] = [*source.of_type(ast.Attribute),
                                    *(k for call in source.of_type(ast.Call) for k in call.keywords)]
            self._inert[rel] = frozenset(span for n in nodes if (span := source.name_span(n)) is not None)
        return self._inert[rel]

    def _stars(self, rel: str) -> list[str]:
        """The project modules `rel` star-imports."""
        parsed = self.world.parsed(rel) if may_name(_STAR, self.before(rel)) else None
        found = (self.world.find(dotted) for dotted, _ in parsed.stars) if parsed is not None else ()
        return [module for module in found if module is not None]

    def _star_importers(self) -> dict[str, list[str]]:
        """Each project module's star importers."""
        if self._importers is None:
            out: defaultdict[str, list[str]] = defaultdict(list)
            for rel in self.files:
                for module in self._stars(rel):
                    out[module].append(rel)
            self._importers = dict(out)
        return self._importers

    def _judged(self, edited: set[str]) -> set[str]:
        """`edited` and every module star-importing one of them, transitively."""
        out, todo = set(edited), list(edited)
        while todo:
            for importer in self._star_importers().get(todo.pop(), []):
                if importer not in out:
                    out.add(importer)
                    todo.append(importer)
        return out

    def _names(self, entries: list[EntryEdits]) -> frozenset[str]:
        out: set[str] = set()
        for entry in entries:
            for e in (*entry.edits, *entry.kept):
                out |= {nfkc(t) for t in (self.before(e.path)[e.start : e.end], e.new_text) if t.isidentifier()}
            if entry.target is not None:
                out.add(nfkc(entry.target))
        return frozenset(out)

    def _plan(self, entries: list[EntryEdits], moves: dict[str, str]) -> _Plan | None:
        """What a pass of `entries` judges; None when they check no name."""
        names = self._names(entries)
        if not names:
            return None
        by_file: defaultdict[str, list[TextEdit]] = defaultdict(list)
        for e in merge_edits([e for entry in entries for e in entry.edits]):
            by_file[e.path].append(e)
        binding = {rel: tuple(edits) if moves else tuple(e for e in edits if (e.start, e.end) not in self._inert_spans(rel))
                   for rel, edits in by_file.items()}
        return _Plan(entries, names, dict(by_file), {rel: edits for rel, edits in binding.items() if edits}, moves)

    def conflicts(self, passes: list[list[EntryEdits]], moves: dict[str, str] | None = None, *,
                  each: list[dict[str, str]] | None = None) -> Iterator[list[Conflict]]:
        """Each pass's sites whose meaning its edits change, in order; `moves` maps a moved file to its path after the
        rename, `each` gives every pass its own. An after-edit state lives until the last pass reading it."""
        own = each if each is not None else [moves or {}] * len(passes)
        plans = [self._plan(entries, pass_moves) for entries, pass_moves in zip(passes, own, strict=True)]
        last = {key: n for n, plan in enumerate(plans) if plan is not None for key in plan.states()}
        for n, plan in enumerate(plans):
            found = [] if plan is None else self._judge(plan)
            for key in [k for k in self._after if last.get(k, -1) <= n]:
                del self._after[key]
            yield found

    def _judge(self, plan: _Plan) -> list[Conflict]:
        def state(rel: str) -> tuple[_Parsed | None, _Edited]:
            return self._state(*plan.key(rel))

        def after_origin(rel: str, offset: int) -> Site:
            src = plan.back.get(rel, rel)
            return src, state(rel)[1].original(offset) if src in plan.binding else offset

        moves = plan.moves
        after = World({moves.get(f, f) for f in self.files}, self.folders, lambda rel: state(rel)[0], after_origin,
                      unchanged=self.world, edited=plan.changed)
        judged = set(self.files) if moves else self._judged(set(plan.binding))
        checked = [rel for rel in self.files
                   if rel in judged and (rel in plan.by_file or may_name(plan.pattern, self.before(rel)))]
        return _Judge(plan.entries, plan.names, self.world, after, moves).conflicts(checked)


class _Plan:
    """A pass: its entries and names, its edits by file, those that can bind a name and its after-world's edited
    modules."""

    def __init__(self, entries: list[EntryEdits], names: frozenset[str], by_file: dict[str, list[TextEdit]],
                 binding: dict[str, tuple[TextEdit, ...]], moves: dict[str, str]) -> None:
        self.entries, self.names, self.by_file, self.binding, self.moves = entries, names, by_file, binding, moves
        self.pattern = re.compile(rf"(?<!\w)(?:{'|'.join(map(re.escape, sorted(names)))})(?!\w)")
        self.back = {dest: src for src, dest in moves.items()}
        self.changed = frozenset({moves.get(rel, rel) for rel in binding} | set(moves.values()))

    def key(self, rel: str) -> tuple[str, str, tuple[TextEdit, ...]]:
        """The after-edit state of module `rel`: its path, its file before the edits and that file's binding edits."""
        src = self.back.get(rel, rel)
        return rel, src, self.binding.get(src, ())

    def states(self) -> set[tuple[str, str, tuple[TextEdit, ...]]]:
        """The after-edit states the pass reads."""
        return {self.key(rel) for rel in self.changed}


def _conflict(site: Site, entry: EntryEdits) -> Conflict:
    return Conflict(site=site, name=entry.new_name, entry=entry.index)


class _Judge:
    """Compares each occurrence's meanings before and after; collects the sites a finding may name."""

    def __init__(self, entries: list[EntryEdits], names: frozenset[str], before: World, after: World,
                 moves: dict[str, str]) -> None:
        self.names = names
        self.moves = moves
        self.entries = sorted(entries, key=lambda e: e.index)
        self.before = before
        self.after = after
        self.rewritten: dict[Site, EntryEdits] = {}
        self.kept: dict[Site, EntryEdits] = {}
        for entry in self.entries:
            self.rewritten |= {(e.path, e.start): entry for e in entry.edits}
            self.kept |= {(e.path, e.start): entry for e in entry.kept}
        self.declared: dict[Site, EntryEdits] = {}
        self.retargeted: dict[Site, Meaning] = {}
        self.added = [e for entry in self.entries for e in entry.binds if e.new_text]

    def _pairs(self, rel: str) -> list[tuple[str, Occurrence, Occurrence]]:
        """Each occurrence of `rel` before the edits with the one at its site after them."""
        old = self.before.parsed(rel)
        new = self.after.parsed(self._moved(rel))
        if old is None or new is None:
            return []
        at = {(o.offset, o.binds): o for o in old.occurrences(self.names)}
        out: list[tuple[str, Occurrence, Occurrence]] = []
        for occ in new.occurrences(self.names):
            site = self.after.origin(self._moved(rel), occ.offset)
            if site[0] == rel and (site[1], occ.binds) in at:
                out.append((rel, at[(site[1], occ.binds)], occ))
        return out

    def conflicts(self, files: list[str]) -> list[Conflict]:
        pairs = [pair for rel in files for pair in self._pairs(rel)]
        for rel, old_occ, _ in pairs:
            entry = self.rewritten.get((rel, old_occ.offset))
            if old_occ.binds and entry is not None:
                self.declared.setdefault((rel, old_occ.offset), entry)
                if entry.target is not None:
                    self.retargeted[(rel, old_occ.offset)] = self.before.meaning(rel, old_occ.scope, entry.target)
        return [c for rel, old_occ, new_occ in pairs for c in self._verdict(rel, old_occ, new_occ)]

    def _first_declaration(self, entry: EntryEdits) -> Site:
        own = [site for site, e in self.declared.items() if e is entry]
        return min(own) if own else min((e.path, e.start) for e in entry.edits)

    def _naming(self, name: str) -> EntryEdits:
        """The entry a finding about an existing occurrence of `name` belongs to: the first whose new name it is."""
        return next((entry for entry in self.entries if nfkc(entry.new_name) == name), self.entries[0])

    def _verdict(self, rel: str, old: Occurrence, new: Occurrence) -> list[Conflict]:
        site = (rel, old.offset)
        before = self.before.meaning(rel, old.scope, old.name, old.read_at)
        meaning = self.after.meaning(self._moved(rel), new.scope, new.name, new.read_at)
        after = self._through_retargets(meaning, new.name, rel, new.scope)
        entry = self.rewritten.get(site)
        if entry is not None:
            return self._rewritten_verdict(rel, old, new, entry, before, after)
        kept = self.kept.get(site)
        if kept is not None:
            # A declaration another entry renames onto the kept name is that entry's finding.
            after = {d: s for d, s in after.items() if self.declared.get(d, kept) is kept}
            if not after or after.keys() == before.keys():
                return []
            reported = [s for s in after.values() if s[1] >= 0]
            return [_conflict(s, kept) for s in reported or [site]]
        if after.keys() == before.keys():
            return []
        return [_conflict(site, self._naming(new.name))]

    def _rewritten_verdict(self, rel: str, old: Occurrence, new: Occurrence, entry: EntryEdits, before: Meaning,
                           after: Meaning) -> list[Conflict]:
        expected = before if entry.target is None else self.before.meaning(rel, old.scope, entry.target, old.read_at)
        joined = self._joined(rel, new) if old.binds else []
        if joined:
            return [_conflict(s, entry) for s in joined]
        if after.keys() == expected.keys():
            return []
        return self._rewritten_conflicts((rel, old.offset), entry, after, expected)

    def _rewritten_conflicts(self, site: Site, entry: EntryEdits, after: Meaning, expected: Meaning) -> list[Conflict]:
        """A rewritten occurrence meaning other declarations than `expected`: an existing one's sites, else the first
        declaration of the earliest entry it meets (the latest one's finding), else its own site."""
        foreign = [s for s in after if s not in expected]
        existing = [after[s] for s in foreign if s not in self.declared and s[1] >= 0]
        if existing:
            return [_conflict(s, entry) for s in existing]
        met = [self.declared[s] for s in foreign if s in self.declared and self.declared[s] is not entry]
        if met:
            meeting = sorted([entry, *met], key=lambda e: e.index)
            return [_conflict(self._first_declaration(meeting[0]), meeting[-1])]
        return [_conflict(site, entry)]

    def _joined(self, rel: str, new: Occurrence) -> list[Site]:
        """The existing declarations of `new`'s name in the scopes its own declaration shares."""
        parsed = self.after.parsed(self._moved(rel))
        assert parsed is not None
        sites = [self.after.origin(self._moved(rel), o) for s in parsed.joined(new.scope)
                 for o in parsed.sites.get((s, new.name), [])]
        return [s for s in sites if s not in self.declared]

    def _through_retargets(self, meaning: Meaning, name: str, rel: str, scope: Scope) -> Meaning:
        """`meaning` of `name`, read in `scope` of `rel`, with each binding a retarget rewrote replaced by what its
        target meant there, and each it adds by what `name` meant before in the scope the import binds it in."""
        out: Meaning = {}
        for decl, shown in meaning.items():
            if self._added(decl):
                out |= self._added_meaning(decl[0], name, scope if decl[0] == rel else None)
            else:
                out |= self.retargeted.get(decl, {decl: shown})
        return out

    def _added_meaning(self, rel: str, name: str, scope: Scope | None) -> Meaning:
        """What `name` meant before the edits in the scope of `rel` that resolves it from `scope` (the module when
        None); the edits add or remove no scope, so a scope's place in its module's list matches it across them."""
        old, new = self.before.parsed(rel), self.after.parsed(self._moved(rel))
        if old is None:
            return {}
        owner = scope.resolving(name) if scope is not None else None
        index = next((i for i, s in enumerate(new.scopes) if s is owner), 0) if new is not None else 0
        return self.before.meaning(rel, old.scopes[index], name)

    def _added(self, site: Site) -> bool:
        """`site` is in the new text of an import a retarget adds, which maps into the span it replaces."""
        rel, offset = site
        return any(e.path == rel and e.start <= offset <= e.end for e in self.added)

    def _moved(self, rel: str) -> str:
        return self.moves.get(rel, rel)
