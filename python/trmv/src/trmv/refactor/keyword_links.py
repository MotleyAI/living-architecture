"""Call keywords of an old name that the checker resolves to no declaration: the signature proof that links one to a
renamed parameter, and the `**kwargs` carriers that take one to a renamed parameter or keyed field."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from trmv.lang import Span
from trmv.refactor.keyed import (
    ClassRef,
    TypeFacts,
    UnresolvedBase,
    binds_otherwise,
    declares_alias,
    own_nodes,
    plain_key_span,
    single_binding,
)
from trmv.refactor.occurrence_index import RunIndex, carrier_queries, unpacked_keys
from trmv.refactor.python_source import SourceFile, every_parameter, name_end, nfkc
from trmv.refactor.text_edits import TextEdit, apply_edits

Function = ast.FunctionDef | ast.AsyncFunctionDef
Load = Callable[[Path], SourceFile | None]
Verdict = Literal["renamed", "other", "mixed", "unresolved"]
_Landing = Literal["renamed", "other", "mixed", "unresolved", "declared"]
_SinkKind = Literal["call", "keyed"]
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_NESTED = (*_FUNCTIONS, ast.Lambda, ast.ClassDef, *_COMPREHENSIONS)
_CONSTRUCTORS = ("__init__", "__new__")
_METHOD_DECORATORS = ("staticmethod", "classmethod")
_KEY_METHODS = ("get", "pop", "setdefault")
_KEYED_ARGUMENTS = (("update", "model_copy"), ("obj", "model_validate"))


class KeywordSite(BaseModel):
    """A keyword `old=` of a call, or a constant key `"old"` of a dict literal unpacked into one: the span of its name
    characters, its line, and where the call's signature fact is asked (None: the callee is no name)."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    call: ast.Call
    span: tuple[int, int]
    line: int
    keyword: bool
    query: int | None


def keyword_sites(source: SourceFile, old: str) -> list[KeywordSite]:
    """Every keyword site of `old` in `source`, in source order."""
    out: list[KeywordSite] = []
    for call in source.of_type(ast.Call):
        callee = source.name_span(call.func) if isinstance(call.func, (ast.Name, ast.Attribute)) else None
        for k in call.keywords:
            if k.arg == old and (span := source.name_span(k)) is not None:
                out.append(KeywordSite(call=call, span=span, line=source.line(span[0]), keyword=True, query=span[0]))
            elif k.arg is None and isinstance(k.value, ast.Dict):
                out += [
                    KeywordSite(call=call, span=span, line=source.line(span[0]), keyword=False,
                                query=callee[0] if callee is not None else None)
                    for key in unpacked_keys(k.value) if (span := plain_key_span(source, key, old)) is not None
                ]
    return sorted(out, key=lambda s: s.span)


def _takes_by_name(load: Load, span: Span, old: str) -> bool:
    """Whether the declaration at `span` is named `old` and is no `**kwargs` parameter."""
    source = load(span.path)
    if source is None or not source.text.startswith(old, span.start) or name_end(source.text, span.start) != span.start + len(old):
        return False
    before = span.start - 1
    while before >= 0 and source.text[before] in " \t":
        before -= 1
    return before < 0 or source.text[before] != "*"


def unresolved_sites(index: RunIndex, load: Load, path: Path, source: SourceFile, old: str) -> Iterator[KeywordSite]:
    """The keyword sites of `old` the checker resolves to no declaration of that name: a keyword it binds to a
    `**kwargs` parameter is one."""
    for site in index.memo(("keyword_sites", path, old), partial(keyword_sites, source, old)):
        found = index.at(path, old, site.span[0]) if site.keyword else None
        if found is None or not any(_takes_by_name(load, d.span, old) for d in found.declarations):
            yield site


class ParameterRename(BaseModel):
    """A parameter rename as the signature proof needs it: its names, renamed declarations and candidate files."""

    model_config = ConfigDict(frozen=True)

    old: str
    new: str
    seeds: frozenset[tuple[str, int]]
    candidates: tuple[str, ...]


