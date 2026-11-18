"""Call keywords of an old name that the checker resolves to no declaration: the signature proof that links one to a
renamed parameter, and the `**kwargs` carriers that take one to a renamed parameter or keyed field."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from living_architecture.lang import FactQuery, Span
from living_architecture.refactor.keyed import (
    ClassRef,
    TypeFacts,
    UnresolvedBase,
    declares_alias,
    own_nodes,
    plain_key_span,
    single_binding,
)
from living_architecture.refactor.occurrence_index import RunIndex, carrier_queries
from living_architecture.refactor.python_source import SourceFile, every_parameter, name_end
from living_architecture.refactor.text_edits import TextEdit, apply_edits

Function = ast.FunctionDef | ast.AsyncFunctionDef
Load = Callable[[Path], SourceFile | None]
Verdict = Literal["renamed", "other", "mixed", "unresolved"]
_Landing = Literal["renamed", "other", "mixed", "unresolved", "declared"]
_SinkKind = Literal["call", "keyed"]
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_NESTED = (*_FUNCTIONS, ast.Lambda, ast.ClassDef, *_COMPREHENSIONS)
_CONSTRUCTORS = ("__init__", "__new__")
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
                    for key in k.value.keys if (span := plain_key_span(source, key, old)) is not None
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


def signature_round(index: RunIndex, root: Path, source: Callable[[str], SourceFile], load: Load,
                    renames: list[ParameterRename]) -> None:
    """One export for every unresolved keyword site whose signature binds its old name: the signature there again,
    with each file declaring a renamed parameter opened as its text with that parameter renamed."""
    asked: set[tuple[str, int]] = set()
    for r in renames:
        for rel in r.candidates:
            for site in unresolved_sites(index, load, root / rel, source(rel), r.old):
                before = index.signature(root / rel, site.query).signature if site.query is not None else ()
                if site.query is not None and before and all(r.old in names for names in before):
                    asked.add((rel, site.query))
    if not asked:
        return
    edits: dict[str, set[TextEdit]] = {}
    for r in renames:
        for rel, start in r.seeds:
            if source(rel).text.startswith(r.old, start):
                edits.setdefault(rel, set()).add(TextEdit(path=rel, start=start, end=start + len(r.old), new_text=r.new))
    renamed = {rel: sorted(found, key=lambda e: e.start) for rel, found in edits.items()
               if len({e.start for e in found}) == len(found)}

    def probe_offset(rel: str, offset: int) -> int:
        return offset + sum(len(e.new_text) - (e.end - e.start) for e in renamed.get(rel, ()) if e.start < offset)

    queries = sorted(asked)
    index.probe({root / rel: apply_edits(source(rel).text, found) for rel, found in renamed.items()},
                [FactQuery(path=root / rel, offset=probe_offset(rel, offset), kinds=("signature",)) for rel, offset in queries])
    for rel, offset in queries:
        facts = index.probed(root / rel, probe_offset(rel, offset))
        if facts is not None:
            index.record_signature(root / rel, offset, facts.signature)


def signature_links(index: RunIndex, path: Path, site: KeywordSite, old: str, new: str) -> bool:
    """Whether every callable alternative at `site` binds `old` as the code is and `new` in its place once the run's
    renamed parameters are renamed."""
    if site.query is None:
        return False
    before = index.signature(path, site.query).signature
    after = index.renamed_signature(path, site.query)
    return bool(before) and after is not None and len(after) == len(before) and all(
        old in b and new not in b and set(a) == (set(b) - {old}) | {new} for b, a in zip(before, after, strict=True))


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


def _binds(scope: ast.AST, name: str) -> bool:
    """Whether nested scope `scope` binds `name` itself: as a parameter or as a comprehension target."""
    if isinstance(scope, (*_FUNCTIONS, ast.Lambda)):
        return any(a.arg == name for a in every_parameter(scope.args))
    if isinstance(scope, _COMPREHENSIONS):
        return any(isinstance(n, ast.Name) and n.id == name for g in scope.generators for n in ast.walk(g.target))
    return False


def _outer_parts(scope: ast.AST) -> list[ast.expr]:
    """The expressions of nested scope `scope` evaluated in the scope holding it."""
    if isinstance(scope, _COMPREHENSIONS):
        return [scope.generators[0].iter]
    if isinstance(scope, (*_FUNCTIONS, ast.Lambda)):
        decorators = scope.decorator_list if isinstance(scope, _FUNCTIONS) else []
        return [*decorators, *scope.args.defaults, *(d for d in scope.args.kw_defaults if d is not None)]
    return []


def _uses(fn: Function, name: str) -> tuple[list[ast.Name], bool]:
    """The uses of `name` in `fn`'s own scope, and whether a nested scope that does not bind it mentions it."""
    found: list[ast.Name] = []
    nested = False
    stack: list[ast.AST] = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Name):
            if node.id == name:
                found.append(node)
        elif isinstance(node, _NESTED):
            outer = _outer_parts(node)
            stack.extend(outer)
            skipped = {id(n) for part in outer for n in ast.walk(part)}
            nested = nested or (not _binds(node, name) and any(
                isinstance(n, ast.Name) and n.id == name and id(n) not in skipped for n in ast.walk(node)))
        else:
            stack.extend(ast.iter_child_nodes(node))
    return found, nested


