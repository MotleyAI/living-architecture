"""The receivers of a member name basedpyright cannot type, and the registry's forms that name a member by a string
(calls, field-name reads, decorators, class-body values): one scan over the run's occurrence index behind
`dr-compliance --attr` and a rename's blind spots and string rewrites."""

from __future__ import annotations

import ast
import bisect
import functools
import io
import re
import tokenize
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from deterministic_refactor.contract import language
from deterministic_refactor.lang import FactQuery, Span
from deterministic_refactor.refactor.occurrence_index import RunIndex
from deterministic_refactor.refactor.python_source import SourceFile

_SPACE = re.compile(r"\s+")


_Position = Annotated[StrictInt, Field(ge=0)]
_KEYS = ("string_member_calls", "name_decorators", "name_reads", "name_class_values")


class StringForm(BaseModel):
    """A call naming a member by a string (`string_member_calls` in the language registry)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    call: str
    module: str
    qualname: str
    syntax: str
    object: _Position | None = None
    member: _Position | None = None
    target: _Position | None = None
    silent: StrictBool = False
    default: _Position | None = None

    def misses_silently(self, call: ast.Call) -> bool:
        """A miss of `call` raises no error."""
        return self.silent or (self.default is not None and len(call.args) > self.default)


class NameDecorator(BaseModel):
    """A decorator whose positional arguments name members of the decorated method's class (`name_decorators`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    call: str
    module: str
    qualname: str


