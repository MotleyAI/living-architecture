"""Field renames of keyed classes (Pydantic models, TypedDicts): keyword arguments and dict keys proven from types.

Every rewrite resolves its target class through basedpyright's declaration locations and looks the field up in that
class's method resolution order; anything not proven so is left unchanged.
"""

from __future__ import annotations

import ast
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
            if not isinstance(stmt, (ast.AnnAssign, ast.Assign)):
                continue
            targets = [stmt.target] if isinstance(stmt, ast.AnnAssign) else stmt.targets
            for target in targets:
                if isinstance(target, ast.Name) and target.id == name:
                    start, end = self.source.span(target)
                    return Span(path=self.source.path, start=start, end=end), stmt
        return None


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
                continue
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
        for cls in ast.walk(source.tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for fn in cls.body:
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or _is_static(fn):
                    continue
                params = [*fn.args.posonlyargs, *fn.args.args]
                name = source.name_span(params[0]) if params else None
                if name is not None and name[0] == spans[0].start:
                    return ClassRef(source, cls)
        return None

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


def _is_static(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in fn.decorator_list)


def _last_name(expr: ast.expr) -> str | None:
    return expr.id if isinstance(expr, ast.Name) else expr.attr if isinstance(expr, ast.Attribute) else None


def _sets_alias_generator(node: ast.ClassDef) -> bool:
    if any(k.arg == "alias_generator" for k in node.keywords):
        return True
    for stmt in node.body:
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            targets = [stmt.target] if isinstance(stmt, ast.AnnAssign) else stmt.targets
            if not any(isinstance(t, ast.Name) and t.id == "model_config" for t in targets):
                continue
            value = stmt.value
            if isinstance(value, ast.Call) and any(k.arg == "alias_generator" for k in value.keywords):
                return True
            if isinstance(value, ast.Dict) and any(
                isinstance(k, ast.Constant) and k.value == "alias_generator" for k in value.keys
            ):
                return True
    return False


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
        members = list(expr.slice.elts) if isinstance(expr.slice, ast.Tuple) else [expr.slice]
    else:
        return expr
    rest = [m for m in members if not (isinstance(m, ast.Constant) and m.value is None)]
    return rest[0] if len(rest) == 1 else None


def _union_members(expr: ast.expr) -> list[ast.expr]:
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
        return [*_union_members(expr.left), *_union_members(expr.right)]
    return [expr]


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

    # ---- typed values

    def dict_value(self, source: SourceFile, rel: str, value: ast.expr, cls: ClassRef, out: list[TextEdit]) -> None:
        """A dict literal validated as `cls`."""
        if not isinstance(value, ast.Dict) or self.facts.chain(cls).kind is None:
            return
        keyed_keys = not self.aliased and not self.facts.generates_aliases(cls)
        for key, item in zip(value.keys, value.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if keyed_keys and key.value == self.old and self._renames(cls, key.value):
                self._key_edit(source, key, rel, out)
            if _mentions(item, self.old) and (found := self._lands(cls, key.value)) is not None:
                self.typed_value(source, rel, item, found[0].source, _annotation(found[2]), out)

    def typed_value(
        self, source: SourceFile, rel: str, value: ast.expr, ann_source: SourceFile, ann: ast.expr | None,
        out: list[TextEdit],
    ) -> None:
        """A literal assigned to a field annotated `ann` (in `ann_source`)."""
        if ann is None or (ann := _without_none(ann)) is None:
            return
        if isinstance(ann, ast.Subscript):
            base = _last_name(ann.value)
            args = list(ann.slice.elts) if isinstance(ann.slice, ast.Tuple) else [ann.slice]
            if base in _LIST_LIKE or base in ("tuple", "Tuple"):
                if base in ("tuple", "Tuple") and not (
                    len(args) == 1 or (len(args) == 2 and isinstance(args[1], ast.Constant) and args[1].value is Ellipsis)
                ):
                    return
                if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
                    for elt in value.elts:
                        self.typed_value(source, rel, elt, ann_source, args[0], out)
                return
            if base in ("dict", "Dict") and len(args) == 2 and _last_name(args[0]) == "str":
                if isinstance(value, ast.Dict):
                    for item in value.values:
                        self.typed_value(source, rel, item, ann_source, args[1], out)
                return
            return
        cls = self.facts.annotation_class(ann_source, ann)
        if cls is not None:
            self.dict_value(source, rel, value, cls, out)

    def field_selection(self, source: SourceFile, rel: str, value: ast.expr, cls: ClassRef, out: list[TextEdit]) -> None:
        """`include=`/`exclude=` of `model_dump`: a set or dict of `cls`'s field names."""
        keyed_keys = not self.aliased and not self.facts.generates_aliases(cls)
        if isinstance(value, ast.Set):
            for elt in value.elts:
                if keyed_keys and isinstance(elt, ast.Constant) and elt.value == self.old and self._renames(cls, self.old):
                    self._key_edit(source, elt, rel, out)
            return
        if not isinstance(value, ast.Dict):
            return
        for key, item in zip(value.keys, value.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if keyed_keys and key.value == self.old and self._renames(cls, key.value):
                self._key_edit(source, key, rel, out)
            if _mentions(item, self.old) and (found := self._lands(cls, key.value)) is not None:
                self._nested_selection(source, rel, item, found[0].source, _annotation(found[2]), out)

    def _nested_selection(
        self, source: SourceFile, rel: str, value: ast.expr, ann_source: SourceFile, ann: ast.expr | None,
        out: list[TextEdit],
    ) -> None:
        if ann is None or (ann := _without_none(ann)) is None:
            return
        if isinstance(ann, ast.Subscript):
            args = list(ann.slice.elts) if isinstance(ann.slice, ast.Tuple) else [ann.slice]
            if _last_name(ann.value) in _LIST_LIKE and isinstance(value, ast.Dict):
                for key, item in zip(value.keys, value.values):
                    if isinstance(key, ast.Constant) and (isinstance(key.value, int) or key.value == "__all__"):
                        self._nested_selection(source, rel, item, ann_source, args[0], out)
            return
        cls = self.facts.annotation_class(ann_source, ann)
        if cls is not None:
            self.field_selection(source, rel, value, cls, out)

    # ---- sinks

    def scan(self, source: SourceFile, rel: str, bindings: Bindings) -> None:
        """Every sink in `source`: calls, TypedDict-annotated assignments and returns."""
        if source.tree is None:
            return
        self._dict_names = {
            t.id
            for n in ast.walk(source.tree)
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict) and _mentions(n.value, self.old)
            for t in n.targets
            if isinstance(t, ast.Name)
        }
        for node in ast.walk(source.tree):
            if isinstance(node, ast.Call) and self._relevant(node):
                self._call(source, rel, node, bindings)
            elif isinstance(node, ast.AnnAssign) and node.value is not None and _mentions(node.value, self.old):
                self._typeddict_value(source, rel, node.value, node.annotation, bindings)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
                for ret in _returns(node):
                    if ret.value is not None and _mentions(ret.value, self.old):
                        self._typeddict_value(source, rel, ret.value, node.returns, bindings)

    def _typeddict_value(self, source: SourceFile, rel: str, value: ast.expr, ann: ast.expr, bindings: Bindings) -> None:
        cls = self.facts.annotation_class(source, ann)
        if cls is not None and self.facts.chain(cls).kind == "typeddict":
            self._sink(source, rel, value, lambda v, out: self.dict_value(source, rel, v, cls, out), bindings)

    def _sink(
        self, source: SourceFile, rel: str, value: ast.expr, rewrite: Callable[[ast.expr, list[TextEdit]], None],
        bindings: Bindings,
    ) -> None:
        if isinstance(value, ast.Name):
            bindings.sink(source, value, rewrite)
        else:
            rewrite(value, self.edits)

    def _relevant(self, call: ast.Call) -> bool:
        return (
            any(k.arg == self.old for k in call.keywords)
            or any(_mentions(a, self.old) or (isinstance(a, ast.Name) and a.id in self._dict_names) for a in _arguments(call))
        )

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
        if method == "model_validate":
            arg = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg == "obj"), None)
            if arg is not None:
                self._sink(source, rel, arg, lambda v, out: self.dict_value(source, rel, v, cls, out), bindings)
        elif method == "model_construct":
            self._construct(source, rel, call, cls, bindings, keywords=True)
        elif method == "model_copy":
            for kw in call.keywords:
                if kw.arg == "update":
                    self._sink(source, rel, kw.value, lambda v, out: self.dict_value(source, rel, v, cls, out), bindings)
        else:
            for kw in call.keywords:
                if kw.arg in ("include", "exclude"):
                    self.field_selection(source, rel, kw.value, cls, self.edits)

    def _construct(
        self, source: SourceFile, rel: str, call: ast.Call, cls: ClassRef, bindings: Bindings, *, keywords: bool
    ) -> None:
        for kw in call.keywords:
            if kw.arg is None:
                self._sink(source, rel, kw.value, lambda v, out: self.dict_value(source, rel, v, cls, out), bindings)
                continue
            if keywords and kw.arg == self.old and self._renames(cls, kw.arg):
                span = source.name_span(kw)
                if span is not None:
                    self.edits.append(TextEdit(path=rel, start=span[0], end=span[1], new_text=self.new))
            if _mentions(kw.value, self.old) and (found := self._lands(cls, kw.arg)) is not None:
                self.typed_value(source, rel, kw.value, found[0].source, _annotation(found[2]), self.edits)

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
        positional = [*fn.args.posonlyargs, *fn.args.args]
        by_name = {a.arg: a for a in [*fn.args.args, *fn.args.kwonlyargs]}
        pairs = [(positional[i], arg) for i, arg in enumerate(call.args) if i < len(positional) and not isinstance(arg, ast.Starred)]
        pairs += [(by_name[k.arg], k.value) for k in call.keywords if k.arg in by_name]
        for param, value in pairs:
            if param.annotation is None or not (_mentions(value, self.old) or isinstance(value, ast.Name)):
                continue
            cls = self.facts.annotation_class(callee, param.annotation)
            if cls is not None and self.facts.chain(cls).kind == "typeddict":
                self._sink(source, rel, value, lambda v, out, c=cls: self.dict_value(source, rel, v, c, out), bindings)


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
    """The dict literal of `var = {...}`, when that is `var`'s only binding in `scope` and every load is a sink."""
    if not isinstance(scope, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)):
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