def _binds_old(index: RunIndex, path: Path, query: int, old: str) -> bool:
    """Whether every callable alternative at `query` binds `old`."""
    before = index.signature(path, query).signature
    return bool(before) and all(old in names for names in before)


def _seed_edits(source: Callable[[str], SourceFile], renames: list[ParameterRename]) -> dict[str, list[TextEdit]]:
    """Per file, the edits renaming the run's parameter declarations; none for a file where two renames meet on one."""
    edits: dict[str, set[TextEdit]] = {}
    for r in renames:
        for rel, start in r.seeds:
            if source(rel).text.startswith(r.old, start):
                edits.setdefault(rel, set()).add(TextEdit(path=rel, start=start, end=start + len(r.old), new_text=r.new))
    return {rel: sorted(found, key=lambda e: e.start) for rel, found in edits.items()
            if len({e.start for e in found}) == len(found)}


def signature_round(index: RunIndex, root: Path, source: Callable[[str], SourceFile], load: Load,
                    renames: list[ParameterRename]) -> None:
    """One export for every unresolved keyword site whose signature binds its old name: the signature there again,
    with each file declaring a renamed parameter opened as its text with that parameter renamed."""
    renamed = _seed_edits(source, renames)
    index.record_parameter_renames(
        frozenset((r.old, nfkc(r.new)) for r in renames),
        {root / rel: apply_edits(source(rel).text, found) for rel, found in renamed.items()},
        {root / rel: [(e.start, len(e.new_text) - (e.end - e.start)) for e in found] for rel, found in renamed.items()})
    index.probe_signatures(
        (root / rel, site.query) for r in renames for rel in r.candidates
        for site in unresolved_sites(index, load, root / rel, source(rel), r.old)
        if site.query is not None and _binds_old(index, root / rel, site.query, r.old))


def signature_proof(index: RunIndex, path: Path, query: int, old: str, new: str) -> bool:
    """Whether every callable alternative of the call at `query` binds `old` as the code is and `new` in its place once
    the run's renamed parameters are renamed, its other names changing only by the run's parameter renames; names are
    compared as Python binds them."""
    before = index.signature(path, query).signature
    after = index.renamed_signature(path, query)
    return bool(before) and after is not None and len(after) == len(before) and all(
        renamed_names(index.parameter_renames(), b, a, (old, nfkc(new))) for b, a in zip(before, after, strict=True))


def signature_links(index: RunIndex, path: Path, site: KeywordSite, old: str, new: str) -> bool:
    """Whether the signature at `site` proves its keyword follows the rename."""
    return site.query is not None and signature_proof(index, path, site.query, old, new)


def renamed_names(run: frozenset[tuple[str, str]], before: tuple[str, ...], after: tuple[str, ...],
                  rename: tuple[str, str]) -> bool:
    """Whether `after` names the parameters of `before` in their order, one changed by `rename` and any other only by
    a rename of `run`."""
    if len(before) != len(after):
        return False
    changed = {(b, a) for b, a in zip(before, after, strict=True) if b != a}
    return rename in changed and changed <= run


def _attr(call: ast.Call) -> str | None:
    return call.func.attr if isinstance(call.func, ast.Attribute) else None


def _sink_of(source: SourceFile, node: ast.expr) -> tuple[_SinkKind, ast.Call] | None:
    """The sink `node` is handed to as a whole mapping: unpacked into a call, or validated as a keyed class."""
    parent = source.parent(node)
    if isinstance(parent, ast.keyword):
        call = source.parent(parent)
        if not isinstance(call, ast.Call):
            return None
        if parent.arg is None:
            return "call", call
        return ("keyed", call) if (parent.arg, _attr(call)) in _KEYED_ARGUMENTS else None
    if isinstance(parent, ast.Call) and parent.args and parent.args[0] is node and _attr(parent) == "model_validate":
        return "keyed", parent
    return None


