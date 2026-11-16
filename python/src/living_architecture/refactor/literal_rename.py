"""A rename of a `Literal` member: the strings the checker types by that literal type, found by probing the checker
with the member replaced by a sentinel; every other equal string is listed unless another literal type holds it."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Callable
from pathlib import Path

from rope.base.project import Project
from typing_extensions import override

from living_architecture.contract import literal_value_forbidden, message
from living_architecture.lang import Diagnostic, LanguageServer, reverse_closure
from living_architecture.refactor.keyed import TypeFacts
from living_architecture.refactor.locators import RefactorError
from living_architecture.refactor.member_scan import TextProbe
from living_architecture.refactor.mentions import docstrings
from living_architecture.refactor.occurrence_index import RunIndex
from living_architecture.refactor.outcomes import Finding, Outcome, file_outcome
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.rename_union import MapRename, RenameOptions, Session
from living_architecture.refactor.routing import language_files, stub_files
from living_architecture.refactor.symbol_path import LocatorError, names_literal
from living_architecture.refactor.text_edits import TextEdit
from living_architecture.refactor.timings import timed

SENTINEL = "__la_probe_sentinel__"
_QUOTE = re.compile(r"[rRuU]?('''|\"\"\"|'|\")")
_REVEAL = "reveal_type("
_EQUALITY = (ast.Eq, ast.NotEq, ast.Is, ast.IsNot)
_DISPLAYS = (ast.List, ast.Tuple, ast.Set, ast.Dict)

Key = tuple[str, int, int]


def literal_member_at(source: SourceFile, offset: int) -> ast.Constant | None:
    """The string inside a `Literal[...]` subscript whose span holds `offset`."""
    if source.tree is None:
        return None
    literals = (n for n in source.nodes if isinstance(n, ast.Subscript) and names_literal(n.value))
    strings = (i for n in literals for i in ast.walk(n.slice) if isinstance(i, ast.Constant) and isinstance(i.value, str))
    return next((i for i in strings if source.span(i)[0] <= offset < source.span(i)[1]), None)


def _in_literal_type(parents: dict[ast.AST, ast.AST], node: ast.AST) -> bool:
    """`node` is a member of a `Literal[...]` type."""
    up = parents.get(node)
    while up is not None:
        if isinstance(up, ast.Subscript) and names_literal(up.value):
            return True
        up = parents.get(up)
    return False


def check_value(value: str) -> None:
    """`LocatorError` (exit 2) for a new value a string literal cannot hold unescaped."""
    if any(part in value for part in literal_value_forbidden()):
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
        if quote is not None and _one_token(segment):
            start, end = self.span[0] + quote.end(), self.span[1] - len(quote.group(1))
            if start <= end:
                self.inner = (start, end)

    def on(self, span: tuple[int, int]) -> bool:
        """`span` is this literal or the display holding it."""
        return span == self.span or span == self.display


def _one_token(segment: str) -> bool:
    """`segment` is a single string token, not an implicit concatenation."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(f"({segment})").readline))
    except (tokenize.TokenError, SyntaxError):
        return False
    return sum(t.type == tokenize.STRING for t in tokens) == 1


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
        return _compared(parent, node)
    if isinstance(parent, ast.MatchValue):
        return _match_subject(parents, parent)
    return None


def _compared(compare: ast.Compare, node: ast.AST) -> ast.expr | None:
    """The operand `node` is tested for equality or identity with, left side first."""
    operands = [compare.left, *compare.comparators]
    i = next(k for k, o in enumerate(operands) if o is node)
    if i > 0 and isinstance(compare.ops[i - 1], _EQUALITY):
        return operands[i - 1]
    if i + 1 < len(operands) and isinstance(compare.ops[i], _EQUALITY):
        return operands[i + 1]
    return None


def _match_subject(parents: dict[ast.AST, ast.AST], pattern: ast.MatchValue) -> ast.expr | None:
    up: ast.AST | None = parents.get(pattern)
    while isinstance(up, (ast.MatchOr, ast.match_case)):
        up = parents.get(up)
    return up.subject if isinstance(up, ast.Match) else None


def _reveal_anchors(probe: TextProbe | None, subs: list[tuple[int, int, str, int]]) -> dict[int, int]:
    """Each `reveal_type` substitution's start in the probe text, mapped to its operand's start in the file."""
    if probe is None:
        return {}
    return {probe.accesses[i]: s for i, (s, _, text, _) in enumerate(subs) if text.startswith(_REVEAL)}


