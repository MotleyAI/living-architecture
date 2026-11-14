"""`rename --docs`: the old name's mentions in comments, docstrings, strings and prose files, rewritten when
qualified or code-marked, else listed."""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from collections.abc import Callable, Iterator

from pydantic import BaseModel, ConfigDict

from living_architecture.refactor.python_source import SourceFile

_QUALIFIER = re.compile(r"((?:[A-Za-z_]\w*[.#])*[A-Za-z_]\w*)[.#]$")
_PREFIX = re.compile(r"[A-Za-z]*")
_FSTRING_PARTS = {getattr(tokenize, name) for name in ("FSTRING_MIDDLE", "TSTRING_MIDDLE") if hasattr(tokenize, name)}
_FSTRING_STARTS = {getattr(tokenize, name) for name in ("FSTRING_START", "TSTRING_START") if hasattr(tokenize, name)}


class Owner(BaseModel):
    """A renamed declaration's qualifying path (module segments, then classes) and whether a class declares it."""

    model_config = ConfigDict(frozen=True)

    path: tuple[str, ...]
    member: bool


class Mention(BaseModel):
    """An occurrence of the old name: its span, its line and where it is."""

    model_config = ConfigDict(frozen=True)

    start: int
    end: int
    line: int
    where: str
    opens: bool


class MentionRules(BaseModel):
    """What makes a mention rewritable: the renamed declarations' owners, and the simple class names other project
    classes declaring the old name also use."""

    model_config = ConfigDict(frozen=True)

    old: str
    owners: frozenset[Owner]
    colliding: frozenset[str]

    def qualified(self, text: str, start: int) -> bool:
        """`Owner.OLD` with an optional dotted prefix naming the owner's module from its end."""
        m = _QUALIFIER.search(text, max(0, start - 300), start)
        if m is None or m.end() != start or (m.start() > 0 and (text[m.start() - 1].isalnum() or text[m.start() - 1] in "_.#")):
            return False
        segments = re.split(r"[.#]", m.group(1))
        bare = segments[0] if len(segments) == 1 else None
        for owner in self.owners:
            if len(segments) > len(owner.path) or list(owner.path[len(owner.path) - len(segments) :]) != segments:
                continue
            if bare is None or not owner.member or bare not in self.colliding:
                return True
        return False


def _code_marked(text: str, mention: Mention) -> bool:
    """In backticks (optionally followed by `()`), a role or `{@link}` target, or opening its string before `:`,
    `(` or whitespace."""
    before, after = text[max(0, mention.start - 20) : mention.start], text[mention.end : mention.end + 3]
    if before.endswith(("`", "`~", "`!")) and after.startswith(("`", "()`")):
        return True
    if re.search(r"\{@link\s+$", before) and re.match(r"[}\s|]", after):
        return True
    return mention.opens and re.match(r"[:(\s]", after) is not None


Region = tuple[int, int, str, bool]


def mentions(text: str, old: str, regions: Iterator[Region], line: Callable[[int], int]) -> list[Mention]:
    """Occurrences of `old` not adjacent to an identifier character inside each region (start, end, where, whether
    it opens a string literal)."""
    pattern = re.compile(rf"(?<!\w){re.escape(old)}(?!\w)")
    return [
        Mention(start=m.start(), end=m.end(), line=line(m.start()), where=where, opens=opens and m.start() == start)
        for start, end, where, opens in regions
        for m in pattern.finditer(text, start, end)
    ]


def _docstrings(tree: ast.Module | None) -> list[ast.Constant]:
    if tree is None:
        return []
    owners = [tree, *(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef))]
    return [
        o.body[0].value
        for o in owners
        if o.body
        and isinstance(o.body[0], ast.Expr)
        and isinstance(o.body[0].value, ast.Constant)
        and isinstance(o.body[0].value.value, str)
    ]


def _masked_fstring(token: str) -> list[tuple[int, int]]:
    """The literal runs of a whole f-string token (Python before 3.12), relative to the token."""
    runs: list[tuple[int, int]] = []
    depth, start, i = 0, 0, 0
    while i < len(token):
        if token.startswith(("{{", "}}"), i) and depth == 0:
            i += 2
            continue
        if token[i] == "{":
            if depth == 0:
                runs.append((start, i))
            depth += 1
        elif token[i] == "}" and depth:
            depth -= 1
            if depth == 0:
                start = i + 1
        i += 1
    runs.append((start, len(token)))
    return runs


def source_regions(source: SourceFile) -> Iterator[Region]:
    """The comments and string literal contents of a Python file."""
    docstrings = [source.span(d) for d in _docstrings(source.tree)]
    starts = [0, *(i + 1 for i, c in enumerate(source.text) if c == "\n")]
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source.text, newline="").readline))
    except (tokenize.TokenError, SyntaxError):
        return
    previous = None
    for token in tokens:
        offset = starts[token.start[0] - 1] + token.start[1]
        end = starts[token.end[0] - 1] + token.end[1]
        opening = previous in _FSTRING_STARTS
        previous = token.type
        if token.type == tokenize.COMMENT:
            yield offset, end, "comment", False
        elif token.type in _FSTRING_PARTS:
            yield offset, offset + len(token.string), "string", opening
        elif token.type == tokenize.STRING:
            prefix = len(_PREFIX.match(token.string).group())  # type: ignore[union-attr]
            quote = 3 if token.string[prefix : prefix + 3] in ('"""', "'''") else 1
            where = "docstring" if any(s <= offset < e for s, e in docstrings) else "string"
            if "f" in token.string[:prefix].lower() and sys.version_info < (3, 12):
                for i, (s, e) in enumerate(_masked_fstring(token.string[prefix + quote : len(token.string) - quote])):
                    yield offset + prefix + quote + s, offset + prefix + quote + e, where, i == 0
            else:
                yield offset + prefix + quote, end - quote, where, True


def classify(text: str, found: list[Mention], rules: MentionRules, *, declaring: bool) -> tuple[list[Mention], list[Mention]]:
    """The mentions to rewrite and the ones to list."""
    rewrite: list[Mention] = []
    listed: list[Mention] = []
    for mention in found:
        if rules.qualified(text, mention.start) or (declaring and _code_marked(text, mention)):
            rewrite.append(mention)
        else:
            listed.append(mention)
    return rewrite, listed
