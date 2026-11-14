"""Field renames of keyed classes (Pydantic models, TypedDicts): keyword arguments and dict keys proven from types.

Every rewrite resolves its target class through basedpyright's declaration locations and looks the field up in that
class's method resolution order; anything not proven so is left unchanged.
"""

from __future__ import annotations

import ast
import itertools
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Literal

from living_architecture.lang import LanguageServer, Span
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.text_edits import TextEdit

KeyedKind = Literal["pydantic", "typeddict"]
_PLAIN_STRING = re.compile(r"""(?:[rRuU])?(['"])(\w+)\1""")
_LIST_LIKE = {"list", "List", "Sequence", "set", "Set", "frozenset", "FrozenSet"}
_PYDANTIC_METHODS = {"model_validate", "model_construct", "model_copy", "model_dump", "model_dump_json"}
_NONE_NAMES = {"None", "NoneType"}
_DecoratorKind = Literal["static", "class", "plain", "overload"]
_DECORATORS: dict[str, _DecoratorKind] = {
    "builtins.staticmethod": "static",
    "builtins.classmethod": "class",
    "typing.override": "plain",
    "typing_extensions.override": "plain",
    "typing.overload": "overload",
    "typing_extensions.overload": "overload",
}


class UnresolvedBase(Exception):
    """Class `name` has a base at `path`:`line` the language server cannot resolve."""

    def __init__(self, name: str, path: Path, line: int) -> None:
        super().__init__(name, path, line)
        self.name = name
        self.path = path
        self.line = line


class ClassRef:
    """A class declaration: its file and node."""

    def __init__(self, source: SourceFile, node: ast.ClassDef) -> None:
        self.source = source
        self.node = node
        name = source.name_span(node)
        self.key = (source.path, name[0] if name else -1)

    def field(self, name: str) -> tuple[Span, ast.AnnAssign | ast.Assign] | None:
        """The declaration of field `name` in this class's own body."""
        for stmt in self.node.body:
            if (found := field_assignment(stmt, name)) is not None:
                start, end = self.source.span(found[1])
                return Span(path=self.source.path, start=start, end=end), found[0]
        return None


def _targets(stmt: ast.AnnAssign | ast.Assign) -> list[ast.expr]:
    return [stmt.target] if isinstance(stmt, ast.AnnAssign) else stmt.targets


def field_assignment(stmt: ast.stmt, name: str) -> tuple[ast.AnnAssign | ast.Assign, ast.Name] | None:
    """`stmt` with its target, when `stmt` assigns the bare name `name`."""
    if not isinstance(stmt, (ast.AnnAssign, ast.Assign)):
        return None
    target = next((t for t in _targets(stmt) if isinstance(t, ast.Name) and t.id == name), None)
    return (stmt, target) if target is not None else None


class _Chain:
    """A class's resolved ancestry: the method resolution order and whether a keyed root is in it."""

    mro: list[ClassRef]
    kind: KeyedKind | None

    def __init__(self, mro: list[ClassRef], kind: KeyedKind | None) -> None:
        self.mro = mro
        self.kind = kind


def _is_pydantic_main(path: Path) -> bool:
    return path.name == "main.py" and path.parent.name == "pydantic"


def _c3(head: ClassRef, parents: list[list[ClassRef]]) -> list[ClassRef]:
    seqs = [list(s) for s in parents if s] + [[p[0] for p in parents if p]]
    out = [head]
    while seqs := [s for s in seqs if s]:
        for seq in seqs:
            candidate = seq[0]
            if not any(candidate.key in (c.key for c in s[1:]) for s in seqs):
                break
        else:
            return out + [c for s in seqs for c in s if c.key not in {o.key for o in out}]
        out.append(candidate)
        seqs = [s[1:] if s[0].key == candidate.key else s for s in seqs]
    return out


