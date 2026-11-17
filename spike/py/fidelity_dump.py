"""CPython's spans of what dr reads: AST node spans, comment and string token spans, and the parts of each string
literal (f- and t-string literal runs, replacement fields, format specs), as character and UTF-8 byte offsets.

Usage: fidelity_dump.py --root DIR [REL ...]; with no REL, reads one per line from stdin. Prints `REL<TAB>JSON` per file.
"""

from __future__ import annotations

import argparse
import ast
import codecs
import io
import itertools
import sys
import tokenize
from pathlib import Path

from binding_dump import canonical
from living_architecture.refactor.python_project import Snapshot, read_str_coding
from living_architecture.refactor.python_source import line_starts

Json = dict[str, object]
Span = tuple[int, int]

_BOM = codecs.BOM_UTF8
_STRING_NODES = (ast.JoinedStr, *((ast.TemplateStr,) if hasattr(ast, "TemplateStr") else ()))
_FIELD_NODES = (ast.FormattedValue, *((ast.Interpolation,) if hasattr(ast, "Interpolation") else ()))
_PREFIX_CHARS = frozenset("rRbBuUfFtT")
_QUOTES = ('"""', "'''", '"', "'")
_RUN_START = {name: getattr(tokenize, name) for name in ("FSTRING_START", "TSTRING_START") if hasattr(tokenize, name)}
_RUN_END = {getattr(tokenize, name) for name in ("FSTRING_END", "TSTRING_END") if hasattr(tokenize, name)}


class _Offsets:
    """Character offsets of AST and token positions, and their UTF-8 byte offsets."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.starts = line_starts(text)
        self.ascii = text.isascii()
        self._bytes = [] if self.ascii else [0, *itertools.accumulate(len(ch.encode("utf-8", "surrogatepass")) for ch in text)]

    def from_bytes(self, line: int, col: int) -> int:
        start = self.starts[line - 1]
        head = self.text[start : start + col]
        return start + (col if head.isascii() else len(head.encode()[:col].decode(errors="ignore")))

    def from_chars(self, line: int, col: int) -> int:
        return self.starts[line - 1] + col

    def entry(self, kind: str, span: Span, **extra: object) -> Json:
        start, end = span
        as_bytes = [start, end] if self.ascii else [self._bytes[start], self._bytes[end]]
        return {"kind": kind, "chars": [start, end], "bytes": as_bytes, **extra}


def _is_string_node(node: ast.AST) -> bool:
    return isinstance(node, _STRING_NODES) or (isinstance(node, ast.Constant) and isinstance(node.value, str | bytes))


def _node_span(offsets: _Offsets, node: ast.AST) -> Span:
    line, col = node.lineno, node.col_offset  # type: ignore[attr-defined]
    end_line = getattr(node, "end_lineno", None) or line
    end_col = getattr(node, "end_col_offset", None) or 0
    return offsets.from_bytes(line, col), offsets.from_bytes(end_line, end_col)


def _chunks(tree: ast.Module) -> set[int]:
    """The ids of the literal chunks and format specs inside f- and t-strings."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, _STRING_NODES):
            found.update(id(v) for v in node.values)
        elif isinstance(node, _FIELD_NODES) and node.format_spec is not None:
            found.add(id(node.format_spec))
    return found


def _nodes(offsets: _Offsets, tree: ast.Module) -> tuple[list[Json], list[Span]]:
    """Every positioned node but strings and their fields, by class name; and the spans of the expression-level string
    nodes."""
    nodes: list[Json] = []
    strings: list[Span] = []
    chunks = _chunks(tree)
    for node in ast.walk(tree):
        if not hasattr(node, "lineno"):
            continue
        if _is_string_node(node):
            if id(node) not in chunks:
                strings.append(_node_span(offsets, node))
        elif not isinstance(node, _FIELD_NODES):
            nodes.append(offsets.entry(type(node).__name__, _node_span(offsets, node)))
    return nodes, strings


