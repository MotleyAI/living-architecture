import ast
import re
import subprocess
import sys
import sysconfig
from collections.abc import Callable
from pathlib import Path

import pytest
from rope.base import codeanalyze, pyscopes, simplify
from rope.refactor import patchedast

from living_architecture.refactor import rope_patches

PY312 = pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 / PEP 701 syntax")
PY313 = pytest.mark.skipif(sys.version_info < (3, 13), reason="PEP 696 type parameter defaults")
PY314 = pytest.mark.skipif(sys.version_info < (3, 14), reason="t-strings")

CLICKHOUSE = (
    "(checks,) = _admin_rows(\n"
    "    clickhouse_container,\n"
    "    \"SELECT count() FROM system.query_log WHERE type = 'QueryFinish' \"\n"
    "    f\"AND user = '{clickhouse_readonly_datasource.username}' \"\n"
    "    \"AND query LIKE '%getSetting(%readonly%'\",\n"
    ")\n"
)

CORPUS = [
    # signatures
    pytest.param('def f(*, m: str = "(host)"):\n    pass\n', id="kwonly-default"),
    pytest.param('def f(a, /, b="(", *args, c=")", **kw):\n    pass\n', id="posonly-vararg-kwonly-kwarg"),
    pytest.param("def f(a, /):\n    pass\n", id="posonly-only"),
    pytest.param("def f(*args, k=1):\n    pass\n", id="vararg-kwonly"),
    pytest.param('def f(p: A[F(d="t")] = None) -> str:\n    return ""\n', id="annotation-keyword"),
    pytest.param(
        'async def probe(p: Annotated[_Payload | None, Field(description="param text")] = None) -> str:\n'
        '    """Docstring text."""\n'
        '    return ""\n',
        id="async-annotated-field",
    ),
    pytest.param('def f() -> A[F(d="(")]:\n    pass\n', id="return-annotation"),
    pytest.param('async def f() -> A[F(d=")")]:\n    pass\n', id="async-return-annotation"),
    pytest.param('def f(*a: F("("), **k: F(")")):\n    pass\n', id="star-annotations"),
    pytest.param('def f(*, k: F(")") = "(") -> None:\n    pass\n', id="kwonly-annotated-default"),
    pytest.param('def f(a: F("("), /, b: F(")") = 1) -> None:\n    pass\n', id="posonly-annotated"),
    pytest.param(
        'class C:\n    @d(x="(")\n    async def m(self, p: A[F(d="(")] = None) -> F(")"):\n        pass\n',
        id="decorated-async-method",
    ),
    pytest.param(
        'def f(\n    a: int,\n    p: A[F(d="(")] = None,\n    *rest: F(")"),\n) -> A["("]:\n    return a\n',
        id="multiline-signature",
    ),
    pytest.param('f = lambda a, /, b=")", *c, d="(", **e: a\n', id="lambda-every-kind"),
    pytest.param('g = lambda *, k="(": k\n', id="lambda-kwonly"),
    pytest.param('h = lambda: "("\n', id="lambda-no-args"),
    pytest.param('def f[T: A[F(d="(")], *Ts, **P](x: T) -> T:\n    return x\n', id="pep695-bound", marks=PY312),
    pytest.param('class C[T: (int, str)](B[T], metaclass=M, x="("):\n    pass\n', id="pep695-class", marks=PY312),
    pytest.param('type X[T: A[F(d="(")]] = list[T]\n', id="pep695-alias", marks=PY312),
    pytest.param(
        'def f[T = int, *Ts = *tuple[int], **P = [str]](x: T = "(") -> T:\n    return x\n',
        id="pep696-defaults",
        marks=PY313,
    ),
    # f-strings
    pytest.param('c = g(f"{d}" "(")\n', id="fstring-then-paren-literal"),
    pytest.param(CLICKHOUSE, id="fstring-clickhouse"),
    pytest.param('g(f"{d}(")\n', id="fstring-holding-paren"),
    pytest.param('g("(" f"{d}")\n', id="literal-then-fstring"),
    pytest.param('g(f"{d}" "x")\n', id="fstring-then-literal"),
    pytest.param('x = (f"{a}" "(" f"{b}" ")" "(")\n', id="fstring-multi-piece"),
    pytest.param('x = f"""{a}\n(""" """)\n"""\n', id="fstring-triple-quoted"),
    pytest.param("x = f\"{a!r:>{w}} {b=} {f'{c}('}\" \")\"\n", id="fstring-conversion-spec-nested"),
    pytest.param('x = f"{f"{a}("}" ")"\n', id="fstring-nested-same-quotes", marks=PY312),
    pytest.param('x = (f"{a}"  # (\n     "(")\n', id="fstring-comment-between"),
    pytest.param('x = f"{a}" \\\n    "("\ny = g(1)\n', id="fstring-backslash-between"),
    # string prefixes
    pytest.param('x = rb"("\n', id="prefix-rb"),
    pytest.param('x = Rb"("\n', id="prefix-Rb"),
    pytest.param('x = bR"(" br")" BR"(" RB")"\n', id="prefix-bR-br-BR-RB"),
    pytest.param('x = u"(" U")"\n', id="prefix-u"),
    pytest.param('x = rf"{a}(" Rf")" fR"(" FR")"\n', id="prefix-rf"),
    # class keywords, try/except/else/finally
    pytest.param('class A(B, metaclass=M, x=")"):\n    pass\n', id="class-keywords"),
    pytest.param('class A(metaclass=M):\n    x = "("\n', id="class-keyword-only"),
    pytest.param('class A(x=")", *bases, **kw):\n    pass\n', id="class-keyword-before-starred"),
    pytest.param('try:\n    a = 1\nexcept E:\n    b = 2\nelse:\n    x = "("\nfinally:\n    y = ")"\n', id="try-else-finally"),
    pytest.param(
        'try:\n    a = 1\nexcept* E:\n    b = 2\nelse:\n    x = "("\nfinally:\n    y = ")"\n', id="try-star-else-finally"
    ),
    pytest.param('try:\n    a = "("\nfinally:\n    b = ")"\n', id="try-finally"),
    pytest.param('try:\n    a = 1\nexcept E:\n    pass\nelse:\n    x = "("\n', id="try-else"),
    # t-strings
    pytest.param('f(t"{a}(", ")")\n', id="tstring", marks=PY314),
    pytest.param('x = (t"{a}" t"(")\n', id="tstring-concatenated", marks=PY314),
    pytest.param('x = t"{a!r:>{w}} {b=}(" rt"{c}(" Tr")"\n', id="tstring-spec-prefixes", marks=PY314),
    # non-ASCII and line separators
    pytest.param('def f(s: str = "😀", p: A[F(d="(")] = None) -> str:\n    return ""\n', id="non-ascii-before-annotation"),
    pytest.param('def f(p: A[F(d="é(")] = None) -> "ü(":\n    pass\n', id="non-ascii-in-annotation"),
    pytest.param('é = f"ü{a}é" "(" "ö"\n', id="non-ascii-fstring"),
    pytest.param('x = "é" + Rb"("\n', id="non-ascii-before-prefix"),
    pytest.param('class Ä(B, x="ö("):\n    pass\n', id="non-ascii-class-keyword"),
    pytest.param('x = t"é{ü}(" t")"\n', id="non-ascii-tstring", marks=PY314),
    pytest.param(
        'x = "\x1c\u2028\x85"\ndef f(p: A[F(d="(")] = None) -> str:\n    return ""\n', id="line-separators-in-string"
    ),
    pytest.param('\x0cdef f(p: A[F(d="(")] = None):\n    pass\n', id="form-feed"),
    pytest.param('def f(p: A[F(d="(")] = None):\r\n    return f"{p}" "("\r\n', id="crlf"),
]


