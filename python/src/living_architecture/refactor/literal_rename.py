"""A rename of a `Literal` member: the strings the checker types by that literal type, found by probing the checker
with the member replaced by a sentinel; every other equal string is listed unless another literal type holds it."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable

from rope.base.project import Project

from living_architecture.contract import message
from living_architecture.lang import Diagnostic, LanguageServer
from living_architecture.refactor.keyed import TypeFacts
from living_architecture.refactor.member_scan import TextProbe
from living_architecture.refactor.mentions import docstrings
from living_architecture.refactor.outcomes import Finding, Outcome, file_outcome
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.rename_union import RenameOptions, Session
from living_architecture.refactor.routing import language_files
from living_architecture.refactor.symbol_path import LocatorError
from living_architecture.refactor.text_edits import TextEdit

SENTINEL = "__la_probe_sentinel__"
_QUOTE = re.compile(r"[rRuU]?('''|\"\"\"|'|\")")
_REVEAL = "reveal_type("
_EQUALITY = (ast.Eq, ast.NotEq, ast.Is, ast.IsNot)
_DISPLAYS = (ast.List, ast.Tuple, ast.Set, ast.Dict)
_FORBIDDEN = re.compile(r"['\"\\\r\n]")

Key = tuple[str, int, int]


def literal_member_at(source: SourceFile, offset: int) -> ast.Constant | None:
    """The string inside a `Literal[...]` subscript whose span holds `offset`."""
    if source.tree is None:
        return None
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Subscript) and _names_literal(node.value):
            for inner in ast.walk(node.slice):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    start, end = source.span(inner)
                    if start <= offset < end:
                        return inner
    return None


def _in_literal_type(parents: dict[ast.AST, ast.AST], node: ast.AST) -> bool:
    """`node` is a member of a `Literal[...]` type."""
    up = parents.get(node)
    while up is not None:
        if isinstance(up, ast.Subscript) and _names_literal(up.value):
            return True
        up = parents.get(up)
    return False


def _names_literal(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "Literal") or (isinstance(node, ast.Attribute) and node.attr == "Literal")


def check_value(value: str) -> None:
    """`LocatorError` (exit 2) for a new value a string literal cannot hold unescaped."""
    if _FORBIDDEN.search(value):
        raise LocatorError(message("refactor.literal-value", value=value))


class _Site:
    """A string literal whose value is the member's: its file, node, span and the span of its value."""

    def __init__(self, rel: str, source: SourceFile, node: ast.Constant, display: tuple[int, int] | None,
                 in_type: bool) -> None:
        self.rel = rel
        self.in_type = in_type
        self.node = node
        self.span = source.span(node)
        self.display = display
        segment = source.text[self.span[0] : self.span[1]]
        quote = _QUOTE.match(segment)
        self.inner: tuple[int, int] | None = None
        if quote is not None:
            start, end = self.span[0] + quote.end(), self.span[1] - len(quote.group(1))
            if start <= end:
                self.inner = (start, end)

    def on(self, span: tuple[int, int]) -> bool:
        """`span` is this literal or the display holding it."""
        return span == self.span or span == self.display


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def _operand(parents: dict[ast.AST, ast.AST], node: ast.AST) -> ast.expr | None:
    """The expression a literal is compared with (`==`, `!=`, `is`, `is not`), tested for (`in`), or matched against."""
    parent = parents.get(node)
    if isinstance(parent, (ast.Tuple, ast.List, ast.Set)) and isinstance(compare := parents.get(parent), ast.Compare):
        operands = [compare.left, *compare.comparators]
        i = next((k for k, o in enumerate(operands) if o is parent), 0)
        if i > 0 and isinstance(compare.ops[i - 1], (ast.In, ast.NotIn)):
            return operands[i - 1]
    if isinstance(parent, ast.Compare):
        operands = [parent.left, *parent.comparators]
        i = next(k for k, o in enumerate(operands) if o is node)
        if i > 0 and isinstance(parent.ops[i - 1], _EQUALITY):
            return operands[i - 1]
        if i + 1 < len(operands) and isinstance(parent.ops[i], _EQUALITY):
            return operands[i + 1]
    if isinstance(parent, ast.MatchValue):
        up: ast.AST | None = parents.get(parent)
        while isinstance(up, (ast.MatchOr, ast.match_case)):
            up = parents.get(up)
        if isinstance(up, ast.Match):
            return up.subject
    return None