class _Scanner:
    """Splits string literals of `text` into their parts, from the token's first character."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.parts: list[tuple[str, Span]] = []

    def string(self, at: int) -> int:
        """Scans the string literal starting at `at` (prefix included); its end."""
        text = self.text
        body = at
        while text[body] in _PREFIX_CHARS:
            body += 1
        prefix = text[at:body].lower()
        quote = next(q for q in _QUOTES if text.startswith(q, body))
        kind = "fstr" if "f" in prefix else "tstr" if "t" in prefix else "str"
        if kind == "str":
            end = self._plain_end(body + len(quote), quote)
        else:
            end = self._formatted(body + len(quote), quote, raw="r" in prefix, stop=None) + len(quote)
        self.parts.append((kind, (at, end)))
        return end

    def _plain_end(self, at: int, quote: str) -> int:
        text = self.text
        while not text.startswith(quote, at):
            at += 2 if text[at] == "\\" else 1
        return at + len(quote)

    def _formatted(self, at: int, quote: str | None, *, raw: bool, stop: str | None) -> int:
        """Scans literal runs and fields up to the closing `quote` (or the spec-closing `stop`); where it stopped."""
        text = self.text
        literal = at
        while True:
            if quote is not None and text.startswith(quote, at):
                break
            ch = text[at]
            if stop is not None and ch == stop:
                break
            if ch == "\\":
                if not raw and text.startswith("N{", at + 1):
                    at = text.index("}", at) + 1
                else:  # a backslash keeps a quote or backslash from ending the string, never a brace from opening a field
                    at += 1 if text[at + 1] in "{}" else 2
                continue
            if ch in "{}" and text.startswith(ch, at + 1):
                at += 2
                continue
            if ch == "{":
                self._literal(literal, at)
                at = self._field(at)
                literal = at
                continue
            at += 1
        self._literal(literal, at)
        return at

    def _literal(self, start: int, end: int) -> None:
        if end > start:
            self.parts.append(("fstr-literal", (start, end)))

    def _field(self, at: int) -> int:
        """Scans the replacement field opening at `at`; its end (after `}`)."""
        text = self.text
        start = at
        at += 1
        depth = 0
        while True:
            ch = text[at]
            if ch == "#":
                at = text.index("\n", at)
            elif ch in "\"'" or (ch in _PREFIX_CHARS and self._starts_string(at)):
                at = self.string(at)
                continue
            elif ch in "([{":
                depth += 1
            elif ch in ")]" or (ch == "}" and depth):
                depth -= 1
            elif depth == 0 and ch == "}":
                break
            elif depth == 0 and ch == "!" and not text.startswith("=", at + 1):
                at += 1
                while text[at] not in ":}":
                    at += 1
                continue
            elif depth == 0 and ch == ":":
                spec = at + 1
                at = self._formatted(spec, None, raw=False, stop="}")
                self.parts.append(("fstr-spec", (spec, at)))
                break
            at += 1
        self.parts.append(("fstr-field", (start, at + 1)))
        return at + 1

    def _starts_string(self, at: int) -> bool:
        """A string prefix starts at `at`: prefix letters right before a quote, not inside a longer name."""
        text = self.text
        if at > 0 and (text[at - 1].isalnum() or text[at - 1] == "_"):
            return False
        end = at
        while end < len(text) and text[end] in _PREFIX_CHARS and end - at < 2:
            end += 1
        return end < len(text) and text[end] in "\"'"


def _string_kind(token: str) -> str:
    """A string token's kind by its prefix: Python 3.11 tokenizes an f-string as one STRING token."""
    prefix = token[: len(token) - len(token.lstrip("rRbBuUfFtT"))].lower()
    return "fstring" if "f" in prefix else "tstring" if "t" in prefix else "string"


