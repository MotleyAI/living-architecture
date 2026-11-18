"""A run's occurrence index: every occurrence of the old names in the candidate files and the position facts the rules
ask about, exported in one request by the run's one language server, or read from the cache, then looked up."""

from __future__ import annotations

import ast
import bisect
from collections.abc import Callable, Hashable, Iterable
from contextlib import ExitStack
from pathlib import Path
from typing import TypeVar, cast

from living_architecture.contract import language
from living_architecture.lang import (
    ExportRequest,
    FactQuery,
    LanguageServer,
    Occurrence,
    OccurrenceIndex,
    PositionFacts,
    Span,
)
from living_architecture.lang.language_server import FACT_KINDS, FactKind, Verdict
from living_architecture.refactor.index_cache import IndexCache, request_key
from living_architecture.refactor.python_source import SourceFile, nfkc
from living_architecture.refactor.timings import timed

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
READ_ATTRIBUTES = frozenset(read["attribute"] for read in language("python").get("name_reads", []))
_T = TypeVar("_T")


class ServerSession:
    """At most one language server per run, started at first need."""

    def __init__(self, root: Path, read: Callable[[Path], str]) -> None:
        self.root = root
        self.read = read
        self._stack = ExitStack()
        self._server: LanguageServer | None = None

    @property
    def started(self) -> bool:
        return self._server is not None

    def get(self) -> LanguageServer:
        if self._server is None:
            with timed("load"):
                self._server = self._stack.enter_context(LanguageServer(self.root, read=self.read))
        return self._server

    def close(self) -> None:
        """Stop the server; a failure it raised then holds its stderr and exit code."""
        self._stack.close()
        self._server = None


def _name_node(expr: ast.expr) -> ast.expr | None:
    if isinstance(expr, ast.Subscript):
        expr = expr.value
    return expr if isinstance(expr, (ast.Name, ast.Attribute)) else None


class _Shape:
    """One pass over a file: the nodes holding a string constant in `names`, and the names assigned a dict literal
    holding one."""

    def __init__(self, source: SourceFile, names: set[str]) -> None:
        self.source = source
        self.mentioning: set[int] = set()
        order = source.nodes
        for node in reversed(order):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in names) or any(
                id(c) in self.mentioning for c in ast.iter_child_nodes(node)
            ):
                self.mentioning.add(id(node))
        self.dicts = {
            t.id
            for n in order
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict) and id(n.value) in self.mentioning
            for t in n.targets
            if isinstance(t, ast.Name)
        }

    def candidate(self, value: ast.AST) -> bool:
        """`value` may carry a name: a literal holding one, or a name bound to such a dict."""
        return id(value) in self.mentioning or (isinstance(value, ast.Name) and value.id in self.dicts)

    def function_of(self, node: ast.AST) -> ast.AST | None:
        """The function whose own body holds `node`, nested functions, lambdas and classes stopping the search."""
        up = self.source.parent(node)
        while up is not None and not isinstance(up, (*_FUNCTIONS, ast.Lambda, ast.ClassDef)):
            up = self.source.parent(up)
        return up if isinstance(up, _FUNCTIONS) else None


def _plain(node: ast.expr) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class _Queries:
    """The positions of one file to ask about, each with its kinds."""

    def __init__(self, source: SourceFile) -> None:
        self.source = source
        self.kinds: dict[int, set[FactKind]] = {}

    def ask(self, node: ast.AST | None, *kinds: FactKind) -> None:
        span = self.source.name_span(node) if node is not None else None
        if span is not None:
            self.kinds.setdefault(span[0], set()).update(kinds)

    def names(self, expr: ast.AST | None) -> None:
        for node in ast.walk(expr) if expr is not None else ():
            if isinstance(node, (ast.Name, ast.Attribute)):
                self.ask(node, "definition")

    def queries(self) -> list[FactQuery]:
        return [FactQuery(path=self.source.path, offset=offset, kinds=tuple(k for k in FACT_KINDS if k in kinds))
                for offset, kinds in sorted(self.kinds.items())]