class NameRead(BaseModel):
    """An attribute holding a class's member names, read by a string in `shapes` (`name_reads`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attribute: str
    module: str
    qualname: str
    shapes: tuple[Literal["subscript", "get", "in"], ...]


class NameClassValue(BaseModel):
    """A class-body assignment whose value names members of the class in `shapes` (`name_class_values`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    shapes: tuple[Literal["element", "string", "key"], ...]


class RegistryForms(BaseModel):
    """The string-named member forms of the python registry section."""

    model_config = ConfigDict(frozen=True)

    string_member_calls: tuple[StringForm, ...]
    name_decorators: tuple[NameDecorator, ...] = ()
    name_reads: tuple[NameRead, ...] = ()
    name_class_values: tuple[NameClassValue, ...] = ()

    def modules(self) -> set[str]:
        return {f.module for f in (*self.string_member_calls, *self.name_decorators, *self.name_reads)}


def registry_forms(section: dict[str, object]) -> RegistryForms:
    """The forms of a registry section; `ValueError` for a malformed entry."""
    found = {key: section[key] for key in _KEYS if key in section}
    unlisted = [key for key, entries in found.items() if not isinstance(entries, list)]
    if unlisted:
        raise ValueError(f"{unlisted[0]}: not a list")
    return RegistryForms.model_validate(found)


REGISTRY = registry_forms(language("python"))
FORMS = REGISTRY.string_member_calls


class Blindspot(BaseModel):
    """A receiver of the member name typed `Unknown`, `Any` or `Never`: at an access, or at a string-named access printed as
    `site`, `silent` when its miss raises no error."""

    model_config = ConfigDict(frozen=True)

    line: int
    col: int
    receiver: str
    kind: str
    literal: tuple[int, int] | None = None
    site: str | None = None
    silent: bool = False

    @property
    def check(self) -> str:
        """The compliance check reporting it."""
        return "attr-blindspot" if self.site is None else "string-blindspot"


class FormCall(BaseModel):
    """A string-named access whose string names the member: the call (or a field-name `read`), its literal's inner
    span (a name's span, for a member held by a name) and for a member form the object; `forms` is what the callee
    resolves to (None: it does not resolve)."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    call: ast.expr
    literal: tuple[int, int]
    text: str
    obj: ast.expr | None
    forms: tuple[StringForm, ...] | None
    read: bool = False
    silent: bool = False
    named: bool = False

    @property
    def replaced(self) -> tuple[int, int]:
        """The span a probe replaces: the literal with its quotes, or the name."""
        return self.literal if self.named else (self.literal[0] - 1, self.literal[1] + 1)


class NamedUse(BaseModel):
    """An access with a member form's syntax whose member is a name: the object, the name, and the callee (or a
    read's attribute) to resolve."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    access: ast.expr
    obj: ast.expr
    member: ast.Name | ast.Attribute
    callee: ast.expr
    read: NameRead | None = None


class NameString(BaseModel):
    """A string naming a member of class `cls` in a decorator or class-body value: its inner span, line, and the other
    names beside it."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    cls: ast.ClassDef
    literal: tuple[int, int]
    line: int
    beside: tuple[str, ...]


def plain_literal(source: SourceFile, node: ast.expr) -> tuple[tuple[int, int], str] | None:
    """The inner span and text of a single-quoted or double-quoted string literal without prefix or escapes."""
    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
        return None
    start, end = source.span(node)
    raw = source.text[start:end]
    if len(raw) < 2 or raw[0] not in "'\"" or raw[-1] != raw[0] or raw[1:-1] != node.value or raw[0] in node.value:
        return None
    return (start + 1, end - 1), node.value


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and (head := _dotted(node.value)) is not None:
        return f"{head}.{node.attr}"
    return None


def _syntax(callee: str, form: StringForm) -> bool:
    return callee == form.syntax or callee.endswith(f".{form.syntax}")


def _module_of(path: Path) -> str | None:
    """The registry module `path` (a definition's file) is, by its trailing path components."""
    posix = path.as_posix()
    for module in REGISTRY.modules():
        stem = module.replace(".", "/")
        if any(posix.endswith(f"/{stem}{tail}") for tail in (".py", ".pyi", "/__init__.py", "/__init__.pyi")):
            return module
    return None


class FormResolver:
    """Which registry forms a callee's declarations are."""

    def __init__(self, index: RunIndex, load: Callable[[Path], SourceFile | None]) -> None:
        self.index = index
        self._load = load
        self._classes: dict[Path, list[ast.ClassDef]] = {}

    def _qualname(self, span: Span) -> str | None:
        source = self._load(span.path)
        if source is None or source.tree is None:
            return None
        if span.path not in self._classes:
            self._classes[span.path] = [n for n in source.nodes if isinstance(n, ast.ClassDef)]
        line = source.line(span.start)
        chain = sorted(
            (c for c in self._classes[span.path] if c.lineno <= line <= (c.end_lineno or c.lineno)), key=lambda c: c.lineno
        )
        return ".".join([*(c.name for c in chain), source.text[span.start : span.end]])

    def declared(self, path: Path, source: SourceFile, node: ast.expr) -> list[tuple[str | None, str | None]] | None:
        """The registry module and qualified name of each declaration the name `node` resolves to (None where it is
        in no registry module); None for an expression that is no name."""
        span = source.name_span(node)
        if span is None:
            return None
        out: list[tuple[str | None, str | None]] = []
        for d in self.index.definition(path, span[0]):
            module = _module_of(d.path)
            out.append((module, self._qualname(d) if module is not None else None))
        return out

    def forms(self, path: Path, source: SourceFile, call: ast.Call) -> tuple[StringForm, ...] | None:
        """The forms the callee resolves to; None when basedpyright finds no declaration of it, or declarations of
        which some are forms and some are not (ambiguous)."""
        declared = self.declared(path, source, call.func)
        if declared is None:
            return ()
        if not declared:
            return None
        found: dict[str, StringForm] = {}
        others = 0
        for at in declared:
            matched = {f.call: f for f in FORMS if (f.module, f.qualname) == at}
            found |= matched
            others += not matched
        if found and others:
            return None
        return tuple(found[call] for call in sorted(found))

    def is_entry(self, path: Path, source: SourceFile, node: ast.expr, entries: list[tuple[str, str]]) -> bool | None:
        """Whether every declaration of the name `node` is one of `entries` (module, qualified name); None when it
        resolves to none."""
        declared = self.declared(path, source, node)
        if not declared:
            return None if declared is not None else False
        return all(at in entries for at in declared)


def _member_literal(source: SourceFile, call: ast.Call, form: StringForm, name: str) -> tuple[tuple[int, int], ast.expr] | None:
    """The member literal naming `name` of `call` read as member form `form`, with the object argument."""
    if form.object is None or form.member is None or len(call.args) <= max(form.object, form.member):
        return None
    obj, member = call.args[form.object], call.args[form.member]
    if isinstance(obj, ast.Starred) or any(isinstance(a, ast.Starred) for a in call.args[: form.member + 1]):
        return None
    if form.target is not None and plain_literal(source, call.args[form.target]) is not None:
        return None
    literal = plain_literal(source, member)
    return (literal[0], obj) if literal is not None and literal[1] == name else None


def _read_parts(node: ast.AST) -> tuple[ast.expr, ast.expr, ast.expr, str] | None:
    """A subscript, a `.get(...)` call or an `in` test: the access, what it reads, the member expression and the shape."""
    if isinstance(node, ast.Subscript):
        return node, node.value, node.slice, "subscript"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
        return None if isinstance(node.args[0], ast.Starred) else (node, node.func.value, node.args[0], "get")
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], (ast.In, ast.NotIn)):
        return node, node.comparators[0], node.left, "in"
    return None