def _tokens(offsets: _Offsets) -> tuple[list[Json], list[Span]] | str:
    """Top-level comment and string tokens (an f- or t-string run as one), and the string token spans; or the
    tokenizer's error."""
    found: list[Json] = []
    strings: list[Span] = []
    depth = 0
    run_start = 0
    run_kind = ""
    try:
        for tok in tokenize.generate_tokens(io.StringIO(offsets.text, newline="").readline):
            if tok.type in _RUN_START.values():
                if depth == 0:
                    run_start = offsets.from_chars(*tok.start)
                    run_kind = "fstring" if tok.type == _RUN_START.get("FSTRING_START") else "tstring"
                depth += 1
            elif tok.type in _RUN_END:
                depth -= 1
                if depth == 0:
                    end = offsets.from_chars(*tok.end)
                    found.append(offsets.entry(run_kind, (run_start, end)))
                    strings.append((run_start, end))
            elif depth == 0 and tok.type in (tokenize.COMMENT, tokenize.STRING):
                span = offsets.from_chars(*tok.start), offsets.from_chars(*tok.end)
                found.append(offsets.entry("comment" if tok.type == tokenize.COMMENT else _string_kind(tok.string), span))
                if tok.type == tokenize.STRING:
                    strings.append(span)
    except (tokenize.TokenError, SyntaxError) as exc:
        return type(exc).__name__
    return found, strings


def _innermost(spans: list[Span], span: Span) -> list[int] | None:
    inside = [s for s in spans if s[0] <= span[0] and span[1] <= s[1]]
    return list(min(inside, key=lambda s: s[1] - s[0])) if inside else None


def string_parts(offsets: _Offsets, tokens: list[Span], nodes: list[Span]) -> list[Json]:
    """The parts of each string token, each with the span of the innermost string node holding it."""
    scanner = _Scanner(offsets.text)
    for start, end in tokens:
        if scanner.string(start) != end:
            raise ValueError(f"string token {start}:{end} scanned to a different end")
    return [offsets.entry(kind, span, node=_innermost(nodes, span)) for kind, span in sorted(scanner.parts, key=lambda p: (p[1], p[0]))]


def _sorted(entries: list[Json]) -> list[Json]:
    return sorted(entries, key=lambda e: (e["chars"], e["kind"]))  # type: ignore[arg-type,return-value]


def dump_text(text: str) -> Json:
    """The span dump of a decoded source `text`."""
    offsets = _Offsets(text)
    try:
        tree: ast.Module | None = ast.parse(text)
    except (SyntaxError, ValueError):
        tree = None
    tokens = _tokens(offsets)
    out: Json = {"status": "ok" if tree is not None else "syntax-error"}
    out["tokens"] = _sorted(tokens[0]) if isinstance(tokens, tuple) else tokens
    if tree is not None:
        nodes, strings = _nodes(offsets, tree)
        out["nodes"] = _sorted(nodes)
        out["strings"] = string_parts(offsets, tokens[1], strings) if isinstance(tokens, tuple) else []
    return out


def dump(root: Path, rel: str) -> Json:
    try:
        text = Snapshot(root).text(rel)
    except (UnicodeDecodeError, LookupError):
        return {"status": "undecodable"}
    return dump_text(text)


def _decoding(data: bytes, encoding: str | None) -> str:
    """The codec `encoding` names, or why `data` does not decode with it."""
    if encoding is None:
        return "error"
    try:
        name = codecs.lookup(encoding).name
    except LookupError:
        return "error"
    try:
        data.decode(name)
    except UnicodeDecodeError:
        return f"{name}: undecodable"
    return name


def encodings(data: bytes) -> Json:
    """dr's decoding rule and `tokenize.detect_encoding` on the same bytes, and whether their outcomes differ."""
    body = data.removeprefix(_BOM)
    dr = _decoding(body, read_str_coding(body) or "utf-8")
    try:
        detected: str | None = tokenize.detect_encoding(io.BytesIO(data).readline)[0]
    except SyntaxError:
        detected = None
    if detected == "utf-8-sig":
        detected, data = "utf-8", body
    cpython = _decoding(data, detected)
    return {"dr": dr, "cpython": cpython, "differ": dr != cpython}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("rels", nargs="*")
    args = parser.parse_args(argv)
    rels = args.rels or [line.rstrip("\n") for line in sys.stdin if line.strip()]
    for rel in rels:
        sys.stdout.write(f"{rel}\t{canonical(dump(args.root, rel))}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