class LiteralRename(MapRename):
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

    @override
    def header(self) -> str:
        return message("refactor.rename-header", old=self.old, new=self.new)

    @override
    def stand_in_findings(self) -> list[Finding]:
        return []

    @override
    def check_conflicts(self, edits: list[TextEdit]) -> None:
        """A literal member has no name to collide with."""

    @override
    def seed(self, facts: TypeFacts) -> None:
        """The member is located by its literal; nothing to seed."""

    @override
    def finish(self) -> None:
        """Every rule of a literal rename asks the checker."""

    @override
    def prepare(self, index: RunIndex) -> None:
        """Every string literal whose value is the member's; the candidates are their files and the project sources
        whose imports reach the member's file."""
        with timed("literal-scan"):
            modules = self._sources(language_files(self.root, "python"))
            holding = {rel for rel, source in modules.items() if self._scan(rel, source)}
            stubs = self._sources(stub_files(self.root, "python", ".pyi"))
            trees = {rel: source.tree if source.tree is not None else source.text for rel, source in {**modules, **stubs}.items()}
            self.candidates = sorted((reverse_closure(self.rel, trees) & set(modules)) | holding)
        if self._member is None or self._member.inner is None:
            raise RefactorError(message("refactor.cannot-rename"))

    def _sources(self, paths: list[Path]) -> dict[str, SourceFile]:
        """Each readable file of `paths` by its project-relative path, in path order."""
        out: dict[str, SourceFile] = {}
        for path in paths:
            rel = path.relative_to(self.root).as_posix()
            try:
                out[rel] = self.snapshot.source(rel)
            except (OSError, UnicodeDecodeError, LookupError):
                continue
        return out

    def _scan(self, rel: str, source: SourceFile) -> bool:
        """Record the member and the other equal strings of `source`; whether it holds one."""
        sites = self._equal_strings(rel, source)
        for site in sites:
            if rel == self.rel and site.span == source.span(self.node):
                self._member = site
            else:
                self._sites.append(site)
        return bool(sites)

    def _equal_strings(self, rel: str, source: SourceFile) -> list[_Site]:
        """Each string literal of `source` whose value is the member's, docstrings and f-string parts not."""
        if source.tree is None:
            return []
        parents = _parents(source.tree)
        skipped = {id(d) for d in docstrings(source.tree)}
        skipped |= {id(v) for n in source.nodes if isinstance(n, ast.JoinedStr) for v in n.values}
        out: list[_Site] = []
        for node in source.nodes:
            if isinstance(node, ast.Constant) and node.value == self.old and id(node) not in skipped:
                parent = parents.get(node)
                display = source.span(parent) if isinstance(parent, _DISPLAYS) else None  # pyright: ignore[reportArgumentType]
                out.append(_Site(rel, source, node, display, _in_literal_type(parents, node)))
        return out

    def _diagnostics(self, server: LanguageServer, rel: str, probe: TextProbe | None) -> list[tuple[Diagnostic, int]]:
        """Each diagnostic with its span in the file's own offsets, and its start in the probe text."""
        found = server.diagnostics(self.root / rel)
        if probe is None:
            return [(d, d.span.start) for d in found]
        return [(d.model_copy(update={"span": probe.original(d.span)}), d.span.start) for d in found]

    def _errors(self, diagnostics: list[tuple[Diagnostic, int]]) -> set[Key]:
        return {(d.code, d.span.start, d.span.end) for d, _ in diagnostics if d.severity in (1, 2)}

    def _pull_before(self, server: LanguageServer, before: dict[str, set[Key]],
                     result: dict[str, tuple[TextProbe | None, list[tuple[Diagnostic, int]]]]) -> None:
        """Once per file, after a round reverted: the pre-probe errors of each file the round shows an error."""
        for rel, (_, diagnostics) in result.items():
            if rel not in before and any(d.severity in (1, 2) for d, _ in diagnostics):
                before[rel] = self._errors(self._diagnostics(server, rel, None))

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

    @override
    def rules(self, index: RunIndex, facts: TypeFacts) -> None:
        """The probe's rounds on the run's language server: candidates, the verification, then the remaining equal
        strings."""
        if self._member is None or self._member.inner is None:
            return
        server = index.opened(self.root / rel for rel in self.candidates)
        with timed("literal-probe"):
            before: dict[str, set[Key]] = {}
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
            start = self._reveal_operand(site, substitutions.setdefault(site.rel, []))
            if start is not None:
                wraps.setdefault(site.rel, {}).setdefault(start, []).append(site)
        pulled = sorted({s.rel for s in self._sites})
        result = self._round(server, substitutions, pulled)
        self._pull_before(server, before, result)
        typed: list[_Site] = []
        for rel, (probe, diagnostics) in result.items():
            anchors = _reveal_anchors(probe, substitutions.get(rel, []))
            revealed = {anchors[at] for d, at in diagnostics if d.severity == 3 and SENTINEL in d.message and at in anchors}
            errors = {(d.span.start, d.span.end) for d, _ in diagnostics
                      if d.severity in (1, 2) and (d.code, d.span.start, d.span.end) not in before.get(rel, set())}
            for site in (s for s in self._sites if s.rel == rel):
                hit = any(site.on(span) for span in errors) or any(site in wraps.get(rel, {}).get(o, []) for o in revealed)
                if hit and site.inner is not None:
                    typed.append(site)
        return typed

    def _reveal_operand(self, site: _Site, subs: list[tuple[int, int, str, int]]) -> int | None:
        """The start of the operand `site` is compared with, wrapped in `reveal_type` in `subs` once; None when it
        has none or it overlaps another substitution."""
        source = self.snapshot.source(site.rel)
        assert source.tree is not None
        operand = _operand(_parents(source.tree), site.node)
        if operand is None:
            return None
        start, end = source.span(operand)
        spans = {(s, e) for s, e, _, _ in subs}
        if (start, end) in spans:
            return start
        if any(s < end and start < e for s, e in spans):
            return None
        subs.append((start, end, f"{_REVEAL}{source.text[start:end]})", len(_REVEAL)))
        return start

    def _verify(self, server: LanguageServer, before: dict[str, set[Key]], typed: list[_Site]) -> None:
        """With the member and every rewritten literal set to the sentinel, each new error is a blind spot."""
        assert self._member is not None
        result = self._round(server, self._sentinels([self._member, *typed]), self.candidates)
        self._pull_before(server, before, result)
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
        self._pull_before(server, before, result)
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
            finding = Finding(path=site.rel, line=line, col=site.span[0], end=site.span[1], text=text)
            self._file(Outcome(kind="leftover", rel=site.rel, span=site.span, finding=finding))

    def _file(self, outcome: Outcome) -> None:
        file_outcome(outcome, edits=self.edits, blindspots=self.blindspots, leftovers=self.leftovers)

