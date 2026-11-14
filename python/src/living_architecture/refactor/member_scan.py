"""The receivers of a member name basedpyright cannot type, and the calls that name a member by a string: one scan
behind `dr-compliance --attr` and a rename's blind spots and string rewrites."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import language
from living_architecture.lang import LanguageServer, Span
from living_architecture.refactor.python_source import SourceFile

_HOVER = re.compile(r"\([\w ]+\) [\w.]+: (.*)", re.DOTALL)
_SPACE = re.compile(r"\s+")


class StringForm(BaseModel):
    """A call naming a member by a string (`string_member_calls` in the language registry)."""

    model_config = ConfigDict(frozen=True)

    call: str
    module: str
    qualname: str
    syntax: str
    object: int | None = None
    member: int | None = None
    target: int | None = None


FORMS = tuple(StringForm.model_validate(f) for f in language("python")["string_member_calls"])


class Blindspot(BaseModel):
    """A receiver of the member name typed `Unknown` or `Any`, at an access or a string-member call."""

    model_config = ConfigDict(frozen=True)

    line: int
    col: int
    receiver: str
    kind: str


class FormCall(BaseModel):
    """A string-member call whose string names the member: its literal's inner span, and for a member form the
    object; `forms` is what the callee resolves to (None: it does not resolve)."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    call: ast.Call
    literal: tuple[int, int]
    text: str
    obj: ast.expr | None
    forms: tuple[StringForm, ...] | None


def hover_type(hover: str | None) -> str | None:
    """`Unknown` or `Any` when a hover's declared type is, or is a union holding, either; else None."""
    if hover is None or (m := _HOVER.match(hover.split("\n\n")[0])) is None:
        return None
    members: list[str] = []
    depth, start, text = 0, 0, m.group(1)
    for i, char in enumerate(text):
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        elif depth == 0 and text.startswith(" | ", i):
            members.append(text[start:i])
            start = i + 3
    members = [t.strip() for t in [*members, text[start:]]]
    return next((kind for kind in ("Unknown", "Any") if kind in members), None)


def _access_kind(server: LanguageServer, path: Path, source: SourceFile, node: ast.Attribute) -> str | None:
    """`Unknown` or `Any` in the type of `node`'s receiver: hovered when a name or attribute, else read from the access
    when no declaration of the member is itself typed so."""
    receiver = node.value
    if isinstance(receiver, (ast.Name, ast.Attribute)):
        span = source.name_span(receiver)
        return hover_type(server.hover(path, span[0])) if span else None
    span = source.name_span(node)
    if span is None or (kind := hover_type(server.hover(path, span[0]))) is None:
        return None
    declared = (hover_type(server.hover(d.path, d.start)) for d in server.definition(path, span[0]))
    return None if any(declared) else kind


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
    for module in {f.module for f in FORMS}:
        stem = module.replace(".", "/")
        if any(posix.endswith(f"/{stem}{tail}") for tail in (".py", ".pyi", "/__init__.py", "/__init__.pyi")):
            return module
    return None


class FormResolver:
    """Which registry forms a callee's declarations are."""

    def __init__(self, server: LanguageServer, load: Callable[[Path], SourceFile | None]) -> None:
        self.server = server
        self._load = load
        self._classes: dict[Path, list[ast.ClassDef]] = {}

    def _qualname(self, span: Span) -> str | None:
        source = self._load(span.path)
        if source is None or source.tree is None:
            return None
        if span.path not in self._classes:
            self._classes[span.path] = [n for n in ast.walk(source.tree) if isinstance(n, ast.ClassDef)]
        line = source.line(span.start)
        chain = sorted(
            (c for c in self._classes[span.path] if c.lineno <= line <= (c.end_lineno or c.lineno)), key=lambda c: c.lineno
        )
        return ".".join([*(c.name for c in chain), source.text[span.start : span.end]])

    def forms(self, path: Path, source: SourceFile, call: ast.Call) -> tuple[StringForm, ...] | None:
        """The forms the callee resolves to; None when basedpyright finds no declaration of it."""
        span = source.name_span(call.func)
        if span is None:
            return ()
        definitions = self.server.definition(path, span[0])
        if not definitions:
            return None
        found: set[StringForm] = set()
        for d in definitions:
            module = _module_of(d.path)
            if module is not None and (qualname := self._qualname(d)) is not None:
                found |= {f for f in FORMS if (f.module, f.qualname) == (module, qualname)}
        return tuple(sorted(found, key=lambda f: f.call))


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


def _target_literal(source: SourceFile, call: ast.Call, form: StringForm, name: str) -> tuple[tuple[int, int], str] | None:
    """The dotted target literal of `call` read as target form `form` when a segment is `name`."""
    if form.target is None or len(call.args) <= form.target or any(isinstance(a, ast.Starred) for a in call.args[: form.target + 1]):
        return None
    literal = plain_literal(source, call.args[form.target])
    return literal if literal is not None and name in literal[1].split(".") else None


