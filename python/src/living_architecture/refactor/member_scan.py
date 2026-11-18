"""The receivers of a member name basedpyright cannot type, and the calls that name a member by a string: one scan
over the run's occurrence index behind `dr-compliance --attr` and a rename's blind spots and string rewrites."""

from __future__ import annotations

import ast
import bisect
import functools
import io
import re
import tokenize
from collections.abc import Callable, Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import language
from living_architecture.lang import FactQuery, Span
from living_architecture.refactor.occurrence_index import RunIndex
from living_architecture.refactor.python_source import SourceFile

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
    """A receiver of the member name typed `Unknown`, `Any` or `Never`, at an access or a string-member call."""

    model_config = ConfigDict(frozen=True)

    line: int
    col: int
    receiver: str
    kind: str
    literal: tuple[int, int] | None = None


class FormCall(BaseModel):
    """A string-member call whose string names the member: its literal's inner span, and for a member form the
    object; `forms` is what the callee resolves to (None: it does not resolve)."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    call: ast.Call
    literal: tuple[int, int]
    text: str
    obj: ast.expr | None
    forms: tuple[StringForm, ...] | None


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

    def forms(self, path: Path, source: SourceFile, call: ast.Call) -> tuple[StringForm, ...] | None:
        """The forms the callee resolves to; None when basedpyright finds no declaration of it, or declarations of
        which some are forms and some are not (ambiguous)."""
        span = source.name_span(call.func)
        if span is None:
            return ()
        definitions = self.index.definition(path, span[0])
        if not definitions:
            return None
        found: dict[str, StringForm] = {}
        others = 0
        for d in definitions:
            module = _module_of(d.path)
            qualname = self._qualname(d) if module is not None else None
            matched = {f.call: f for f in FORMS if (f.module, f.qualname) == (module, qualname)}
            found |= matched
            others += not matched
        if found and others:
            return None
        return tuple(found[call] for call in sorted(found))


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
        out: list[FormCall] = []
        for call in _calls(source):
            callee = _dotted(call.func)
            syntactic = [f for f in FORMS if callee is not None and _syntax(callee, f)]
            found = next(((f, m) for f in syntactic or FORMS if (m := _member_literal(source, call, f, self.name)) is not None), None)
            if found is None:
                continue
            forms = self.callees.forms(path, source, call)
            member = [f for f in forms if _member_literal(source, call, f, self.name)] if forms is not None else None
            if (member is not None and not member) or (member is None and not syntactic):
                continue
            (literal, obj) = found[1]
            out.append(FormCall(call=call, literal=literal, text=self.name, obj=obj,
                                forms=tuple(member) if member is not None else None))
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
        if found.forms is None:
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
        probed = [c for c in calls if c.forms is not None and not isinstance(c.obj, (ast.Name, ast.Attribute))]
        kinds = dict(zip(map(id, probed), (k for k, _ in self.probe(path, probed)), strict=True)) if probed else {}
        for call in calls:
            kind = kinds.get(id(call)) if id(call) in kinds else self.object_kind(path, source, call)
            if kind is not None:
                assert call.obj is not None
                found.append(Blindspot(line=call.call.lineno, col=call.call.col_offset,
                                       receiver=object_text(source, call), kind=kind, literal=call.literal))
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
    """`source` with each member call's literal replaced by `(obj).NAME` (NAME the call's own unless `name` is given);
    `accesses[i]` is where call `i`'s access names NAME."""

    def __init__(self, source: SourceFile, calls: list[FormCall], name: str | None = None) -> None:
        substitutions: list[tuple[int, int, str, int]] = []
        for call in calls:
            assert call.obj is not None
            start, end = call.literal
            receiver = f"({source.segment(call.obj)})."
            substitutions.append((start - 1, end + 1, receiver + (name or call.text), len(receiver)))
        super().__init__(source, substitutions)


def probe_round(index: RunIndex, files: list[tuple[Path, SourceFile]], names: list[str],
                load: Callable[[Path], SourceFile | None]) -> None:
    """One export over every file holding resolved member calls naming one of `names`: each file opened as its probe
    text, the declarations and receiver verdict of each probe access recorded by its call's literal."""
    probes: dict[Path, tuple[Probe, list[FormCall]]] = {}
    for path, source in files:
        calls = [c for name in names if name in source.text
                 for c in MemberScan(index, name, load).member_calls(path, source) if c.forms is not None]
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
    comments = _comments(text) if text.find("#", left) != -1 else ()
    while True:
        before, after = _blank_before(text, comments, start - 1, left), _blank_after(text, comments, end)
        if before < left or text[before] != "(" or after >= len(text) or text[after] != ")":
            return collapsed(text[start:end])
        start, end = before, after + 1


def access_receiver(source: SourceFile, access: ast.Attribute) -> str:
    """The receiver of `access` as written."""
    return written_text(source, access.value, source.span(access)[0])


def object_text(source: SourceFile, found: FormCall) -> str:
    """The object argument of a string-member call as written."""
    assert found.obj is not None
    index = next(i for i, a in enumerate(found.call.args) if a is found.obj)
    after = source.span(found.call.args[index - 1])[1] if index else source.span(found.call.func)[1]
    return written_text(source, found.obj, source.text.index("," if index else "(", after) + 1)


def _calls(source: SourceFile) -> Iterator[ast.Call]:
    if source.tree is not None:
        yield from (n for n in source.nodes if isinstance(n, ast.Call))