class CarrierShape:
    """How a `def` uses its `**kw` name: its sinks, its key-form strings, and whether every use is a sink, a key form
    or a neutral use."""

    def __init__(self, source: SourceFile, fn: Function) -> None:
        assert fn.args.kwarg is not None
        self.sinks: list[tuple[_SinkKind, ast.Call]] = []
        self.keys: list[ast.Constant] = []
        uses, nested = _uses(fn, fn.args.kwarg.arg)
        filed = [self._use(source, fn, use) for use in uses]
        self.resolved = not nested and all(filed)

    def _use(self, source: SourceFile, fn: Function, use: ast.Name) -> bool:
        """File one use; whether it is a sink, a key form or a neutral use."""
        if not isinstance(use.ctx, ast.Load):
            return False
        if (sink := _sink_of(source, use)) is not None:
            self.sinks.append(sink)
            return True
        parent = source.parent(use)
        if isinstance(parent, ast.Dict):
            return any(k is None and v is use for k, v in zip(parent.keys, parent.values)) and self._literal(source, fn, parent)
        key: ast.AST | None = None
        if isinstance(parent, ast.Subscript) and parent.value is use:
            key = parent.slice
        elif isinstance(parent, ast.Attribute) and parent.attr in _KEY_METHODS:
            call = source.parent(parent)
            key = call.args[0] if isinstance(call, ast.Call) and call.func is parent and call.args else None
        elif isinstance(parent, ast.Compare) and len(parent.ops) == 1 and isinstance(parent.ops[0], (ast.In, ast.NotIn)):
            key = parent.left if parent.comparators[0] is use else None
        elif isinstance(parent, ast.Call) and isinstance(parent.func, ast.Name) and parent.func.id == "len":
            return len(parent.args) == 1 and not parent.keywords
        else:
            return _truth(source, use)
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
        return True


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
    """Where the key `old` lands from a call: only on declarations `renamed` holds, on others, on both, or unprovably."""

    def __init__(self, index: RunIndex, facts: TypeFacts, old: str, renamed: Callable[[Path, int], bool]) -> None:
        self.index = index
        self.facts = facts
        self.old = old
        self._renamed = renamed
        self._verdicts: dict[tuple[Path, int], Verdict] = {}
        self._active: set[tuple[Path, int]] = set()

    def shape(self, source: SourceFile, fn: Function) -> CarrierShape:
        self.index.ensure(self.index.memo(("carrier_queries", source.path), partial(carrier_queries, source)))
        return self.index.memo(("carrier_shape", source.path, source.span(fn)[0]), partial(CarrierShape, source, fn))

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
        if shape.resolved:
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
        return _join([_as_verdict(self._target(decl, node, site=False), "renamed") for decl, node in found])

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
        if declared:
            return "declared" if all(declared) else "unresolved" if any(declared) else "other"
        return _join([self.carrier(source, fn) for source, fn in constructors if fn.args.kwarg is not None])

    def _field(self, cls: ClassRef) -> Verdict:
        """Where the key lands among keyed class `cls`'s fields; an aliased field does not take it."""
        found = self.facts.lookup(cls, self.old)
        if found is None or declares_alias(found[2]) or self.facts.generates_aliases(cls):
            return "other"
        return "renamed" if self._renamed(found[1].path, found[1].start) else "other"


def _is_super(receiver: ast.expr) -> bool:
    return isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) and receiver.func.id == "super"