def _reads(source: SourceFile) -> Iterator[tuple[ast.expr, ast.Attribute, ast.expr, NameRead]]:
    """Each field-name read of a registry shape: the access, the attribute read, the member expression and the form."""
    by_name = {r.attribute: r for r in REGISTRY.name_reads}
    for parts in map(_read_parts, source.nodes):
        if parts is None or not isinstance(parts[1], ast.Attribute):
            continue
        found = by_name.get(parts[1].attr)
        if found is not None and parts[3] in found.shapes:
            yield parts[0], parts[1], parts[2], found


def _named_call(call: ast.Call) -> NamedUse | None:
    """`call` as a use: it has a member form's syntax and its member is a name."""
    callee = _dotted(call.func)
    for form in FORMS:
        if callee is None or not _syntax(callee, form) or form.object is None or form.member is None:
            continue
        if len(call.args) <= max(form.object, form.member) or any(isinstance(a, ast.Starred) for a in call.args[: form.member + 1]):
            continue
        member = call.args[form.member]
        if isinstance(member, (ast.Name, ast.Attribute)):
            return NamedUse(access=call, obj=call.args[form.object], member=member, callee=call.func)
    return None


def named_uses(source: SourceFile) -> list[NamedUse]:
    """Each call with a member form's syntax, and each field-name read, whose member is a name; syntax only."""
    out = [use for use in map(_named_call, _calls(source)) if use is not None]
    for access, attribute, member, read in _reads(source):
        if isinstance(member, (ast.Name, ast.Attribute)):
            out.append(NamedUse(access=access, obj=attribute.value, member=member, callee=attribute, read=read))
    return out


def _assigned(stmt: ast.stmt) -> tuple[ast.expr, ast.expr] | None:
    """The one target and the value of an assignment."""
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        return stmt.targets[0], stmt.value
    if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        return stmt.target, stmt.value
    return None


def _beside(elements: list[ast.expr | None], own: ast.expr) -> tuple[str, ...]:
    return tuple(e.value for e in elements if e is not own and isinstance(e, ast.Constant) and isinstance(e.value, str))


def _class_value_strings(source: SourceFile, value: ast.expr, form: NameClassValue, name: str) -> Iterator[tuple[ast.expr, tuple[str, ...]]]:
    """Each string of `value` naming `name` in one of the form's shapes, with the names beside it."""
    if "string" in form.shapes and isinstance(value, ast.Constant):
        yield value, ()
    elements: list[ast.expr | None] = []
    if "element" in form.shapes and isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        elements = list(value.elts)
    elif "key" in form.shapes and isinstance(value, ast.Dict):
        elements = list(value.keys)
    for element in elements:
        if element is not None and (found := plain_literal(source, element)) is not None and found[1] == name:
            yield element, _beside(elements, element)


def _target_literal(source: SourceFile, call: ast.Call, form: StringForm, name: str) -> tuple[tuple[int, int], str] | None:
    """The dotted target literal of `call` read as target form `form` when a segment is `name`."""
    if form.target is None or len(call.args) <= form.target or any(isinstance(a, ast.Starred) for a in call.args[: form.target + 1]):
        return None
    literal = plain_literal(source, call.args[form.target])
    return literal if literal is not None and name in literal[1].split(".") else None