class MemberScan:
    """The scan of member name `name` over files opened in `server`."""

    def __init__(self, server: LanguageServer, name: str, load: Callable[[Path], SourceFile | None]) -> None:
        self.server = server
        self.name = name
        self.callees = FormResolver(server, load)

    def accesses(self, path: Path, source: SourceFile) -> Iterator[Blindspot]:
        """`x.NAME` accesses whose receiver is typed `Unknown` or `Any`."""
        if source.tree is None:
            return
        for node in ast.walk(source.tree):
            if not (isinstance(node, ast.Attribute) and node.attr == self.name):
                continue
            if (kind := _access_kind(self.server, path, source, node)) is not None:
                yield Blindspot(line=node.lineno, col=node.col_offset, receiver=_receiver(source, node.value), kind=kind)

    def member_calls(self, path: Path, source: SourceFile) -> list[FormCall]:
        """Calls with a member form's syntax whose member literal is NAME, with what their callee resolves to."""
        out: list[FormCall] = []
        for call in _calls(source):
            callee = _dotted(call.func)
            matching = [f for f in FORMS if callee is not None and _syntax(callee, f)]
            found = next(((f, m) for f in matching if (m := _member_literal(source, call, f, self.name)) is not None), None)
            if found is None:
                continue
            forms = self.callees.forms(path, source, call)
            member = [f for f in forms if _member_literal(source, call, f, self.name)] if forms is not None else None
            if member is not None and not member:
                continue
            (literal, obj) = found[1]
            out.append(FormCall(call=call, literal=literal, text=self.name, obj=obj,
                                forms=tuple(member) if member is not None else None))
        return out

    def target_calls(self, path: Path, source: SourceFile) -> list[FormCall]:
        """Calls resolving to a target form whose dotted target has a segment NAME."""
        out: list[FormCall] = []
        for call in _calls(source):
            callee = _dotted(call.func)
            matching = [f for f in FORMS if f.target is not None and callee is not None and _syntax(callee, f)]
            found = next(((f, t) for f in matching if (t := _target_literal(source, call, f, self.name)) is not None), None)
            if found is None:
                continue
            forms = self.callees.forms(path, source, call)
            resolved = tuple(f for f in forms or () if f.target is not None)
            if resolved:
                out.append(FormCall(call=call, literal=found[1][0], text=found[1][1], obj=None, forms=resolved))
        return out

    def object_kind(self, path: Path, source: SourceFile, found: FormCall) -> str | None:
        """`Unknown` or `Any` for a member call's object, Unknown for an unresolved callee; None when typed."""
        if found.forms is None:
            return "Unknown"
        obj = found.obj
        if isinstance(obj, (ast.Name, ast.Attribute)):
            span = source.name_span(obj)
            return hover_type(self.server.hover(path, span[0])) if span else None
        return None

    def probe(self, path: Path, source: SourceFile, calls: list[FormCall]) -> list[tuple[str | None, list[Span]]]:
        """For each resolved member call, its object's kind when not a name or attribute, and the declarations
        `obj.NAME` lands on: read from the file with each literal replaced by `(obj).NAME`, then restored."""
        pieces: list[str] = []
        offsets: list[int] = []
        pos = 0
        for found in calls:
            assert found.obj is not None
            start, end = found.literal
            prefix = f"({_SPACE.sub(' ', source.segment(found.obj))})."
            pieces += [source.text[pos : start - 1], prefix]
            offsets.append(sum(map(len, pieces)))
            pieces.append(self.name)
            pos = end + 1
        probe = "".join(pieces) + source.text[pos:]
        self.server.change(path, probe)
        try:
            probed = SourceFile(path, probe)
            out: list[tuple[str | None, list[Span]]] = []
            for found, offset in zip(calls, offsets, strict=True):
                access = _access_at(probed, offset)
                kind = None
                if access is not None and not isinstance(found.obj, (ast.Name, ast.Attribute)):
                    kind = _access_kind(self.server, path, probed, access)
                out.append((kind, self.server.definition(path, offset)))
            return out
        finally:
            self.server.change(path, source.text)

    def blindspots(self, path: Path, source: SourceFile) -> list[Blindspot]:
        """Every blind spot of NAME in the file: untyped access receivers and string-member objects or callees."""
        found = list(self.accesses(path, source))
        calls = self.member_calls(path, source)
        probed = [c for c in calls if c.forms is not None and not isinstance(c.obj, (ast.Name, ast.Attribute))]
        kinds = dict(zip(map(id, probed), (k for k, _ in self.probe(path, source, probed)), strict=True)) if probed else {}
        for call in calls:
            kind = kinds.get(id(call)) if id(call) in kinds else self.object_kind(path, source, call)
            if kind is not None:
                assert call.obj is not None
                found.append(Blindspot(line=call.call.lineno, col=call.call.col_offset,
                                       receiver=_receiver(source, call.obj), kind=kind))
        return found


def _receiver(source: SourceFile, node: ast.expr) -> str:
    return _SPACE.sub(" ", source.segment(node))


def _calls(source: SourceFile) -> Iterator[ast.Call]:
    if source.tree is not None:
        yield from (n for n in ast.walk(source.tree) if isinstance(n, ast.Call))


def _access_at(source: SourceFile, offset: int) -> ast.Attribute | None:
    """The attribute access whose member name starts at `offset`."""
    if source.tree is None:
        return None
    return next(
        (n for n in ast.walk(source.tree) if isinstance(n, ast.Attribute) and (s := source.name_span(n)) and s[0] == offset),
        None,
    )