class TypeFacts:
    """Declaration-based type facts from one language-server session, cached."""

    def __init__(self, server: LanguageServer, load: Callable[[Path], SourceFile | None]) -> None:
        self.server = server
        self._load = load
        self._definitions: dict[tuple[Path, int, str], list[Span]] = {}
        self._chains: dict[tuple[Path, int], _Chain] = {}

    def source(self, path: Path) -> SourceFile | None:
        return self._load(path)

    def _query(self, kind: str, path: Path, offset: int) -> list[Span]:
        key = (path, offset, kind)
        if key not in self._definitions:
            query = self.server.definition if kind == "def" else self.server.type_definition
            self._definitions[key] = query(path, offset)
        return self._definitions[key]

    def definition(self, path: Path, offset: int) -> list[Span]:
        return self._query("def", path, offset)

    def type_definition(self, path: Path, offset: int) -> list[Span]:
        return self._query("type", path, offset)

    def span_text(self, span: Span) -> str:
        source = self.source(span.path)
        return source.text[span.start : span.end] if source else ""

    def class_at(self, span: Span) -> ClassRef | None:
        source = self.source(span.path)
        if source is None or source.tree is None:
            return None
        for node in ast.walk(source.tree):
            if isinstance(node, ast.ClassDef) and source.name_span(node) == (span.start, span.end):
                return ClassRef(source, node)
        return None

    def _root_kind(self, span: Span) -> KeyedKind | None:
        text = self.span_text(span)
        if text == "BaseModel" and _is_pydantic_main(span.path):
            return "pydantic"
        if re.match(r"TypedDict\b", text) and span.path.name in ("typing.pyi", "typing_extensions.pyi", "typing_extensions.py"):
            return "typeddict"
        return None

    def chain(self, cls: ClassRef) -> _Chain:
        """`cls`'s ancestry; `UnresolvedBase` when a base in it does not resolve."""
        if cls.key in self._chains:
            return self._chains[cls.key]
        parents: list[list[ClassRef]] = []
        kind: KeyedKind | None = None
        self._chains[cls.key] = _Chain([cls], None)
        for base in cls.node.bases:
            target = _name_node(base)
            if target is None:
                raise UnresolvedBase(cls.node.name, cls.source.path, base.lineno)
            name = cls.source.name_span(target)
            spans = self.definition(cls.source.path, name[0]) if name else []
            if not spans:
                raise UnresolvedBase(cls.node.name, cls.source.path, base.lineno)
            if (root := self._root_kind(spans[0])) is not None:
                kind = kind or root
                continue
            parent = self.class_at(spans[0])
            if parent is None:
                continue
            parent_chain = self.chain(parent)
            kind = kind or parent_chain.kind
            parents.append(parent_chain.mro)
        chain = _Chain(_c3(cls, parents), kind)
        self._chains[cls.key] = chain
        return chain

    def lookup(self, cls: ClassRef, name: str) -> tuple[ClassRef, Span, ast.AnnAssign | ast.Assign] | None:
        """Field `name` as found along `cls`'s method resolution order."""
        for ancestor in self.chain(cls).mro:
            if (found := ancestor.field(name)) is not None:
                return ancestor, *found
        return None

    def generates_aliases(self, cls: ClassRef) -> bool:
        """Whether any class in `cls`'s ancestry configures an `alias_generator`."""
        return any(_sets_alias_generator(c.node) for c in self.chain(cls).mro)

    def resolves_to_pydantic(self, path: Path, offset: int) -> bool:
        return any(_is_pydantic_main(s.path) for s in self.definition(path, offset))

    def target_class(self, source: SourceFile, expr: ast.expr) -> ClassRef | None:
        """The one class `expr` denotes (the class or an instance), or None when not proven."""
        node = _name_node(expr)
        if node is None or (name := source.name_span(node)) is None:
            return None
        if isinstance(node, ast.Name) and (owner := self._receiver_class(source, name[0])) is not None:
            return owner
        spans = [s for s in self.type_definition(source.path, name[0]) if self.span_text(s) not in _NONE_NAMES]
        if len(spans) != 1:
            return None
        return self.class_at(spans[0])

    def _receiver_class(self, source: SourceFile, offset: int) -> ClassRef | None:
        """The class of a method's first parameter (`self`/`cls`) when `offset` names it and nothing rebinds it."""
        spans = self.definition(source.path, offset)
        if len(spans) != 1 or spans[0].path != source.path or source.tree is None:
            return None
        return next(
            (
                ClassRef(source, cls)
                for cls, fn in _methods(source.tree)
                if _receiver_offset(source, fn) == spans[0].start
                and self.method_kind(source, fn, at_call=False) in ("class", "instance")
            ),
            None,
        )

    def _decorator(self, source: SourceFile, decorator: ast.expr) -> _DecoratorKind | None:
        """What `decorator` does to a method's binding, as the checker resolves it; None for any other decorator."""
        if not isinstance(decorator, (ast.Name, ast.Attribute)) or (name := source.name_span(decorator)) is None:
            return None
        kinds: set[_DecoratorKind | None] = {
            _DECORATORS.get(f"{s.path.stem}.{self.span_text(s)}") for s in self.definition(source.path, name[0])
        }
        return kinds.pop() if len(kinds) == 1 else None

    def method_kind(
        self, source: SourceFile, fn: ast.FunctionDef | ast.AsyncFunctionDef, *, at_call: bool
    ) -> Literal["static", "class", "instance"] | None:
        """How method `fn`'s first parameter binds, inside its body or `at_call`; at a call, None when a decorator other
        than `staticmethod`, `classmethod` or `override` may change it."""
        kinds = {self._decorator(source, d) for d in fn.decorator_list} - {"plain", "overload"}
        if at_call and None in kinds:
            return None
        kinds.discard(None)
        if len(kinds) > 1:
            return None
        if "static" in kinds:
            return "static"
        return "class" if "class" in kinds else "instance"

    def is_overload(self, source: SourceFile, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Whether a decorator of `fn` resolves to `typing.overload` or `typing_extensions.overload`."""
        return any(self._decorator(source, d) == "overload" for d in fn.decorator_list)

    def annotation_class(self, source: SourceFile, expr: ast.expr) -> ClassRef | None:
        """The class an annotation expression names."""
        node = _name_node(expr)
        if node is None or (name := source.name_span(node)) is None:
            return None
        spans = self.definition(source.path, name[0])
        return self.class_at(spans[0]) if len(spans) == 1 else None


def _name_node(expr: ast.expr) -> ast.Name | ast.Attribute | None:
    if isinstance(expr, ast.Subscript):
        expr = expr.value
    return expr if isinstance(expr, (ast.Name, ast.Attribute)) else None


def _methods(tree: ast.AST) -> Iterator[tuple[ast.ClassDef, ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Every function in a class body, with its class."""
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef):
            for fn in cls.body:
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield cls, fn