class MemberScan:
    """The scan of member name `name` over the run's occurrence index."""

    def __init__(self, index: RunIndex, name: str, load: Callable[[Path], SourceFile | None]) -> None:
        self.index = index
        self.name = name
        self.callees = FormResolver(index, load)

    def accesses(self, path: Path, source: SourceFile) -> Iterator[Blindspot]:
        """`x.NAME` accesses whose receiver is typed `Unknown`, `Any` or `Never`."""
        if source.tree is None:
            return
        for node in source.nodes:
            if not (isinstance(node, ast.Attribute) and node.attr == self.name):
                continue
            span = source.name_span(node)
            kind = self.index.receiver(path, self.name, span[0]) if span is not None else None
            if kind is not None:
                yield Blindspot(line=node.lineno, col=node.col_offset, receiver=access_receiver(source, node), kind=kind)

    def member_calls(self, path: Path, source: SourceFile) -> list[FormCall]:
        """Calls with a member form's syntax whose member literal is NAME, with what their callee resolves to."""
        return self.index.memo(("member_calls", path, self.name), lambda: self._member_calls(path, source))

    def _member_calls(self, path: Path, source: SourceFile) -> list[FormCall]:
        calls = (self._form_call(path, source, call) for call in _calls(source))
        return [*(found for found in calls if found is not None), *self._read_calls(path, source)]

    def _form_call(self, path: Path, source: SourceFile, call: ast.Call) -> FormCall | None:
        """`call` when its member literal is NAME and its callee is, or may be, a member form."""
        callee = _dotted(call.func)
        syntactic = [f for f in FORMS if callee is not None and _syntax(callee, f)]
        found = next(((f, m) for f in syntactic or FORMS if (m := _member_literal(source, call, f, self.name)) is not None), None)
        if found is None:
            return None
        forms = self.callees.forms(path, source, call)
        member = [f for f in forms if _member_literal(source, call, f, self.name)] if forms is not None else None
        if (member is not None and not member) or (member is None and not syntactic):
            return None
        (literal, obj) = found[1]
        silent = any(f.misses_silently(call) for f in (member if member is not None else syntactic))
        return FormCall(call=call, literal=literal, text=self.name, obj=obj,
                        forms=tuple(member) if member is not None else None, silent=silent)

    def _read_calls(self, path: Path, source: SourceFile) -> Iterator[FormCall]:
        """Each field-name read whose member literal is NAME, unless its attribute resolves elsewhere."""
        for access, attribute, member, read in _reads(source):
            literal = plain_literal(source, member)
            if literal is None or literal[1] != self.name:
                continue
            resolved = self.callees.is_entry(path, source, attribute, [(read.module, read.qualname)])
            if resolved is not False:
                yield FormCall(call=access, literal=literal[0], text=self.name, obj=attribute.value,
                               forms=() if resolved else None, read=True)

    def named(self, path: Path, source: SourceFile, use: NamedUse) -> FormCall | None:
        """`use` as an access naming NAME through its member name, when its callee resolves to a member form (its
        attribute to the read's)."""
        span = source.span(use.member)
        if use.read is not None:
            if not self.callees.is_entry(path, source, use.callee, [(use.read.module, use.read.qualname)]):
                return None
            return FormCall(call=use.access, literal=span, text=self.name, obj=use.obj, forms=(), read=True, named=True)
        assert isinstance(use.access, ast.Call)
        forms = self.callees.forms(path, source, use.access)
        member = tuple(f for f in forms or () if f.object is not None and f.member is not None
                       and len(use.access.args) > f.member and use.access.args[f.member] is use.member)
        return FormCall(call=use.access, literal=span, text=self.name, obj=use.obj, forms=member, named=True) if member else None

    def decorator_names(self, path: Path, source: SourceFile) -> list[NameString]:
        """Each positional string naming NAME of a registry name decorator on a method."""
        return self.index.memo(("decorator_names", path, self.name), lambda: self._decorator_names(path, source))

    def _decorator_names(self, path: Path, source: SourceFile) -> list[NameString]:
        entries = [(d.module, d.qualname) for d in REGISTRY.name_decorators]
        out: list[NameString] = []
        for cls in source.of_type(ast.ClassDef):
            methods = [s for s in cls.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for decorator in (d for m in methods for d in m.decorator_list if isinstance(d, ast.Call)):
                args: list[ast.expr | None] = list(decorator.args)
                named = [(a, found[0]) for a in decorator.args
                         if (found := plain_literal(source, a)) is not None and found[1] == self.name]
                if named and self.callees.is_entry(path, source, decorator.func, entries):
                    out += [NameString(cls=cls, literal=span, line=a.lineno, beside=_beside(args, a)) for a, span in named]
        return out

    def class_values(self, source: SourceFile) -> list[NameString]:
        """Each string naming NAME in a registry class-body value."""
        by_name = {v.name: v for v in REGISTRY.name_class_values}
        out: list[NameString] = []
        for cls in source.of_type(ast.ClassDef):
            for target, value in (found for found in map(_assigned, cls.body) if found is not None):
                form = by_name.get(target.id) if isinstance(target, ast.Name) else None
                if form is not None:
                    out += self._value_names(source, cls, value, form)
        return out

    def _value_names(self, source: SourceFile, cls: ast.ClassDef, value: ast.expr, form: NameClassValue) -> list[NameString]:
        out: list[NameString] = []
        for node, beside in _class_value_strings(source, value, form, self.name):
            found = plain_literal(source, node)
            if found is not None and found[1] == self.name:
                out.append(NameString(cls=cls, literal=found[0], line=node.lineno, beside=beside))
        return out

    def target_calls(self, path: Path, source: SourceFile) -> list[FormCall]:
        """Calls whose dotted target has a segment NAME: resolving to a target form, or with a target form's syntax
        and an unresolved callee (`forms` None)."""
        return self.index.memo(("target_calls", path, self.name), lambda: self._target_calls(path, source))

    def _target_calls(self, path: Path, source: SourceFile) -> list[FormCall]:
        out: list[FormCall] = []
        targets = [f for f in FORMS if f.target is not None]
        for call in _calls(source):
            callee = _dotted(call.func)
            syntactic = [f for f in targets if callee is not None and _syntax(callee, f)]
            found = next(((f, t) for f in syntactic or targets if (t := _target_literal(source, call, f, self.name)) is not None), None)
            if found is None:
                continue
            forms = self.callees.forms(path, source, call)
            if forms is None and syntactic:
                out.append(FormCall(call=call, literal=found[1][0], text=found[1][1], obj=None, forms=None))
            elif resolved := tuple(f for f in forms or () if f.target is not None):
                out.append(FormCall(call=call, literal=found[1][0], text=found[1][1], obj=None, forms=resolved))
        return out

    def object_kind(self, path: Path, source: SourceFile, found: FormCall) -> str | None:
        """`Unknown` or `Any` for a member call's object, Unknown for an unresolved callee; None when typed."""
        if found.forms is None and not found.read:
            return "Unknown"
        obj = found.obj
        if isinstance(obj, (ast.Name, ast.Attribute)):
            span = source.name_span(obj)
            return self.index.verdict(path, span[0]) if span else None
        return None

    def probe(self, path: Path, calls: list[FormCall]) -> list[tuple[str | None, list[Span]]]:
        """For each resolved member call, its object's kind when not a name or attribute, and the declarations
        `obj.NAME` lands on, in the files' own offsets: the run's probe round, read back."""
        out: list[tuple[str | None, list[Span]]] = []
        for found in calls:
            kind, definitions = self.index.probe_result(path, found.literal) or (None, [])
            out.append((kind if not isinstance(found.obj, (ast.Name, ast.Attribute)) else None, definitions))
        return out

    def blindspots(self, path: Path, source: SourceFile) -> list[Blindspot]:
        """Every blind spot of NAME in the file: untyped access receivers and string-member objects or callees."""
        return self.index.memo(("blindspots", path, self.name), lambda: self._blindspots(path, source))

    def _blindspots(self, path: Path, source: SourceFile) -> list[Blindspot]:
        found = list(self.accesses(path, source))
        calls = self.member_calls(path, source)
        probed = [c for c in calls if probed_form(c) and not isinstance(c.obj, (ast.Name, ast.Attribute))]
        kinds = dict(zip(map(id, probed), (k for k, _ in self.probe(path, probed)), strict=True)) if probed else {}
        for call in calls:
            kind = kinds.get(id(call)) if id(call) in kinds else self.object_kind(path, source, call)
            if kind is not None:
                assert call.obj is not None
                found.append(Blindspot(line=call.call.lineno, col=call.call.col_offset,
                                       receiver=object_text(source, call), kind=kind, literal=call.literal,
                                       site=site_text(source, call.call, call.obj, self.name), silent=call.silent))
        return found


class TextProbe:
    """`source` with spans replaced: its text, the probe offset of each substitution's anchor, and the map from its
    offsets back to the file's own."""

    def __init__(self, source: SourceFile, substitutions: list[tuple[int, int, str, int]]) -> None:
        """`substitutions`: disjoint spans, each with its new text and an anchor offset inside that text."""
        self.path = source.path
        self.accesses = [0] * len(substitutions)
        self._ends: list[int] = []
        self._growth: list[int] = []
        pieces: list[str] = []
        pos = 0
        for i in sorted(range(len(substitutions)), key=lambda i: substitutions[i][0]):
            start, end, text, anchor = substitutions[i]
            pieces.append(source.text[pos:start])
            self.accesses[i] = sum(map(len, pieces)) + anchor
            pieces.append(text)
            pos = end
            self._ends.append(sum(map(len, pieces)))
            self._growth.append(self._ends[-1] - pos)
        self.text = "".join(pieces) + source.text[pos:]

    def original(self, span: Span) -> Span:
        """`span` in the file's own offsets; a span in another file unchanged."""
        if span.path.resolve() != self.path.resolve():
            return span
        return Span(path=span.path, start=self._back(span.start), end=self._back(span.end))

    def _back(self, offset: int) -> int:
        i = bisect.bisect_right(self._ends, offset)
        return offset - self._growth[i - 1] if i else offset


class Probe(TextProbe):
    """`source` with each member call's literal (or member name) replaced by `(obj).NAME` (NAME the call's own unless
    `name` is given); `accesses[i]` is where call `i`'s access names NAME."""

    def __init__(self, source: SourceFile, calls: list[FormCall], name: str | None = None) -> None:
        substitutions: list[tuple[int, int, str, int]] = []
        for call in calls:
            assert call.obj is not None
            start, end = call.replaced
            receiver = f"({source.segment(call.obj)})."
            substitutions.append((start, end, receiver + (name or call.text), len(receiver)))
        super().__init__(source, substitutions)


def probed_form(call: FormCall) -> bool:
    """`call`'s object is asked about in the probe round: a resolved form, or a field-name read."""
    return call.forms is not None or call.read


def probe_round(index: RunIndex, files: list[tuple[Path, SourceFile]], names: list[str],
                load: Callable[[Path], SourceFile | None],
                named: dict[Path, tuple[SourceFile, list[FormCall]]] | None = None) -> None:
    """One export over every file holding resolved member calls naming one of `names`, and over the `named` calls
    (a member held by a name): each file opened as its probe text, the declarations and receiver verdict of each probe
    access recorded by its call's literal."""
    probes: dict[Path, tuple[Probe, list[FormCall]]] = {}
    held = named or {}
    sources = dict(files) | {path: source for path, (source, _) in held.items()}
    for path, source in sources.items():
        calls = [c for name in names if name in source.text
                 for c in MemberScan(index, name, load).member_calls(path, source) if probed_form(c)]
        calls += [c for c in held.get(path, (source, []))[1] if not any(c.literal == other.literal for other in calls)]
        if calls:
            probes[path] = (Probe(source, calls), calls)
    queries = [FactQuery(path=path, offset=offset, kinds=("definition", "access"))
               for path, (probe, _) in probes.items() for offset in probe.accesses]
    index.probe({path: probe.text for path, (probe, _) in probes.items()}, queries)

    def original(span: Span) -> Span:
        found = probes.get(span.path)
        return found[0].original(span) if found is not None else span

    for path, (probe, calls) in probes.items():
        for call, offset in zip(calls, probe.accesses, strict=True):
            facts = index.probed(path, offset)
            if facts is not None:
                index.record_probe(path, call.literal, facts.access, [original(d) for d in facts.definition])


def collapsed(text: str) -> str:
    """`text` with each run of whitespace as one space."""
    return _SPACE.sub(" ", text)


_LINE_END = re.compile(r"\r\n|\r|\n")


@functools.lru_cache(maxsize=4)
def _comments(text: str) -> tuple[tuple[int, int], ...]:
    """The span of each comment of `text`, in order; lines end as Python ends them."""
    if "#" not in text:
        return ()
    starts = [0, *(m.end() for m in _LINE_END.finditer(text))]
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(_LINE_END.sub("\n", text)).readline))
    except (tokenize.TokenError, SyntaxError):
        return ()
    return tuple((starts[t.start[0] - 1] + t.start[1], starts[t.end[0] - 1] + t.end[1])
                 for t in tokens if t.type == tokenize.COMMENT)