def _truth(source: SourceFile, node: ast.AST) -> bool:
    """Whether `node` is only tested for truth."""
    parent = source.parent(node)
    if isinstance(parent, (ast.If, ast.While, ast.IfExp, ast.Assert)):
        return parent.test is node
    if isinstance(parent, ast.UnaryOp):
        return isinstance(parent.op, ast.Not)
    return isinstance(parent, ast.BoolOp) and _truth(source, parent)


def _is_key_form(parent: ast.AST | None, use: ast.Name) -> bool:
    """Whether `use` under `parent` is subscripted, asked for a key by method, or tested for membership."""
    if isinstance(parent, ast.Subscript):
        return parent.value is use
    if isinstance(parent, ast.Attribute):
        return parent.attr in _KEY_METHODS
    return isinstance(parent, ast.Compare) and len(parent.ops) == 1 and isinstance(parent.ops[0], (ast.In, ast.NotIn))


def _form_key(source: SourceFile, parent: ast.AST | None, use: ast.Name) -> ast.AST | None:
    """The key of the key form `use` stands in under `parent`."""
    if isinstance(parent, ast.Subscript):
        return parent.slice
    if isinstance(parent, ast.Attribute):
        call = source.parent(parent)
        return call.args[0] if isinstance(call, ast.Call) and call.func is parent and call.args else None
    return parent.left if isinstance(parent, ast.Compare) and parent.comparators[0] is use else None


def _binds_locally(scope: Function | ast.ClassDef, name: str) -> bool:
    """Whether `scope`'s body binds `name` as a name of its own."""
    own = list(own_nodes(scope))
    if any(isinstance(n, (ast.Global, ast.Nonlocal)) and name in n.names for n in own):
        return False
    return any(binds_otherwise(n, name) or (isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store))
               for n in own)


def _binds(scope: ast.AST, name: str) -> bool:
    """Whether nested scope `scope` binds `name` itself: as a parameter, a local or a comprehension target."""
    if isinstance(scope, (*_FUNCTIONS, ast.Lambda)):
        return any(a.arg == name for a in every_parameter(scope.args)) or (
            isinstance(scope, _FUNCTIONS) and _binds_locally(scope, name))
    if isinstance(scope, _COMPREHENSIONS):
        return any(isinstance(n, ast.Name) and n.id == name for g in scope.generators for n in ast.walk(g.target))
    return False


def _outer_parts(scope: ast.AST) -> list[ast.expr]:
    """The expressions of nested scope `scope` evaluated in the scope holding it."""
    if isinstance(scope, _COMPREHENSIONS):
        return [scope.generators[0].iter]
    if isinstance(scope, (*_FUNCTIONS, ast.Lambda)):
        defaults = [*scope.args.defaults, *(d for d in scope.args.kw_defaults if d is not None)]
        if isinstance(scope, ast.Lambda):
            return defaults
        annotations = [a.annotation for a in every_parameter(scope.args) if a.annotation is not None]
        return [*scope.decorator_list, *defaults, *annotations, *([scope.returns] if scope.returns is not None else [])]
    if isinstance(scope, ast.ClassDef):
        return [*scope.decorator_list, *scope.bases, *(k.value for k in scope.keywords)]
    return []


def _uses(fn: Function, name: str) -> tuple[list[ast.Name], bool]:
    """The uses of `name` in `fn`'s own scope, and whether it is out of their reach: a nested scope that does not bind
    it mentions it, or a statement binds it without a name store. A class body binding it hides it from that body
    and the headers of its scopes only."""
    found: list[ast.Name] = []
    opaque = False
    stack: list[ast.AST] = list(fn.body)
    while stack:
        node = stack.pop()
        opaque = opaque or binds_otherwise(node, name)
        if isinstance(node, ast.Name):
            if node.id == name:
                found.append(node)
        elif isinstance(node, _NESTED):
            outer = _outer_parts(node)
            stack.extend(outer)
            opaque = opaque or _nested_reads(node, name, outer)
        else:
            stack.extend(ast.iter_child_nodes(node))
    return found, opaque