def class_queries(source: SourceFile) -> list[FactQuery]:
    """The class facts of every class `source` declares."""
    found = _Queries(source)
    for node in source.of_type(ast.ClassDef):
        found.ask(node, "class")
    return found.queries()


def fact_queries(source: SourceFile, names: set[str]) -> list[FactQuery]:
    """The positions of `source` the rules of a rename of `names` ask about: each class, its bases and field
    annotations, decorators, the callees, receivers and annotations of keyed sinks, and string-member callees and
    objects, and the signature of each call with a keyword or an unpacked constant key in `names`."""
    if source.tree is None:
        return []
    found = _Queries(source)
    shape = _Shape(source, names)
    returning = _returning(source, shape)
    for node in source.nodes:
        if isinstance(node, ast.ClassDef):
            _class_queries(found, node)
        elif isinstance(node, _FUNCTIONS):
            _function_queries(found, node, id(node) in returning, names)
        elif isinstance(node, ast.AnnAssign) and node.value is not None and shape.candidate(node.value):
            found.names(node.annotation)
        elif isinstance(node, ast.Call):
            _call_queries(found, node, names, shape)
        elif isinstance(node, ast.Attribute) and node.attr in READ_ATTRIBUTES:
            found.ask(node, "definition")
            found.ask(node.value if isinstance(node.value, (ast.Name, ast.Attribute)) else None, "verdict")
    return found.queries()


def _returning(source: SourceFile, shape: _Shape) -> set[int]:
    """The ids of the functions returning a keyed candidate."""
    out: set[int] = set()
    for node in source.of_type(ast.Return):
        fn = shape.function_of(node) if node.value is not None and shape.candidate(node.value) else None
        if fn is not None:
            out.add(id(fn))
    return out


def _class_queries(found: _Queries, cls: ast.ClassDef) -> None:
    found.ask(cls, "class")
    for base in cls.bases:
        found.ask(_name_node(base), "definition")
    for stmt in cls.body:
        if isinstance(stmt, ast.AnnAssign):
            found.names(stmt.annotation)


def _function_queries(found: _Queries, fn: ast.FunctionDef | ast.AsyncFunctionDef, returning: bool, names: set[str]) -> None:
    for decorator in fn.decorator_list:
        named = isinstance(decorator, ast.Call) and any(_plain(a) in names for a in decorator.args)
        callee = decorator.func if isinstance(decorator, ast.Call) and named else decorator
        found.ask(callee if isinstance(callee, (ast.Name, ast.Attribute)) else None, "definition")
    if returning:
        found.names(fn.returns)


def _signature_queries(found: _Queries, call: ast.Call, names: set[str]) -> None:
    for k in call.keywords:
        if k.arg in names:
            found.ask(k, "signature")
        elif k.arg is None and isinstance(k.value, ast.Dict) and any(_plain(key) in names for key in k.value.keys if key):
            found.ask(call.func if isinstance(call.func, (ast.Name, ast.Attribute)) else None, "signature")


def _call_queries(found: _Queries, call: ast.Call, names: set[str], shape: _Shape) -> None:
    arguments = [*call.args, *(k.value for k in call.keywords)]
    keyed = any(k.arg in names for k in call.keywords) or any(shape.candidate(a) for a in arguments)
    if keyed and isinstance(call.func, (ast.Name, ast.Attribute)):
        found.ask(call.func, "definition", "typeDefinition")
        if isinstance(call.func, ast.Attribute):
            found.ask(_name_node(call.func.value), "definition", "typeDefinition")
    _signature_queries(found, call, names)
    strings = [s for a in call.args if (s := _plain(a)) is not None]
    if any(s in names or names & set(s.split(".")) for s in strings):
        found.ask(call.func, "definition")
        for a in call.args:
            if isinstance(a, (ast.Name, ast.Attribute)):
                found.ask(a, "verdict")