def _violations(source: str, *, sorted_children: bool = False) -> list[tuple[int, str]]:
    rope_patches.apply_rope_patches()
    return rope_patches.coverage_violations(patchedast.get_patched_ast(source, sorted_children), source)


@pytest.mark.parametrize("source", CORPUS)
def test_corpus_is_walked_fully_and_written_back(source: str) -> None:
    rope_patches.apply_rope_patches()
    tree = patchedast.get_patched_ast(source, sorted_children=True)
    assert rope_patches.coverage_violations(tree, source) == []
    assert patchedast.write_ast(tree) == source


@pytest.mark.parametrize("source", CORPUS)
def test_corpus_is_walked_fully_without_sorted_children(source: str) -> None:
    assert _violations(source) == []


# Canaries: unpatched rope still mis-walks each repro; drop its patch once rope fixes the gap upstream.
UNPATCHED_WALK = """\
import sys
from rope.refactor import patchedast

source = sys.argv[1]
try:
    tree = patchedast.get_patched_ast(source, sorted_children=True)
except Exception:
    print("crash")
else:
    # Imported only after the walk: importing the package applies the patches.
    from living_architecture.refactor.rope_patches import coverage_violations

    print("gap" if coverage_violations(tree, source) else "clean")
"""


@pytest.mark.parametrize(
    "source",
    [
        pytest.param('def f(*, m: str = "(host)"): pass\n', id="kwonly-arguments"),
        pytest.param('def f(p: A[F(d="t")] = None): pass\n', id="parameter-annotation"),
        pytest.param('def f() -> A[F(d="(")]: pass\n', id="return-annotation"),
        pytest.param('def f(*a: F("("), **k: F(")")): pass\n', id="star-annotations"),
        pytest.param('c = g(f"{d}" "(")\n', id="fstring-concatenation"),
        pytest.param('class A(B, metaclass=M, x=")"): pass\n', id="class-keywords"),
        pytest.param('try:\n    pass\nexcept E:\n    pass\nelse:\n    x = "("\nfinally:\n    pass\n', id="try-else-finally"),
        pytest.param('x = rb"("\n', id="string-prefix"),
        pytest.param('f(t"{a}(", ")")\n', id="tstring", marks=PY314),
    ],
)
def test_unpatched_rope_still_needs_the_patch(source: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", UNPATCHED_WALK, source], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() in {"crash", "gap"}


def test_unpatched_rope_still_blanks_tstrings() -> None:
    script = "from rope.base import simplify; print(simplify.real_code('t\"{a}(\"'))"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "a" not in result.stdout


def test_patched_simplify_keeps_tstring_text() -> None:
    rope_patches.apply_rope_patches()
    assert simplify.real_code('x = t"{a}" + T"{b}" + "c"\n') == 'x = t"{a}" + T"{b}" + " "\n'


def test_apply_resets_a_primed_string_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(patchedast._Source, "_string_pattern", re.compile(r'"[^"\n]*"'))
    assert _violations('x = rb"("\n') == []


def test_apply_is_idempotent() -> None:
    def state() -> tuple[object, ...]:
        return (
            dict(vars(patchedast._PatchingASTWalker)),
            pyscopes.GlobalScope._calculate_scope_regions,
            codeanalyze.get_string_pattern,
            codeanalyze.get_formatted_string_pattern,
        )

    rope_patches.apply_rope_patches()
    once = state()
    rope_patches.apply_rope_patches()
    assert state() == once


@pytest.mark.parametrize(
    ("source", "line", "col", "offset"),
    [
        ("é\nab😀c\n", 2, len("ab😀".encode()), 5),
        ("a\x1cb\u2028c\x0cd\nx\n", 2, 0, 8),
        ("a\r\nb\rc\n", 3, 0, 5),
    ],
)
def test_char_offset_counts_characters_on_tokenizer_lines(source: str, line: int, col: int, offset: int) -> None:
    assert rope_patches.char_offset(source, line, col) == offset


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "site-packages" not in p.relative_to(root).parts)