def _nested_reads(scope: ast.AST, name: str, outer: list[ast.expr]) -> bool:
    """Whether nested scope `scope` reads `name` of the scope holding it, below its `outer` parts."""
    if isinstance(scope, ast.ClassDef) and _binds_locally(scope, name):
        inner = [n for stmt in scope.body for n in [stmt, *own_nodes(stmt)] if isinstance(n, _NESTED)]
        return any(_reads_outer(n, name, _outer_parts(n)) for n in inner)
    return _reads_outer(scope, name, outer)


def _reads_outer(scope: ast.AST, name: str, outer: list[ast.expr]) -> bool:
    """Whether nested scope `scope` mentions or rebinds `name` below its `outer` parts without binding it itself."""
    skipped = {id(n) for part in outer for n in ast.walk(part)}
    return not _binds(scope, name) and any(
        id(n) not in skipped and ((isinstance(n, ast.Name) and n.id == name) or (n is not scope and binds_otherwise(n, name)))
        for n in ast.walk(scope))


class CarrierShape:
    """How a `def` uses its `**kw` name: its sinks, its key-form strings, the constant keys of the dict literals
    holding it (`staged_keys`: of those bound to a name), the callees measuring it, and whether every use is a sink, a key form or a neutral use."""

    def __init__(self, source: SourceFile, fn: Function) -> None:
        assert fn.args.kwarg is not None
        self.sinks: list[tuple[_SinkKind, ast.Call]] = []
        self.keys: list[ast.Constant] = []
        self.literal_keys: set[str] = set()
        self.staged_keys: set[str] = set()
        self.measures: list[ast.Name] = []
        uses, opaque = _uses(fn, fn.args.kwarg.arg)
        self.resolved = not opaque
        for use in uses:
            self.resolved = self._use(source, fn, use) and self.resolved

    def _use(self, source: SourceFile, fn: Function, use: ast.Name) -> bool:
        """File one use; whether it is a sink, a key form or a neutral use."""
        if not isinstance(use.ctx, ast.Load):
            return False
        if (sink := _sink_of(source, use)) is not None:
            self.sinks.append(sink)
            return True
        parent = source.parent(use)
        if isinstance(parent, ast.Dict):
            self.literal_keys |= {k.value for k in parent.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            return any(k is None and v is use for k, v in zip(parent.keys, parent.values)) and self._literal(source, fn, parent)
        if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == "len":
            self.measures.append(parent.func)
            return len(parent.args) == 1 and not parent.keywords
        if not _is_key_form(parent, use):
            return _truth(source, use)
        key = _form_key(source, parent, use)
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            self.keys.append(key)
            return True
        return False

    def _literal(self, source: SourceFile, fn: Function, literal: ast.Dict) -> bool:
        """File the sinks of a dict literal holding `**kw`: its own, or those of the one name it is bound to."""
        if (sink := _sink_of(source, literal)) is not None:
            self.sinks.append(sink)
            return True
        parent = source.parent(literal)
        if not (isinstance(parent, ast.Assign) and len(parent.targets) == 1 and isinstance(parent.targets[0], ast.Name)):
            return False
        var = parent.targets[0].id
        loads = [n for n in own_nodes(fn) if isinstance(n, ast.Name) and n.id == var and isinstance(n.ctx, ast.Load)]
        sinks = [s for n in loads if (s := _sink_of(source, n)) is not None]
        if len(sinks) != len(loads) or single_binding(fn, var, {id(n) for n in loads}) is not literal:
            return False
        self.sinks += sinks
        self.staged_keys |= {k.value for k in literal.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        return True

    def takes(self, key: str) -> bool:
        """Whether the carrier does anything with `key`: passes its mapping on, uses it unprovably or reads the key."""
        return bool(self.sinks) or not self.resolved or any(k.value == key for k in self.keys)


def _as_verdict(landing: _Landing, declared: Verdict) -> Verdict:
    """A landing as a verdict, `declared` standing for a callee that declares the renamed parameter itself."""
    return declared if landing == "declared" else landing


def _join(landings: list[Verdict]) -> Verdict:
    found = set(landings)
    if "unresolved" in found:
        return "unresolved"
    if "mixed" in found or found == {"renamed", "other"}:
        return "mixed"
    return "renamed" if found == {"renamed"} else "other"


class KeywordFlow:
    """Where the key `old` lands from a call: only on declarations `renamed` holds, on others, on both, or unprovably;
    unprovably too where the key `new` would meet a name a carrier already takes or sets."""

    def __init__(self, index: RunIndex, facts: TypeFacts, old: str, new: str, renamed: Callable[[Path, int], bool]) -> None:
        self.index = index
        self.facts = facts
        self.old = old
        self.new = nfkc(new)
        self._renamed = renamed
        self._verdicts: dict[tuple[Path, int], Verdict] = {}
        self._active: set[tuple[Path, int]] = set()

    def shape(self, source: SourceFile, fn: Function) -> CarrierShape:
        self.index.memo(("carrier_facts", source.path), lambda: self.index.ensure(carrier_queries(source)))
        return self.index.memo(("carrier_shape", source.path, source.span(fn)[0]), partial(CarrierShape, source, fn))

    def _provable(self, source: SourceFile, fn: Function, shape: CarrierShape) -> bool:
        """Whether `shape` is resolved for this key: `fn` is under no decorator that wraps it, every measuring callee is the builtin, each key-form string of
        `old` is a plain literal, and `fn` neither takes nor sets `new` nor passes it at a sink."""
        if not shape.resolved or self.new in shape.literal_keys or any(key.value == self.new for key in shape.keys):
            return False
        if not all(isinstance(d, ast.Name) and d.id in _METHOD_DECORATORS and self._builtin(source, d) for d in fn.decorator_list):
            return False
        taken = {self.new, *(old for old, new in self.index.parameter_renames() if new == self.new)}
        if self.old in shape.staged_keys or any(a.arg in taken for a in (*fn.args.args, *fn.args.kwonlyargs)):
            return False
        if any(self.new in _passed(call) for _, call in shape.sinks):
            return False
        if any(key.value == self.old and plain_key_span(source, key, self.old) is None for key in shape.keys):
            return False
        return all(self._builtin(source, name) for name in shape.measures)

    def _builtin(self, source: SourceFile, name: ast.Name) -> bool:
        span = source.name_span(name)
        found = self.index.definition(source.path, span[0]) if span is not None else []
        return bool(found) and all(s.path.name == "builtins.pyi" for s in found)

    def key_forms(self, source: SourceFile) -> Iterator[tuple[Function, ast.Constant]]:
        """Each key-form string spelling the key, with its carrier."""
        for fn in source.of_type(ast.FunctionDef) + source.of_type(ast.AsyncFunctionDef):
            if fn.args.kwarg is not None and any(isinstance(n, ast.Constant) and n.value == self.old for n in ast.walk(fn)):
                yield from ((fn, key) for key in self.shape(source, fn).keys if key.value == self.old)

    def carrier(self, source: SourceFile, fn: Function) -> Verdict:
        """The verdict of carrier `fn`: the join of its sinks, unresolved in a cycle of carriers."""
        key = (source.path, source.span(fn)[0])
        if key in self._verdicts:
            return self._verdicts[key]
        if key in self._active:
            return "unresolved"
        self._active.add(key)
        shape = self.shape(source, fn)
        verdict: Verdict = "unresolved"
        if self._provable(source, fn, shape):
            verdict = _join([self._sink(source, fn, kind, call) for kind, call in shape.sinks])
        self._active.discard(key)
        self._verdicts[key] = verdict
        return verdict

    def site(self, source: SourceFile, call: ast.Call) -> Verdict | None:
        """The verdict of an unresolved keyword of `call`: carried to renamed declarations only, to others, or (mixed,
        unresolved) not provably either; a callee declaring a renamed parameter itself is unresolved. None when the
        callee resolves to no def or class."""
        if self._pydantic_method(source, call.func) == "model_construct":
            return "other"
        landings: list[_Landing] = []
        try:
            for decl, node in self._definitions(source, call.func) or []:
                landings.append(self._target(decl, node, site=True))
        except UnresolvedBase:
            return "unresolved"
        return _join([_as_verdict(found, "unresolved") for found in landings]) if landings else None

    def _sink(self, source: SourceFile, fn: Function, kind: _SinkKind, call: ast.Call) -> Verdict:
        try:
            return self._sink_landing(source, fn, kind, call)
        except UnresolvedBase:
            return "unresolved"

    def _sink_landing(self, source: SourceFile, fn: Function, kind: _SinkKind, call: ast.Call) -> Verdict:
        func = call.func
        method = self._pydantic_method(source, func)
        if isinstance(func, ast.Attribute) and method is not None and (kind == "keyed" or method == "model_construct"):
            cls = self._receiver_class(source, func.value)
            return self._field(cls) if cls is not None and self.facts.chain(cls).kind == "pydantic" else "unresolved"
        if kind == "keyed":
            return "unresolved"
        if method == "__init__" and isinstance(func, ast.Attribute) and _is_super(func.value):
            holder = source.parent(fn)
            return self._field(ClassRef(source, holder)) if isinstance(holder, ast.ClassDef) else "unresolved"
        found = self._definitions(source, func, strict=True)
        if found is None:
            return "unresolved"
        return _join([self._sink_target(source, call, decl, node) for decl, node in found])

    def _sink_target(self, source: SourceFile, call: ast.Call, decl: SourceFile, node: Function | ast.ClassDef) -> Verdict:
        """Where the key lands in a sink's callee; a decorated `def` declaring the renamed parameter only by the
        signature's proof."""
        landing = self._target(decl, node, site=False)
        if landing == "declared" and isinstance(node, _FUNCTIONS) and node.decorator_list and not self._proven(source, call):
            return "unresolved"
        return _as_verdict(landing, "renamed")

    def _proven(self, source: SourceFile, call: ast.Call) -> bool:
        """Whether the signature at sink `call` proves the key follows the rename; one export for the file's sinks."""
        self.index.memo(("sink_signatures", source.path, self.old), lambda: self.index.probe_signatures(self._sink_sites(source)))
        span = source.name_span(call.func) if isinstance(call.func, (ast.Name, ast.Attribute)) else None
        return span is not None and signature_proof(self.index, source.path, span[0], self.old, self.new)

    def _sink_sites(self, source: SourceFile) -> list[tuple[Path, int]]:
        """The callee of each call sink of `source`'s carriers whose signature binds the key."""
        carriers = [fn for fn in source.of_type(ast.FunctionDef) + source.of_type(ast.AsyncFunctionDef) if fn.args.kwarg is not None]
        spans = [source.name_span(call.func) for fn in carriers for kind, call in self.shape(source, fn).sinks
                 if kind == "call" and isinstance(call.func, (ast.Name, ast.Attribute))]
        return [(source.path, span[0]) for span in spans if span is not None and _binds_old(self.index, source.path, span[0], self.old)]

    def _pydantic_method(self, source: SourceFile, func: ast.expr) -> str | None:
        """The name of the method of Pydantic's `BaseModel` that callee `func` resolves to."""
        name = source.name_span(func) if isinstance(func, ast.Attribute) else None
        pydantic = name is not None and self.facts.resolves_to_pydantic(source.path, name[0])
        return func.attr if pydantic and isinstance(func, ast.Attribute) else None

    def _receiver_class(self, source: SourceFile, receiver: ast.expr) -> ClassRef | None:
        """The class `receiver` denotes or is an instance of; a call's, the one class it constructs."""
        if not isinstance(receiver, ast.Call):
            return self.facts.target_class(source, receiver)
        found = self._definitions(source, receiver.func, strict=True) or []
        classes = [ClassRef(decl, node) for decl, node in found if isinstance(node, ast.ClassDef)]
        return classes[0] if len(classes) == 1 == len(found) else None

    def _definitions(self, source: SourceFile, func: ast.expr, *, strict: bool = False
                     ) -> list[tuple[SourceFile, Function | ast.ClassDef]] | None:
        """The defs and classes callee `func` resolves to; when `strict`, None unless it resolves and only to those."""
        span = source.name_span(func) if isinstance(func, (ast.Name, ast.Attribute)) else None
        spans = self.index.definition(source.path, span[0]) if span is not None else []
        out: list[tuple[SourceFile, Function | ast.ClassDef]] = []
        for found in spans:
            decl = self.facts.source(found.path)
            node = decl.defined_at((found.start, found.end)) if decl is not None and decl.tree is not None else None
            if node is not None and decl is not None:
                out.append((decl, node))
            elif strict:
                return None
        return out if out or not strict else None

    def _target(self, decl: SourceFile, node: Function | ast.ClassDef, *, site: bool) -> _Landing:
        return self._class(decl, node, site=site) if isinstance(node, ast.ClassDef) else self._function(decl, node)

    def _declared(self, decl: SourceFile, fn: Function) -> bool | None:
        """Whether `fn`'s parameter the key names is renamed; None when no parameter of it takes the key."""
        param = next((a for a in (*fn.args.args, *fn.args.kwonlyargs) if a.arg == self.old), None)
        span = decl.name_span(param) if param is not None else None
        return None if param is None else span is not None and self._renamed(decl.path, span[0])

    def _function(self, decl: SourceFile, fn: Function) -> _Landing:
        declared = self._declared(decl, fn)
        if declared is not None:
            return "declared" if declared else "other"
        return self.carrier(decl, fn) if fn.args.kwarg is not None else "other"

    def _class(self, decl: SourceFile, node: ast.ClassDef, *, site: bool) -> _Landing:
        """Where the key lands in a class's constructors; without one, in a keyed class's fields (at a call site the
        keyed rules own those)."""
        cls = ClassRef(decl, node)
        chain = self.facts.chain(cls)
        constructors: list[tuple[SourceFile, Function]] = []
        for name in _CONSTRUCTORS:
            constructors += next((found for c in chain.mro if (found := [
                (c.source, s) for s in c.node.body if isinstance(s, _FUNCTIONS) and s.name == name])), [])
        if not constructors:
            return "other" if site or chain.kind is None else self._field(cls)
        declared = [d for source, fn in constructors if (d := self._declared(source, fn)) is not None]
        carriers = [(source, fn) for source, fn in constructors if fn.args.kwarg is not None and self._declared(source, fn) is None]
        if not declared:
            return _join([self.carrier(source, fn) for source, fn in carriers])
        if any(declared) and any(self._takes(source, fn) for source, fn in carriers):
            return "unresolved"
        if all(declared):
            return "declared"
        return "unresolved" if any(declared) else "other"

    def _takes(self, source: SourceFile, fn: Function) -> bool:
        return self.shape(source, fn).takes(self.old)

    def _field(self, cls: ClassRef) -> Verdict:
        """Where the key lands among keyed class `cls`'s fields; an aliased field does not take it."""
        found = self.facts.lookup(cls, self.old)
        if found is None or declares_alias(found[2]) or self.facts.generates_aliases(cls):
            return "other"
        return "renamed" if self._renamed(found[1].path, found[1].start) else "other"


def _passed(call: ast.Call) -> set[object]:
    """The names `call` passes by keyword or by a constant key of a dict literal it unpacks, at any depth."""
    passed: set[object] = {k.arg for k in call.keywords}
    literals = [k.value for k in call.keywords if k.arg is None and isinstance(k.value, ast.Dict)]
    return passed.union(key.value for literal in literals for key in unpacked_keys(literal) if isinstance(key, ast.Constant))


def _is_super(receiver: ast.expr) -> bool:
    return isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) and receiver.func.id == "super"