def carrier_queries(source: SourceFile) -> list[FactQuery]:
    """The callees and receivers of every call in a `def` of `source` with a `**kwargs` parameter."""
    found = _Queries(source)
    for fn in (n for n in source.nodes if isinstance(n, _FUNCTIONS) and n.args.kwarg is not None):
        for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
            func = call.func
            found.ask(func if isinstance(func, (ast.Name, ast.Attribute)) else None, "definition", "typeDefinition", "signature")
            if isinstance(func, ast.Attribute):
                receiver = func.value.func if isinstance(func.value, ast.Call) else func.value
                found.ask(_name_node(receiver), "definition", "typeDefinition")
    return found.queries()


def _escaped_constant(source: SourceFile, names: set[str]) -> bool:
    return source.tree is not None and any(
        isinstance(n, ast.Constant) and n.value in names for n in source.nodes
    )


def candidate_files(rels: Iterable[str], text: Callable[[str], str], source: Callable[[str], SourceFile],
                    names: set[str]) -> list[str]:
    """The files whose text holds one of `names`, or a string constant equal to one under an escaped spelling."""
    out: list[str] = []
    for rel in rels:
        try:
            found = text(rel)
        except (OSError, UnicodeDecodeError, LookupError):
            continue
        if any(name in found for name in names) or ("\\" in found and _escaped_constant(source(rel), names)):
            out.append(rel)
    return out