def _readable_source(path: Path) -> str:
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source)
    except (UnicodeDecodeError, SyntaxError, ValueError):
        pytest.skip("not UTF-8 or not parsable on this Python")
    return source


STDLIB = Path(sysconfig.get_paths()["stdlib"])
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("path", _python_files(STDLIB), ids=lambda p: p.relative_to(STDLIB).as_posix())
def test_stdlib_is_walked_fully(path: Path) -> None:
    assert _violations(_readable_source(path)) == []


@pytest.mark.parametrize(
    "path",
    _python_files(PACKAGE_ROOT / "src") + _python_files(PACKAGE_ROOT / "tests"),
    ids=lambda p: p.relative_to(PACKAGE_ROOT).as_posix(),
)
def test_this_repo_is_walked_fully(path: Path) -> None:
    assert _violations(_readable_source(path)) == []


def test_gap_line_is_the_construct_not_the_drift(
    restore_rope_visitor: Callable[[str], None], annotation_gap: str
) -> None:
    restore_rope_visitor("_arg")
    with pytest.raises(patchedast.MismatchedTokenError, match=r"at \(8, "):
        patchedast.get_patched_ast(annotation_gap)
    assert rope_patches.walk_gap_line(annotation_gap) == 3


def test_gap_line_of_a_silent_gap_is_the_short_string(restore_rope_visitor: Callable[[str], None]) -> None:
    restore_rope_visitor("_JoinedStr")
    source = 'é = "😀"\nx = f"{é}" "y"\n'
    patchedast.get_patched_ast(source)
    assert rope_patches.walk_gap_line(source) == 2


def test_gap_line_falls_back_to_the_top_level_statement(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every string fails inside rope's walker, so the partial tree locates nothing.
    monkeypatch.setattr(patchedast._Source, "_string_pattern", re.compile("(?!)"))
    assert rope_patches.walk_gap_line('import os\n\n\ndef use() -> str:\n    os.sep\n    return "x"\n') == 4


def test_gap_line_falls_back_to_line_one(monkeypatch: pytest.MonkeyPatch) -> None:
    original = patchedast._PatchingASTWalker._Module

    def whole_module_only(self: patchedast._PatchingASTWalker, node: ast.Module) -> None:
        if len(node.body) > 1:
            raise patchedast.MismatchedTokenError("fails only as a whole")
        original(self, node)

    monkeypatch.setattr(patchedast._PatchingASTWalker, "_Module", whole_module_only)
    assert rope_patches.walk_gap_line("x = 1\n\ny = 2\n") == 1


def test_gap_line_of_a_clean_module_is_none() -> None:
    assert rope_patches.walk_gap_line('def f(p: A[F(d="(")] = None) -> str:\n    return f"{p}" "("\n') is None
