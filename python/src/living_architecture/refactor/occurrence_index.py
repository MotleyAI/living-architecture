"""A run's occurrence index: every occurrence of the old names in the candidate files and the position facts the rules
ask about, exported in one request by the run's one language server, or read from the cache, then looked up."""

from __future__ import annotations

import ast
import bisect
from collections.abc import Callable, Iterable
from contextlib import ExitStack
from pathlib import Path

from living_architecture.lang import (
    ExportRequest,
    FactQuery,
    LanguageServer,
    Occurrence,
    OccurrenceIndex,
    PositionFacts,
    Span,
)
from living_architecture.lang.language_server import FactKind, Verdict
from living_architecture.refactor.index_cache import IndexCache, request_key
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.timings import timed

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


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
    """One pass over a tree: the nodes holding a string constant in `names`, each node's parent, and the names
    assigned a dict literal holding one."""

    def __init__(self, tree: ast.AST, names: set[str]) -> None:
        self.mentioning: set[int] = set()
        self.parents: dict[int, ast.AST] = {}
        order: list[ast.AST] = []
        stack: list[ast.AST] = [tree]
        while stack:
            node = stack.pop()
            order.append(node)
            for child in ast.iter_child_nodes(node):
                self.parents[id(child)] = node
                stack.append(child)
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
        up = self.parents.get(id(node))
        while up is not None and not isinstance(up, (*_FUNCTIONS, ast.Lambda, ast.ClassDef)):
            up = self.parents.get(id(up))
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
        order: tuple[FactKind, ...] = ("definition", "typeDefinition", "verdict", "access")
        return [FactQuery(path=self.source.path, offset=offset, kinds=tuple(k for k in order if k in kinds))
                for offset, kinds in sorted(self.kinds.items())]


def fact_queries(source: SourceFile, names: set[str]) -> list[FactQuery]:
    """The positions of `source` the rules of a rename of `names` ask about: class bases and field annotations,
    decorators, the callees, receivers and annotations of keyed sinks, and string-member callees and objects."""
    tree = source.tree
    if tree is None:
        return []
    found = _Queries(source)
    shape = _Shape(tree, names)
    returning = {id(fn) for n in ast.walk(tree) if isinstance(n, ast.Return) and n.value is not None
                 and shape.candidate(n.value) and (fn := shape.function_of(n)) is not None}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                found.ask(_name_node(base), "definition")
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign):
                    found.names(stmt.annotation)
        elif isinstance(node, _FUNCTIONS):
            for decorator in node.decorator_list:
                found.ask(decorator if isinstance(decorator, (ast.Name, ast.Attribute)) else None, "definition")
            if node.returns is not None and id(node) in returning:
                found.names(node.returns)
        elif isinstance(node, ast.AnnAssign) and node.value is not None and shape.candidate(node.value):
            found.names(node.annotation)
        elif isinstance(node, ast.Call):
            _call_queries(found, node, names, shape)
    return found.queries()


def _call_queries(found: _Queries, call: ast.Call, names: set[str], shape: _Shape) -> None:
    arguments = [*call.args, *(k.value for k in call.keywords)]
    keyed = any(k.arg in names for k in call.keywords) or any(shape.candidate(a) for a in arguments)
    if keyed and isinstance(call.func, (ast.Name, ast.Attribute)):
        found.ask(call.func, "definition", "typeDefinition")
        if isinstance(call.func, ast.Attribute):
            found.ask(_name_node(call.func.value), "definition", "typeDefinition")
    strings = [s for a in call.args if (s := _plain(a)) is not None]
    if any(s in names or names & set(s.split(".")) for s in strings):
        found.ask(call.func, "definition")
        for a in call.args:
            if isinstance(a, (ast.Name, ast.Attribute)):
                found.ask(a, "verdict")


def _escaped_constant(source: SourceFile, names: set[str]) -> bool:
    return source.tree is not None and any(
        isinstance(n, ast.Constant) and n.value in names for n in ast.walk(source.tree)
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
        self.request = ExportRequest(names=[], files=[])

    # ---- exports

    def prepare(self, names: set[str], files: list[Path]) -> bool:
        """Fix the run's request for `names` over `files`; whether its export is cached."""
        queries = [q for path in files if (source := self._source(path)) is not None for q in fact_queries(source, names)]
        self.request = ExportRequest(names=sorted(names), files=files, facts=queries)
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
        server = self._open([*request.files, *texts], texts)
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

    # ---- lookups

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
            self._merge(self._export(ExportRequest(names=[], files=[], facts=[
                FactQuery(path=path, offset=offset, kinds=(kind,))])))
            entry = self._facts.setdefault((path, offset), {})
            entry.setdefault(kind, PositionFacts(path=path, offset=offset, kinds=(kind,)))
        return entry[kind]

    def definition(self, path: Path, offset: int) -> list[Span]:
        return list(self._fact(path, offset, "definition").definition)

    def type_definition(self, path: Path, offset: int) -> list[Span]:
        return list(self._fact(path, offset, "typeDefinition").type_definition)

    def verdict(self, path: Path, offset: int) -> Verdict | None:
        """`Unknown` or `Any` when the hover at `offset` types a name so."""
        return self._fact(path, offset, "verdict").verdict

    def receiver(self, path: Path, name: str, offset: int) -> Verdict | None:
        """The receiver verdict of the access `x.NAME` whose member name starts at `offset`."""
        found = self.at(path, name, offset)
        if found is not None and found.kind == "member" and found.span.start == offset:
            return found.receiver
        return self._fact(path, offset, "access").access

    # ---- the probe round

    def probe(self, texts: dict[Path, str], queries: list[FactQuery]) -> None:
        """Export `queries` (definitions and access verdicts) with the files of `texts` opened as those texts."""
        if not queries:
            return
        found = self._export(ExportRequest(names=[], files=[], facts=queries), texts)
        for facts in found.answers:
            self._probes[facts.path, facts.offset] = facts

    def probed(self, path: Path, offset: int) -> PositionFacts | None:
        """The probe round's facts at `offset` of a probe text."""
        return self._probes.get((path, offset))

    def record_probe(self, path: Path, literal: tuple[int, int], access: Verdict | None, definitions: list[Span]) -> None:
        self._probe_results[path, literal] = (access, definitions)

    def probe_result(self, path: Path, literal: tuple[int, int]) -> tuple[Verdict | None, list[Span]] | None:
        """The receiver verdict and declarations of the probe access standing for the member call whose literal is
        `literal`, in the files' own offsets."""
        return self._probe_results.get((path, literal))