class LiteralRename:
    """Rename `Literal` member `node` of file `rel` to `new`, as a rename map's entry."""

    def __init__(self, session: Session, rel: str, node: ast.Constant, new: str, options: RenameOptions) -> None:
        self.session = session
        self.project: Project = session.project
        self.root = session.root
        self.snapshot = session.snapshot
        self.options = options
        self.rel = rel
        self.node = node
        self.old = str(node.value)
        self.new = new
        self.member = False
        self.check_names = False
        self.seeds: set[tuple[str, int]] = set()
        self.candidates: list[str] = []
        self.matched_sites: set[str] = set()
        self.is_renamed: Callable[[tuple[str, int]], bool] = lambda _: False
        self.renamed_names: set[str] = set()
        self.edits: list[TextEdit] = []
        self.blindspots: list[Finding] = []
        self.leftovers: list[Finding] = []
        self._sites: list[_Site] = []
        self._member: _Site | None = None

    def header(self) -> str:
        return f"Renaming <{self.old}> to <{self.new}>:"

    def stand_in_findings(self) -> list[Finding]:
        return []

    def check_conflicts(self, edits: list[TextEdit]) -> None:
        """A literal member has no name to collide with."""

    def seed(self, facts: TypeFacts) -> None:
        """The member is located by its literal; nothing to seed."""

    def finish(self) -> None:
        """Every rule of a literal rename asks the checker."""

    def prepare(self) -> None:
        """Every project source, and every string literal whose value is the member's."""
        for path in language_files(self.root, "python"):
            rel = path.relative_to(self.root).as_posix()
            try:
                source = self.snapshot.source(rel)
            except (OSError, UnicodeDecodeError, LookupError):
                continue
            self.candidates.append(rel)
            if source.tree is None or self.old not in source.text:
                continue
            parents = _parents(source.tree)
            skipped = {id(d) for d in docstrings(source.tree)}
            skipped |= {id(v) for n in ast.walk(source.tree) if isinstance(n, ast.JoinedStr) for v in n.values}
            for node in ast.walk(source.tree):
                if isinstance(node, ast.Constant) and node.value == self.old and id(node) not in skipped:
                    parent = parents.get(node)
                    display = source.span(parent) if isinstance(parent, _DISPLAYS) else None  # pyright: ignore[reportArgumentType]
                    site = _Site(rel, source, node, display, _in_literal_type(parents, node))
                    if rel == self.rel and site.span == source.span(self.node):
                        self._member = site
                    else:
                        self._sites.append(site)
        self.candidates.sort()

    def _diagnostics(self, server: LanguageServer, rel: str, probe: TextProbe | None) -> list[tuple[Diagnostic, int]]:
        """Each diagnostic with its span in the file's own offsets, and its start in the probe text."""
        found = server.diagnostics(self.root / rel)
        if probe is None:
            return [(d, d.span.start) for d in found]
        return [(d.model_copy(update={"span": probe.original(d.span)}), d.span.start) for d in found]

    def _errors(self, diagnostics: list[tuple[Diagnostic, int]]) -> set[Key]:
        return {(d.code, d.span.start, d.span.end) for d, _ in diagnostics if d.severity in (1, 2)}

    def _round(self, server: LanguageServer, substitutions: dict[str, list[tuple[int, int, str, int]]],
               pulled: list[str]) -> dict[str, tuple[TextProbe | None, list[tuple[Diagnostic, int]]]]:
        """The diagnostics of `pulled` with `substitutions` made, their spans in the files' own offsets."""
        probes: dict[str, TextProbe] = {}
        for rel, subs in substitutions.items():
            probes[rel] = TextProbe(self.snapshot.source(rel), subs)
            server.change(self.root / rel, probes[rel].text)
        try:
            return {rel: (probes.get(rel), self._diagnostics(server, rel, probes.get(rel))) for rel in pulled}
        finally:
            for rel in probes:
                server.change(self.root / rel, self.snapshot.text(rel))

    def _sentinels(self, sites: list[_Site]) -> dict[str, list[tuple[int, int, str, int]]]:
        out: dict[str, list[tuple[int, int, str, int]]] = {}
        for site in sites:
            if site.inner is not None:
                out.setdefault(site.rel, []).append((*site.inner, SENTINEL, 0))
        return out

    def rules(self, server: LanguageServer, facts: TypeFacts) -> None:
        """The probe's rounds: candidates, the verification, then the remaining equal strings."""
        if self._member is None or self._member.inner is None:
            return
        before = {rel: self._errors(self._diagnostics(server, rel, None)) for rel in self.candidates}
        typed = self._typed(server, before)
        self._file(Outcome(kind="rewrite", rel=self.rel, span=self._member.span, edits=(self._edit(self._member),)))
        for site in typed:
            self._file(Outcome(kind="rewrite", rel=site.rel, span=site.span, edits=(self._edit(site),)))
        self._verify(server, before, typed)
        self._others(server, before, [s for s in self._sites if s not in typed])

    def _edit(self, site: _Site) -> TextEdit:
        assert site.inner is not None
        return TextEdit(path=site.rel, start=site.inner[0], end=site.inner[1], new_text=self.new)

    def _typed(self, server: LanguageServer, before: dict[str, set[Key]]) -> list[_Site]:
        """The literals the checker types by the member: a new error on the literal or its display with the member
        set to the sentinel, or an operand whose revealed type holds the sentinel."""
        assert self._member is not None
        substitutions = self._sentinels([self._member])
        wraps: dict[str, dict[int, list[_Site]]] = {}
        for site in self._sites:
            source = self.snapshot.source(site.rel)
            assert source.tree is not None
            operand = _operand(_parents(source.tree), site.node)
            if operand is None:
                continue
            start, end = source.span(operand)
            subs = substitutions.setdefault(site.rel, [])
            if any(s < end and start < e for s, e, _, _ in subs) and (start, end) not in {(s, e) for s, e, _, _ in subs}:
                continue
            if (start, end) not in {(s, e) for s, e, _, _ in subs}:
                subs.append((start, end, f"{_REVEAL}{source.text[start:end]})", len(_REVEAL)))
            wraps.setdefault(site.rel, {}).setdefault(start, []).append(site)
        pulled = sorted({s.rel for s in self._sites})
        result = self._round(server, substitutions, pulled)
        typed: list[_Site] = []
        for rel, (probe, diagnostics) in result.items():
            anchors: dict[int, int] = {}
            if probe is not None:
                for i, (s, _, text, _) in enumerate(substitutions.get(rel, [])):
                    if text.startswith(_REVEAL):
                        anchors[probe.accesses[i]] = s
            revealed = {anchors[at] for d, at in diagnostics if d.severity == 3 and SENTINEL in d.message and at in anchors}
            errors = {(d.span.start, d.span.end) for d, _ in diagnostics
                      if d.severity in (1, 2) and (d.code, d.span.start, d.span.end) not in before.get(rel, set())}
            for site in (s for s in self._sites if s.rel == rel):
                hit = any(site.on(span) for span in errors) or any(site in wraps.get(rel, {}).get(o, []) for o in revealed)
                if hit and site.inner is not None:
                    typed.append(site)
        return typed

    def _verify(self, server: LanguageServer, before: dict[str, set[Key]], typed: list[_Site]) -> None:
        """With the member and every rewritten literal set to the sentinel, each new error is a blind spot."""
        assert self._member is not None
        result = self._round(server, self._sentinels([self._member, *typed]), self.candidates)
        seen: set[tuple[str, int]] = set()
        for rel, (_, diagnostics) in sorted(result.items()):
            source = self.snapshot.source(rel)
            for d, _ in sorted(diagnostics, key=lambda d: d[0].span.start):
                if d.severity not in (1, 2) or (d.code, d.span.start, d.span.end) in before.get(rel, set()):
                    continue
                line = source.line(d.span.start)
                if (rel, line) in seen:
                    continue
                seen.add((rel, line))
                text = message("refactor.literal-unresolved", path=rel, line=line, old=self.old)
                finding = Finding(path=rel, line=line, col=d.span.start, text=text)
                self._file(Outcome(kind="blindspot", rel=rel, span=(d.span.start, d.span.end), finding=finding))

    def _others(self, server: LanguageServer, before: dict[str, set[Key]], others: list[_Site]) -> None:
        """Each other equal string: unrelated where a sentinel in its place draws a new error on it, else listed (a
        member of another `Literal` type always, as a sentinel there changes what the probe asks)."""
        probed = [s for s in others if not s.in_type]
        result = self._round(server, self._sentinels(probed), sorted({s.rel for s in probed})) if probed else {}
        for site in others:
            _, diagnostics = result.get(site.rel, (None, []))
            rejected = not site.in_type and any(
                d.severity in (1, 2) and (d.code, d.span.start, d.span.end) not in before.get(site.rel, set())
                and site.on((d.span.start, d.span.end))
                for d, _ in diagnostics
            )
            if rejected:
                self._file(Outcome(kind="unrelated", rel=site.rel, span=site.span))
                continue
            line = self.snapshot.source(site.rel).line(site.span[0])
            text = message("refactor.leftover", path=site.rel, line=line, where="string", old=self.old)
            finding = Finding(path=site.rel, line=line, col=site.span[0], text=text)
            self._file(Outcome(kind="leftover", rel=site.rel, span=site.span, finding=finding))

    def _file(self, outcome: Outcome) -> None:
        file_outcome(outcome, edits=self.edits, blindspots=self.blindspots, leftovers=self.leftovers)