def _receiver_offset(source: SourceFile, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int | None:
    params = [*fn.args.posonlyargs, *fn.args.args]
    name = source.name_span(params[0]) if params else None
    return name[0] if name else None


def _last_name(expr: ast.expr) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return expr.attr
    return None


def _subscript_args(ann: ast.Subscript) -> list[ast.expr]:
    return list(ann.slice.elts) if isinstance(ann.slice, ast.Tuple) else [ann.slice]


def _configures_alias_generator(value: ast.expr | None) -> bool:
    if isinstance(value, ast.Call):
        return any(k.arg == "alias_generator" for k in value.keywords)
    if isinstance(value, ast.Dict):
        return any(isinstance(k, ast.Constant) and k.value == "alias_generator" for k in value.keys)
    return False


def _sets_alias_generator(node: ast.ClassDef) -> bool:
    if any(k.arg == "alias_generator" for k in node.keywords):
        return True
    return any(
        _configures_alias_generator(found[0].value)
        for stmt in node.body
        if (found := field_assignment(stmt, "model_config")) is not None
    )


def declares_alias(stmt: ast.AnnAssign | ast.Assign) -> bool:
    """Whether a field declaration passes `alias` or `validation_alias` to `Field(...)`."""
    value = stmt.value
    return (
        isinstance(value, ast.Call)
        and _last_name(value.func) == "Field"
        and any(k.arg in ("alias", "validation_alias") for k in value.keywords)
    )


def _annotation(stmt: ast.AnnAssign | ast.Assign) -> ast.expr | None:
    return stmt.annotation if isinstance(stmt, ast.AnnAssign) else None


def _mentions(node: ast.AST, name: str) -> bool:
    return any(isinstance(n, ast.Constant) and n.value == name for n in ast.walk(node))


def _without_none(expr: ast.expr) -> ast.expr | None:
    """The single non-None member of an optional annotation, or the annotation itself."""
    members: list[ast.expr]
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
        members = _union_members(expr)
    elif isinstance(expr, ast.Subscript) and _last_name(expr.value) == "Optional":
        members = [expr.slice]
    elif isinstance(expr, ast.Subscript) and _last_name(expr.value) == "Union":
        members = _subscript_args(expr)
    else:
        return expr
    rest = [m for m in members if not (isinstance(m, ast.Constant) and m.value is None)]
    return rest[0] if len(rest) == 1 else None


def _union_members(expr: ast.expr) -> list[ast.expr]:
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
        return [*_union_members(expr.left), *_union_members(expr.right)]
    return [expr]


def _element_annotation(ann: ast.Subscript) -> tuple[Literal["sequence", "mapping"], ast.expr] | None:
    """The item annotation of a homogeneous collection annotation (`list[X]`, `tuple[X, ...]`, `dict[str, X]`)."""
    base = _last_name(ann.value)
    args = _subscript_args(ann)
    homogeneous_tuple = len(args) == 1 or (len(args) == 2 and isinstance(args[1], ast.Constant) and args[1].value is Ellipsis)
    if base in _LIST_LIKE or (base in ("tuple", "Tuple") and homogeneous_tuple):
        return "sequence", args[0]
    if base in ("dict", "Dict") and len(args) == 2 and _last_name(args[0]) == "str":
        return "mapping", args[1]
    return None


def _elements(value: ast.expr, kind: Literal["sequence", "mapping"]) -> list[ast.expr]:
    if kind == "sequence" and isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return value.elts
    if kind == "mapping" and isinstance(value, ast.Dict):
        return value.values
    return []


def _string_items(value: ast.Dict) -> Iterator[tuple[ast.Constant, str, ast.expr]]:
    """Each string-keyed item: the key node, the key and the value."""
    for key, item in zip(value.keys, value.values):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            yield key, key.value, item


def _selects_items(key: ast.expr | None) -> bool:
    """Whether a selection key addresses list items: an index or `"__all__"`."""
    return isinstance(key, ast.Constant) and (isinstance(key.value, int) or key.value == "__all__")


def _keyword_values(call: ast.Call, *names: str) -> list[ast.expr]:
    return [k.value for k in call.keywords if k.arg in names]


class KeyedRename:
    """The rewrites of one keyed-class field rename: `old` → `new`, the field declared at `renamed`."""

    def __init__(self, facts: TypeFacts, old: str, new: str, renamed: set[tuple[Path, int]], aliased: bool) -> None:
        self.facts = facts
        self.old = old
        self.new = new
        self.renamed = renamed
        self.aliased = aliased
        self.edits: list[TextEdit] = []
        self._dict_names: set[str] = set()

    def _lands(self, cls: ClassRef, key: str) -> tuple[ClassRef, Span, ast.AnnAssign | ast.Assign] | None:
        if self.facts.chain(cls).kind is None:
            return None
        return self.facts.lookup(cls, key)

    def _renames(self, cls: ClassRef, key: str) -> bool:
        found = self._lands(cls, key)
        return found is not None and (found[1].path, found[1].start) in self.renamed

    def _key_edit(self, source: SourceFile, node: ast.expr, rel: str, out: list[TextEdit]) -> None:
        """Rewrite a plain string literal's name characters."""
        if not (isinstance(node, ast.Constant) and node.value == self.old):
            return
        start, end = source.span(node)
        m = _PLAIN_STRING.fullmatch(source.text, start, end)
        if m is None:
            return
        out.append(TextEdit(path=rel, start=m.start(2), end=m.end(2), new_text=self.new))

    def _rename_key(self, source: SourceFile, rel: str, key: ast.expr, cls: ClassRef, out: list[TextEdit]) -> None:
        if isinstance(key, ast.Constant) and key.value == self.old and self._renames(cls, self.old):
            self._key_edit(source, key, rel, out)

    def _keyed_keys(self, cls: ClassRef) -> bool:
        return not self.aliased and not self.facts.generates_aliases(cls)

    def _dict_items(
        self, source: SourceFile, rel: str, value: ast.Dict, cls: ClassRef, out: list[TextEdit],
        nested: Callable[[ast.expr, SourceFile, ast.expr | None], None],
    ) -> None:
        """Rename `cls`'s field keys of `value`, and hand each item naming `old` to `nested` with its field's annotation."""
        keyed_keys = self._keyed_keys(cls)
        for key, name, item in _string_items(value):
            if keyed_keys:
                self._rename_key(source, rel, key, cls, out)
            if _mentions(item, self.old) and (found := self._lands(cls, name)) is not None:
                nested(item, found[0].source, _annotation(found[2]))

    # ---- typed values

    def dict_value(self, source: SourceFile, rel: str, value: ast.expr, cls: ClassRef, out: list[TextEdit]) -> None:
        """A dict literal validated as `cls`."""
        if not isinstance(value, ast.Dict) or self.facts.chain(cls).kind is None:
            return
        self._dict_items(
            source, rel, value, cls, out, lambda item, ann_source, ann: self.typed_value(source, rel, item, ann_source, ann, out)
        )

    def typed_value(
        self, source: SourceFile, rel: str, value: ast.expr, ann_source: SourceFile, ann: ast.expr | None,
        out: list[TextEdit],
    ) -> None:
        """A literal assigned to a field annotated `ann` (in `ann_source`)."""
        if ann is None or (ann := _without_none(ann)) is None:
            return
        if not isinstance(ann, ast.Subscript):
            if (cls := self.facts.annotation_class(ann_source, ann)) is not None:
                self.dict_value(source, rel, value, cls, out)
            return
        if (element := _element_annotation(ann)) is not None:
            kind, item_ann = element
            for item in _elements(value, kind):
                self.typed_value(source, rel, item, ann_source, item_ann, out)

    def field_selection(self, source: SourceFile, rel: str, value: ast.expr, cls: ClassRef, out: list[TextEdit]) -> None:
        """`include=`/`exclude=` of `model_dump`: a set or dict of `cls`'s field names."""
        if isinstance(value, ast.Set):
            if self._keyed_keys(cls):
                for elt in value.elts:
                    self._rename_key(source, rel, elt, cls, out)
        elif isinstance(value, ast.Dict):
            self._dict_items(
                source, rel, value, cls, out,
                lambda item, ann_source, ann: self._nested_selection(source, rel, item, ann_source, ann, out),
            )

    def _nested_selection(
        self, source: SourceFile, rel: str, value: ast.expr, ann_source: SourceFile, ann: ast.expr | None,
        out: list[TextEdit],
    ) -> None:
        if ann is None or (ann := _without_none(ann)) is None:
            return
        if not isinstance(ann, ast.Subscript):
            if (cls := self.facts.annotation_class(ann_source, ann)) is not None:
                self.field_selection(source, rel, value, cls, out)
            return
        if _last_name(ann.value) in _LIST_LIKE and isinstance(value, ast.Dict):
            item_ann = _subscript_args(ann)[0]
            for key, item in zip(value.keys, value.values):
                if _selects_items(key):
                    self._nested_selection(source, rel, item, ann_source, item_ann, out)

    # ---- sinks

    def scan(self, source: SourceFile, rel: str, bindings: Bindings) -> None:
        """Every sink in `source`: calls, TypedDict-annotated assignments and returns."""
        if source.tree is None:
            return
        self._dict_names = _dict_names(source.tree, self.old)
        for node in ast.walk(source.tree):
            if isinstance(node, ast.Call) and self._relevant(node):
                self._call(source, rel, node, bindings)
            elif isinstance(node, ast.AnnAssign) and node.value is not None and self._candidate(node.value):
                self._typeddict_value(source, rel, node.value, node.annotation, bindings)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
                self._typeddict_returns(source, rel, node, node.returns, bindings)

    def _candidate(self, value: ast.expr) -> bool:
        """Whether `value` may carry a renamed key: a literal naming it, or a name bound to such a dict."""
        return _mentions(value, self.old) or (isinstance(value, ast.Name) and value.id in self._dict_names)

    def _typeddict_returns(
        self, source: SourceFile, rel: str, fn: ast.FunctionDef | ast.AsyncFunctionDef, returns: ast.expr,
        bindings: Bindings,
    ) -> None:
        for ret in _returns(fn):
            if ret.value is not None and self._candidate(ret.value):
                self._typeddict_value(source, rel, ret.value, returns, bindings)

    def _typeddict_value(self, source: SourceFile, rel: str, value: ast.expr, ann: ast.expr, bindings: Bindings) -> None:
        cls = self.facts.annotation_class(source, ann)
        if cls is not None and self.facts.chain(cls).kind == "typeddict":
            self._sink(source, value, lambda v, out: self.dict_value(source, rel, v, cls, out), bindings)

    def _sink(
        self, source: SourceFile, value: ast.expr, rewrite: Callable[[ast.expr, list[TextEdit]], None],
        bindings: Bindings,
    ) -> None:
        if isinstance(value, ast.Name):
            bindings.sink(source, value, rewrite)
        else:
            rewrite(value, self.edits)

    def _relevant(self, call: ast.Call) -> bool:
        return any(k.arg == self.old for k in call.keywords) or any(self._candidate(a) for a in _arguments(call))

    def _call(self, source: SourceFile, rel: str, call: ast.Call, bindings: Bindings) -> None:
        func = call.func
        method = func.attr if isinstance(func, ast.Attribute) and func.attr in _PYDANTIC_METHODS else None
        if method is not None:
            assert isinstance(func, ast.Attribute)
            name = source.name_span(func)
            if name is None or not self.facts.resolves_to_pydantic(source.path, name[0]):
                return
            cls = self.facts.target_class(source, func.value)
            if cls is None or self.facts.chain(cls).kind != "pydantic":
                return
            self._pydantic_call(source, rel, call, method, cls, bindings)
            return
        cls = self.facts.target_class(source, func) if _name_node(func) is func else None
        if cls is not None and self.facts.chain(cls).kind is not None:
            self._construct(source, rel, call, cls, bindings, keywords=True)
            return
        self._typeddict_arguments(source, rel, call, bindings)

    def _pydantic_call(
        self, source: SourceFile, rel: str, call: ast.Call, method: str, cls: ClassRef, bindings: Bindings
    ) -> None:
        def validated(v: ast.expr, out: list[TextEdit]) -> None:
            self.dict_value(source, rel, v, cls, out)

        if method == "model_construct":
            self._construct(source, rel, call, cls, bindings, keywords=True)
            return
        if method == "model_validate":
            dicts = call.args[:1] or _keyword_values(call, "obj")[:1]
        elif method == "model_copy":
            dicts = _keyword_values(call, "update")
        else:
            for value in _keyword_values(call, "include", "exclude"):
                self.field_selection(source, rel, value, cls, self.edits)
            return
        for value in dicts:
            self._sink(source, value, validated, bindings)

    def _construct(
        self, source: SourceFile, rel: str, call: ast.Call, cls: ClassRef, bindings: Bindings, *, keywords: bool
    ) -> None:
        for kw in call.keywords:
            if kw.arg is None:
                self._sink(source, kw.value, lambda v, out: self.dict_value(source, rel, v, cls, out), bindings)
                continue
            if keywords and not self.aliased and kw.arg == self.old and self._renames(cls, kw.arg):
                span = source.name_span(kw)
                if span is not None:
                    self.edits.append(TextEdit(path=rel, start=span[0], end=span[1], new_text=self.new))
            if _mentions(kw.value, self.old) and (found := self._lands(cls, kw.arg)) is not None:
                self.typed_value(source, rel, kw.value, found[0].source, _annotation(found[2]), self.edits)

    def _positional_parameters(
        self, source: SourceFile, call: ast.Call, callee: SourceFile, fn: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[ast.arg]:
        """The parameters `call`'s positional arguments fill; none when an instance method's binding is unproven."""
        assert callee.tree is not None
        params = [*fn.args.posonlyargs, *fn.args.args]
        if not any(isinstance(c, ast.ClassDef) and fn in c.body for c in ast.walk(callee.tree)):
            return params
        kind = self.facts.method_kind(callee, fn, at_call=True)
        if kind == "static":
            return params
        if kind == "class":
            return params[1:]
        if kind is None or not isinstance(call.func, ast.Attribute):
            return []
        binding = self._receiver_binding(source, call.func.value)
        if binding == "class":
            return params
        return params[1:] if binding == "instance" else []

    def _receiver_binding(self, source: SourceFile, receiver: ast.expr) -> Literal["class", "instance"] | None:
        """Whether `receiver` is provably a class or an instance: a class, a method's own `self`, or a name or attribute
        annotated with a class."""
        if not isinstance(receiver, (ast.Name, ast.Attribute)) or (name := source.name_span(receiver)) is None:
            return None
        spans = self.facts.definition(source.path, name[0])
        if len(spans) != 1:
            return None
        if self.facts.class_at(spans[0]) is not None:
            return "class"
        decl = self.facts.source(spans[0].path)
        return "instance" if decl is not None and self._declares_instance(decl, spans[0]) else None

    def _declares_instance(self, decl: SourceFile, span: Span) -> bool:
        if decl.tree is None:
            return False
        if any(
            _receiver_offset(decl, fn) == span.start and self.facts.method_kind(decl, fn, at_call=False) == "instance"
            for _, fn in _methods(decl.tree)
        ):
            return True
        ann = next((a for n in ast.walk(decl.tree) if (a := _annotation_declared_at(decl, n, span)) is not None), None)
        return isinstance(ann, (ast.Name, ast.Attribute)) and self.facts.annotation_class(decl, ann) is not None

    def _typeddict_arguments(self, source: SourceFile, rel: str, call: ast.Call, bindings: Bindings) -> None:
        node = _name_node(call.func)
        if node is None or node is not call.func or (name := source.name_span(node)) is None:
            return
        spans = self.facts.definition(source.path, name[0])
        if len(spans) != 1 or (callee := self.facts.source(spans[0].path)) is None or callee.tree is None:
            return
        fn = next(
            (
                n for n in ast.walk(callee.tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and callee.name_span(n) == (spans[0].start, spans[0].end)
            ),
            None,
        )
        if fn is None:
            return
        leading = itertools.takewhile(lambda a: not isinstance(a, ast.Starred), call.args)
        pairs = list(zip(self._positional_parameters(source, call, callee, fn), leading))
        by_name = {a.arg: a for a in [*fn.args.args, *fn.args.kwonlyargs]}
        pairs += [(by_name[k.arg], k.value) for k in call.keywords if k.arg in by_name]
        for param, value in pairs:
            if param.annotation is None or not (_mentions(value, self.old) or isinstance(value, ast.Name)):
                continue
            cls = self.facts.annotation_class(callee, param.annotation)
            if cls is not None and self.facts.chain(cls).kind == "typeddict":
                self._sink(source, value, lambda v, out, c=cls: self.dict_value(source, rel, v, c, out), bindings)


def _annotation_declared_at(source: SourceFile, node: ast.AST, span: Span) -> ast.expr | None:
    """The annotation of `node` when it is the parameter or annotated assignment declaring the name starting at `span`
    (a parameter's definition span covers its annotation too)."""
    if isinstance(node, ast.arg):
        target: ast.AST = node
    elif isinstance(node, ast.AnnAssign):
        target = node.target
    else:
        return None
    name = source.name_span(target)
    return node.annotation if name is not None and name[0] == span.start else None


def _dict_names(tree: ast.AST, old: str) -> set[str]:
    """Names assigned a dict literal mentioning `old`."""
    return {
        t.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict) and _mentions(n.value, old)
        for t in n.targets
        if isinstance(t, ast.Name)
    }


def _arguments(call: ast.Call) -> Iterator[ast.expr]:
    yield from call.args
    yield from (k.value for k in call.keywords)


def _returns(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.Return]:
    """The `return` statements of `fn` itself, not of nested functions or classes."""
    stack: list[ast.AST] = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Return):
            yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(node))