class RunIndex:
    """The run's index over the project at `root`: exports answered by the cache or the run's language server."""

    def __init__(self, root: Path, source: Callable[[Path], SourceFile | None], server: ServerSession,
                 cache: IndexCache | None) -> None:
        self.root = root
        self._source = source
        self.server = server
        self.cache = cache
        self._opened: set[Path] = set()
        self._occurrences: dict[tuple[Path, str], list[Occurrence]] = {}
        self._starts: dict[tuple[Path, str], list[int]] = {}
        self._facts: dict[tuple[Path, int], dict[FactKind, PositionFacts]] = {}
        self._probes: dict[tuple[Path, int], PositionFacts] = {}
        self._probe_results: dict[tuple[Path, tuple[int, int]], tuple[Verdict | None, list[Span]]] = {}
        self._renamed_signatures: dict[tuple[Path, int], tuple[tuple[str, ...], ...]] = {}
        self._parameter_renames: frozenset[tuple[str, str]] = frozenset()
        self._renamed_texts: dict[Path, str] = {}
        self._shifts: dict[Path, list[tuple[int, int]]] = {}
        self.request = ExportRequest(names=[], files=[])
        self._memo: dict[Hashable, object] = {}

    # ---- exports

    def prepare(self, names: set[str], files: list[Path], members: Iterable[str] = (), classes: Iterable[Path] = ()) -> bool:
        """Fix the run's request for `names` over `files`, with the class facts of `classes` looking up `members`;
        whether its export is cached."""
        queries = [q for path in files if (source := self._source(path)) is not None for q in fact_queries(source, names)]
        asked = {(q.path, q.offset) for q in queries}
        queries += [q for path in classes if path not in files and (source := self._source(path)) is not None
                    for q in class_queries(source) if (q.path, q.offset) not in asked]
        self.request = ExportRequest(names=sorted(names), files=files, facts=queries, members=sorted({nfkc(m) for m in members}))
        return self.cache is not None and self.cache.get(request_key(self.request, {})) is not None

    def build(self) -> None:
        """Export the prepared request, or read it from the cache."""
        self._merge(self._export(self.request))

    def _open(self, paths: Iterable[Path], texts: dict[Path, str]) -> LanguageServer:
        server = self.server.get()
        for path in paths:
            if path in texts:
                server.open(path, texts[path])
            elif path not in self._opened and (source := self._source(path)) is not None:
                server.open(path, source.text)
            self._opened.add(path)
        return server

    def opened(self, paths: Iterable[Path]) -> LanguageServer:
        """The run's language server with `paths` opened as the snapshot holds them."""
        return self._open(paths, {})

    def _export(self, request: ExportRequest, texts: dict[Path, str] | None = None) -> OccurrenceIndex:
        texts = texts or {}
        key = request_key(request, texts)
        found = self.cache.get(key) if self.cache is not None else None
        if found is not None:
            return found
        server = self._open(dict.fromkeys([*request.files, *(q.path for q in request.facts), *texts]), texts)
        try:
            with timed("references"):
                found = server.export(request)
        finally:
            for path in texts:
                source = self._source(path)
                if source is not None:
                    server.change(path, source.text)
        if self.cache is not None:
            self.cache.put(key, found)
        return found

    def _merge(self, index: OccurrenceIndex) -> None:
        for o in index.occurrences:
            self._occurrences.setdefault((o.span.path, o.name), []).append(o)
        for key, found in self._occurrences.items():
            found.sort(key=lambda o: o.span.start)
            self._starts[key] = [o.span.start for o in found]
        for facts in [*index.answers, *index.followed]:
            entry = self._facts.setdefault((facts.path, facts.offset), {})
            for kind in facts.kinds:
                entry.setdefault(kind, facts)

    def close(self) -> None:
        if self.cache is not None:
            self.cache.save()

    def class_fact_source(self) -> ClassFactSource:
        """The class facts merged so far, holding nothing else of the index."""
        facts = {key: entry["class"] for key, entry in self._facts.items() if "class" in entry}
        return ClassFactSource(facts, list(self.request.members), self._source, self.server)

    # ---- lookups

    def memo(self, key: Hashable, compute: Callable[[], _T]) -> _T:
        """`compute()`, run once per run for `key`: a rule's per-file result that no entry changes."""
        if key not in self._memo:
            self._memo[key] = compute()
        return cast("_T", self._memo[key])

    def occurrences(self, path: Path, name: str) -> list[Occurrence]:
        """The occurrences of `name` in the file at `path`, in source order."""
        return self._occurrences.get((path, name), [])

    def at(self, path: Path, name: str, offset: int) -> Occurrence | None:
        """The occurrence of `name` whose span holds `offset`."""
        found = self._occurrences.get((path, name), [])
        i = bisect.bisect_right(self._starts.get((path, name), []), offset) - 1
        return found[i] if i >= 0 and found[i].span.start <= offset < found[i].span.end else None

    def _fact(self, path: Path, offset: int, kind: FactKind) -> PositionFacts:
        entry = self._facts.get((path, offset), {})
        if kind not in entry:
            members = self.request.members if kind == "class" else []
            self._merge(self._export(ExportRequest(names=[], files=[], members=members, facts=[
                FactQuery(path=path, offset=offset, kinds=(kind,))])))
            entry = self._facts.setdefault((path, offset), {})
            entry.setdefault(kind, PositionFacts(path=path, offset=offset, kinds=(kind,)))
        return entry[kind]

    def ensure(self, queries: list[FactQuery]) -> None:
        """Export, in one request, the facts of `queries` the index does not hold."""
        missing: list[FactQuery] = []
        for q in queries:
            held = self._facts.get((q.path, q.offset), {})
            if any(k not in held for k in q.kinds):
                missing.append(q)
        if missing:
            self._merge(self._export(ExportRequest(names=[], files=[], facts=missing)))

    def definition(self, path: Path, offset: int) -> list[Span]:
        return list(self._fact(path, offset, "definition").definition)

    def signature(self, path: Path, offset: int) -> PositionFacts:
        """The signature fact of the call whose keyword or callee name starts at `offset`."""
        return self._fact(path, offset, "signature")

    def class_facts(self, path: Path, offset: int) -> PositionFacts:
        """The class fact of the class whose name starts at `offset`: its ancestors and the members of the run's
        new names a class of them outside the project declares."""
        return self._fact(path, offset, "class")

    def type_definition(self, path: Path, offset: int) -> list[Span]:
        return list(self._fact(path, offset, "typeDefinition").type_definition)

    def verdict(self, path: Path, offset: int) -> Verdict | None:
        """`Unknown`, `Any` or `Never` when the hover at `offset` types a name so."""
        return self._fact(path, offset, "verdict").verdict

    def receiver(self, path: Path, name: str, offset: int) -> Verdict | None:
        """The receiver verdict of the access `x.NAME` whose member name starts at `offset`."""
        found = self.at(path, name, offset)
        if found is not None and found.kind == "member" and found.span.start == offset:
            return found.receiver
        return self._fact(path, offset, "access").access

    # ---- the probe round

    def probe(self, texts: dict[Path, str], queries: list[FactQuery]) -> None:
        """Export `queries` with the files of `texts` opened as those texts."""
        if not queries:
            return
        found = self._export(ExportRequest(names=[], files=[], facts=queries), texts)
        for facts in found.answers:
            self._probes[facts.path, facts.offset] = facts

    def probed(self, path: Path, offset: int) -> PositionFacts | None:
        """The probe round's facts at `offset` of a probe text."""
        return self._probes.get((path, offset))

    def record_parameter_renames(self, renames: frozenset[tuple[str, str]], texts: dict[Path, str],
                                 shifts: dict[Path, list[tuple[int, int]]]) -> None:
        """The run's parameter renames: each old and new name, each file declaring one as its text with them renamed,
        and per such file the start and the growth of each edit."""
        self._parameter_renames = renames
        self._renamed_texts = texts
        self._shifts = shifts

    def parameter_renames(self) -> frozenset[tuple[str, str]]:
        """The old and new name of every parameter rename of the run."""
        return self._parameter_renames

    def probe_signatures(self, sites: Iterable[tuple[Path, int]]) -> None:
        """Export, in one request, the signature at each of `sites` not yet probed, over the renamed texts."""
        missing = sorted(set(sites) - self._renamed_signatures.keys())
        shifted = {(path, offset): offset + sum(grown for start, grown in self._shifts.get(path, ()) if start < offset)
                   for path, offset in missing}
        self.probe(self._renamed_texts, [FactQuery(path=path, offset=shifted[path, offset], kinds=("signature",))
                                         for path, offset in missing])
        for path, offset in missing:
            facts = self.probed(path, shifted[path, offset])
            self._renamed_signatures[path, offset] = facts.signature if facts is not None else ()

    def renamed_signature(self, path: Path, offset: int) -> tuple[tuple[str, ...], ...] | None:
        """The signature at `offset` (the file's own) once the run's renamed parameters are renamed, when probed."""
        return self._renamed_signatures.get((path, offset))

    def record_probe(self, path: Path, literal: tuple[int, int], access: Verdict | None, definitions: list[Span]) -> None:
        self._probe_results[path, literal] = (access, definitions)

    def probe_result(self, path: Path, literal: tuple[int, int]) -> tuple[Verdict | None, list[Span]] | None:
        """The receiver verdict and declarations of the probe access standing for the member call whose literal is
        `literal`, in the files' own offsets."""
        return self._probe_results.get((path, literal))


class ClassFactSource:
    """Class facts by position; a miss is exported alone, looking up `members`, through the run's language server."""

    def __init__(self, facts: dict[tuple[Path, int], PositionFacts], members: list[str],
                 source: Callable[[Path], SourceFile | None], server: ServerSession) -> None:
        self._facts = facts
        self._members = members
        self._source = source
        self._server = server

    def class_facts(self, path: Path, offset: int) -> PositionFacts:
        if (path, offset) not in self._facts:
            server = self._server.get()
            source = self._source(path)
            if source is not None:
                server.open(path, source.text)
            request = ExportRequest(names=[], files=[], members=self._members,
                                    facts=[FactQuery(path=path, offset=offset, kinds=("class",))])
            with timed("references"):
                found = server.export(request)
            for facts in [*found.answers, *found.followed]:
                if "class" in facts.kinds:
                    _ = self._facts.setdefault((facts.path, facts.offset), facts)
            _ = self._facts.setdefault((path, offset), PositionFacts(path=path, offset=offset, kinds=("class",)))
        return self._facts[path, offset]