def _blank(text: str, at: int) -> bool:
    """Whether the character at `at` is whitespace or the backslash of a line join."""
    return text[at].isspace() or (text[at] == "\\" and text[at + 1 : at + 2] in ("\r", "\n"))


def _blank_before(text: str, comments: tuple[tuple[int, int], ...], at: int, left: int) -> int:
    """The last offset before `at`, not below `left`, that is neither blank nor in a comment."""
    while at >= left:
        i = bisect.bisect_right(comments, (at, len(text))) - 1
        if i >= 0 and at < comments[i][1]:
            at = comments[i][0] - 1
        elif _blank(text, at):
            at -= 1
        else:
            break
    return at


def _blank_after(text: str, comments: tuple[tuple[int, int], ...], at: int) -> int:
    """The first offset from `at` on that is neither blank nor in a comment."""
    while at < len(text):
        i = bisect.bisect_left(comments, (at, 0))
        if i < len(comments) and comments[i][0] == at:
            at = comments[i][1]
        elif _blank(text, at):
            at += 1
        else:
            break
    return at


def written_text(source: SourceFile, node: ast.expr, left: int) -> str:
    """`node`'s source text with the parentheses written around it from `left` on, whitespace runs collapsed."""
    text = source.text
    start, end = source.span(node)
    comments = _comments(text)
    while True:
        before, after = _blank_before(text, comments, start - 1, left), _blank_after(text, comments, end)
        if before < left or text[before] != "(" or after >= len(text) or text[after] != ")":
            return collapsed(text[start:end])
        start, end = before, after + 1