class Bindings:
    """Dict literals bound once to a name whose every load is a sink argument (the single-binding rule)."""

    def __init__(self) -> None:
        self._sinks: dict[tuple[Path, int], list[tuple[SourceFile, ast.Name, Callable[[ast.expr, list[TextEdit]], None]]]] = {}

    def sink(self, source: SourceFile, name: ast.Name, rewrite: Callable[[ast.expr, list[TextEdit]], None]) -> None:
        self._sinks.setdefault((source.path, id(name)), []).append((source, name, rewrite))

    def edits(self) -> list[TextEdit]:
        by_scope: dict[tuple[Path, int, str], list[tuple[SourceFile, ast.Name, Callable[[ast.expr, list[TextEdit]], None]]]] = {}
        for entries in self._sinks.values():
            for source, name, rewrite in entries:
                scope = _scope_of(source, name)
                if scope is not None:
                    by_scope.setdefault((source.path, id(scope), name.id), []).append((source, name, rewrite))
        out: list[TextEdit] = []
        for (_, _, var), sinks in by_scope.items():
            source = sinks[0][0]
            scope = _scope_of(source, sinks[0][1])
            assert scope is not None
            literal = _single_binding(scope, var, {id(n) for _, n, _ in sinks})
            if literal is None:
                continue
            results: list[list[TextEdit]] = []
            for _, _, rewrite in sinks:
                found: list[TextEdit] = []
                rewrite(literal, found)
                results.append(sorted(found, key=lambda e: e.start))
            if all(r == results[0] for r in results):
                out += results[0]
        return out


_SCOPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_ALL_SCOPES = (*_SCOPES, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _scope_of(source: SourceFile, name: ast.Name) -> ast.AST | None:
    """The innermost function or module scope holding `name`."""
    if source.tree is None:
        return None
    found: list[ast.AST] = []

    def visit(node: ast.AST, scope: ast.AST) -> bool:
        if node is name:
            found.append(scope)
            return True
        inner = node if isinstance(node, _ALL_SCOPES) else scope
        return any(visit(child, inner) for child in ast.iter_child_nodes(node))

    visit(source.tree, source.tree)
    return found[0] if found else None


def _own_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    """The nodes of `scope`, not descending into nested scopes."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _ALL_SCOPES):
            stack.extend(ast.iter_child_nodes(node))


def _nested_scopes(scope: ast.AST) -> Iterator[ast.AST]:
    for node in _own_nodes(scope):
        if isinstance(node, _ALL_SCOPES):
            yield node


def _binds_otherwise(node: ast.AST, var: str) -> bool:
    """Whether `node` binds `var` other than by a plain assignment or name store."""
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return var in node.names
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == var
    if isinstance(node, ast.alias):
        return (node.asname or node.name.split(".")[0]) == var
    if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
        return node.name == var
    if isinstance(node, ast.arg):
        return node.arg == var
    return False


def _single_binding(scope: ast.AST, var: str, sink_loads: set[int]) -> ast.Dict | None:
    """The dict literal of `var = {...}`, when that is `var`'s only binding in function `scope` and every load is a
    sink. A module-scope name is never one: other modules may import it."""
    if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    own = list(_own_nodes(scope))
    if any(_binds_otherwise(n, var) for n in own):
        return None
    names = [n for n in own if isinstance(n, ast.Name) and n.id == var]
    stores = [n for n in names if not isinstance(n.ctx, ast.Load)]
    assigns = [
        n for n in own
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and stores and n.targets[0] is stores[0]
    ]
    if len(stores) != 1 or len(assigns) != 1 or not isinstance(assigns[0].value, ast.Dict):
        return None
    if any(id(n) not in sink_loads for n in names if isinstance(n.ctx, ast.Load)):
        return None
    for inner in _nested_scopes(scope):
        if any(
            (isinstance(n, ast.Name) and n.id == var) or _binds_otherwise(n, var) for n in ast.walk(inner)
        ):
            return None
    return assigns[0].value