def access_receiver(source: SourceFile, access: ast.Attribute) -> str:
    """The receiver of `access` as written."""
    return written_text(source, access.value, source.span(access)[0])


def object_text(source: SourceFile, found: FormCall) -> str:
    """The object of a string-named access as written."""
    assert found.obj is not None
    call = found.call
    index = next((i for i, a in enumerate(call.args) if a is found.obj), None) if isinstance(call, ast.Call) else None
    if not isinstance(call, ast.Call) or index is None:
        return written_text(source, found.obj, source.span(call)[0])
    after = source.span(call.args[index - 1])[1] if index else source.span(call.func)[1]
    return written_text(source, found.obj, source.text.index("," if index else "(", after) + 1)


def receiver_text(source: SourceFile, node: ast.expr) -> str:
    return _SPACE.sub(" ", source.segment(node))


def site_text(source: SourceFile, access: ast.expr, obj: ast.expr, name: str) -> str:
    """A string-named access as a finding prints it: `CALLEE(OBJECT, 'NAME')`, with `, …` when the call passes more;
    a field-name read as written; each run of whitespace collapsed and the member in single quotes."""
    if isinstance(access, ast.Call) and any(a is obj for a in access.args):
        more = ", …" if len(access.args) + len(access.keywords) > 2 else ""
        return f"{receiver_text(source, access.func)}({receiver_text(source, obj)}, {name!r}{more})"
    start, end = source.span(access)
    constants = (n for n in ast.walk(access) if isinstance(n, ast.Constant))
    member = next((n for n in constants if (found := plain_literal(source, n)) is not None and found[1] == name), None)
    if member is None:
        return _SPACE.sub(" ", source.text[start:end])
    at, until = source.span(member)
    return _SPACE.sub(" ", source.text[start:at]) + repr(name) + _SPACE.sub(" ", source.text[until:end])


def _calls(source: SourceFile) -> Iterator[ast.Call]:
    if source.tree is not None:
        yield from (n for n in source.nodes if isinstance(n, ast.Call))
