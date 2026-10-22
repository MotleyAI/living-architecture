## Context

See proposal.md (Why). rope 1.15.0 (the latest) walks a module in `patchedast._PatchingASTWalker`. Each `_<Node>`
visitor passes `_handle` a hand-written list of string tokens and child nodes, and `_handle` finds each token
with a forward `source.index` from the current offset. Text between consumed items is kept as "formats". There
`_count_needed_parens` counts `(`/`)` to widen regions over parentheses. rope patches a whole module in
`pyscopes.GlobalScope._calculate_scope_regions`, with `sorted_children=False`. It reads the regions back in
`Scope.get_region`/`in_region` to decide which scope an offset belongs to. So a gap can crash the walk, or it
can silently mis-scope names in a rename.

Probe results (1,222 tracked SLayer files; 655 stdlib files of CPython 3.14):
- Unpatched beyond the existing `_arguments` patch, the sweep found these unvisited nodes: `arg.annotation`,
  `FunctionDef/AsyncFunctionDef.returns`, `arguments.vararg/kwarg`, `ClassDef.keywords`, and `Try.orelse` when
  `finalbody` is present.
- `JoinedStr` regions end at the f-string piece.
- `rb"…"` regions start after the `r`.
- `TemplateStr` (3.14) is an unknown node.
- With the fixes below prototyped, both sweeps pass the invariant. So do 40 edge constructs on 3.11 and 3.14.
  A full stdlib sweep takes about 5 s.

## Goals / Non-Goals

**Goals:**
- One definition of "rope walked this module correctly", used by the tests, the runtime guard and the
  compliance check.
- Every gap the definition finds on supported Pythons is fixed.

**Non-Goals:**
- Exact rope regions for constructs that cannot cause drift. These are left as they are: `*`/`**` before
  `Starred`/`keyword`, number literals with `_`, generator expressions sharing a call's parentheses, and
  trailing commas. They leave only punctuation or digits unconsumed, which no later token search can match.
- Replacing rope's walker with a position-based one. That would be a fork of `patchedast`.
- The TypeScript twin. Its language service has no such walker.

## Decisions

### D1. The walker-coverage invariant
After rope walks a module, the invariant is checked in two parts.

(a) Every AST node has `region`, except:
- `expr_context`, `operator`, `boolop`, `unaryop` and `cmpop` nodes;
- `withitem` (its children are walked);
- everything below a `JoinedStr`/`TemplateStr` (values and `format_spec`). Before 3.12 their inner positions
  are not reliable. The string node's own span covers them.

(b) Every `Constant` of `str`/`bytes`, every `JoinedStr` and every `TemplateStr` has a region that contains
its AST span; anything beyond the span is only whitespace, comments and parentheses.

AST columns are UTF-8 byte offsets. One helper converts `(lineno, col_offset)` to a character offset. It
splits lines on `\r\n|\r|\n` only, as the tokenizer does; `str.splitlines` would also split on `\f`,
`\x1c` and ` `. A violation is `(line, kind)`. "First violation" means the lowest AST start position.

*Why these two parts:* a node's text can only drift the walker if it is left unconsumed, and an unconsumed
node is exactly what (a) detects. String text is the only text with arbitrary characters inside a consumed
node's span, and (b) covers it. Requiring exact regions for every node would flag the harmless differences
listed in Non-Goals, so it is not done.
*Alternative:* checking that every gap holds only punctuation needs an allowlist of rope's unmodelled tokens
(`*`, `**`, `async`, `,`, `!r`, …). That allowlist is brittle and doesn't map to a node, so it gives no line.

### D2. Walker patches
`rope_patches.py` replaces visitors on `_PatchingASTWalker`, as today. `apply_rope_patches()` is idempotent.

- `_arg`: `[arg, ":", annotation]` when there is an annotation.
- `_arguments`: the current version, but `vararg`/`kwarg` are emitted as `arg` nodes, so their annotations
  are walked.
- `_handle_function_def_node`: `"->", returns` before `":"`. Decorators and `type_params` keep their place.
- `_ClassDef`: `bases` and `keywords` are merged into one source-ordered list inside the parentheses.
- `_TryFinally`: `try:` body, handlers, then `else:` with `orelse`, then `finally:`.
- `_JoinedStr`: takes the string's end first and runs rope's own logic. On Python 3.12+ the end is the node's
  AST end, because PEP 701 lets a nested f-string reuse the outer quote (`f"{f"{a}("}" ")"`) and rope's string
  regex stops there; below 3.12 it is the `consume_string` end. Then, if the offset is before that end, it sets
  `source.offset` and the region end to it. Only when `sorted_children` is collected
  does it append the skipped text to the last child, so `write_ast` stays exact. This works independently of
  `sorted_children`, because production walks have it off.
- `_TemplateStr`/`_Interpolation` (only where `ast.TemplateStr` exists) are handled like
  `_JoinedStr`/`_FormattedValue`.
- String prefixes: `codeanalyze.get_string_pattern` / `get_formatted_string_pattern` are patched to accept
  every legal prefix, in any order and case (`r`, `b`, `u`, `f`, `t`, `rb`, `br`, `fr`, `rf`, `tr`, `rt`).
  `_Source._string_pattern` is reset, because rope caches the compiled regex on first use.
- t-strings outside the walker: rope's `simplify.real_code` blanks every string but f-strings before it finds a
  word's range, so a rename inside a t-string edits the wrong offset (`t"{a}("` becomes `t"{ab}("`).
  `codeanalyze.get_any_string_pattern` (and `simplify._str`, compiled from it) accept `t`, and
  `simplify.real_code` keeps t-strings' text like f-strings'.

Each patch has repro tests and a canary. The canary runs a subprocess with unpatched rope and asserts that
the repro still crashes or violates D1. The canary's comment links the upstream issue (D8) as a forward
pointer. When rope fixes a gap, its canary fails and the patch is dropped.

### D3. Line localization
`walk_gap_line(source) -> int | None`:
1. Parse the source and walk it with the patched walker. If the walk raises a walker failure (D4), or
   finishes with D1 violations, the line is the first violation in the partially or fully patched tree. Nodes
   finish bottom-up, so after a crash the omitted node still has a visited parent; part (a) "unvisited with a
   visited parent" finds it, and part (b) finds a short string region.
2. Otherwise walk each top-level statement's source slice alone. Top-level statements need no dedent. The line
   is the first statement that fails.
3. Otherwise 1.

It returns `None` when the module walks clean.

### D4. Runtime guard
`apply_rope_patches()` also wraps `GlobalScope._calculate_scope_regions` (rope's `@saveit` method). The wrapper
calls the original. If that raises a walker failure, or the walk leaves a D1 violation, the wrapper raises
`WalkerGap(path, line)`. The path comes from `self.pyobject.get_resource()`; the line comes from D3.

A walker failure is one of:
- `patchedast.MismatchedTokenError`;
- an exception whose innermost traceback frame is in rope's `patchedast` module (`AttributeError` from
  `_consume_pattern`, `ValueError` from `consume_joined_string`).

Any other exception propagates unchanged, including one raised in our own patch code, so a bug of ours is
never reported as a source construct.

`rope_refactor.run_refactor` catches `WalkerGap` and prints `refactor.rope-walk` on stderr, then exits 1.
rope walks modules only while computing a `ChangeSet` (`get_changes`). `project.do` only applies text and
invalidates caches. So a gap always surfaces before anything is printed to stdout or written. A test pins
that `--apply` leaves the tree unchanged.

### D5. `rope-walk` compliance check
`compliance.check_path` runs `walk_gap_line` when `rope-walk` is selected and the file parsed. A non-`None`
line becomes one `compliance.rope-walk` finding. The check uses the same functions as the guard, so the
preflight and `dr-refactor` cannot disagree. The cost is about 8 ms per file.

### D6. No rope folder
`Project(root, ropefolder=None)`. rope then keeps its object DB in memory, and the refactor results are
unchanged. In conformance, every Python refactor case lists `.ropeproject/history.json` in `expect.files` with
golden `<MISSING>`. rope creates the folder when the `Project` opens and writes `history.json` into it when
`dr-refactor` closes the project, which it always does.

### D7. Findings and goldens
- `compliance.rope-walk: '{path}:{line}: rope-walk: rope cannot follow this construct, so dr-refactor would refuse this file (a rope bug, not a source error)'`
- `refactor.rope-walk: 'rope cannot follow {path}:{line}, so nothing was refactored (a rope bug, not a source error); dr-compliance --select rope-walk lists every such file'`

Once every known gap is fixed, no real input reaches either finding. Both go in `test_contract.py`'s
`UNPRODUCED_BY_DESIGN` with that reason. They are pinned by unit tests that restore one original rope visitor
in-process (monkeypatch) and assert the exact text, line, exit code and an unchanged tree. Codex asked for
goldens; the user chose this over a test hook in shipped code.

### D8. Upstream issues (filed in pr-implement after the user's go-ahead)
`gh issue create -R python-rope/rope`, title: **patchedast: visitors that omit sub-nodes leave unconsumed text
that later token searches mis-match**. Body:

> `_PatchingASTWalker` finds each token with a forward `source.index`, so any source text a visitor does not
> list is skipped as whitespace; a `(`, `)`, `=` or quote inside it is then matched as a later token. The
> walk raises `MismatchedTokenError` / `AttributeError: 'NoneType' object has no attribute 'group'`, or it
> silently produces wrong regions, which `Scope.get_region` uses for scope lookup. On rope 1.15.0, each
> repro below makes `patchedast.get_patched_ast(src, sorted_children=True)` either raise or finish with part
> of the source left without a `region`:
>
> 1. posonly / kw-only args and `kw_defaults` (`_arguments`): `def f(*, m: str = "(host)"): pass`
> 2. parameter annotations (`_arg`): `def f(p: A[F(d="t")] = None): pass`
> 3. return annotations (`_handle_function_def_node`): `def f() -> A[F(d="(")]: pass`
> 4. `*args` / `**kwargs` annotations: `def f(*a: F("("), **k: F(")")): pass`
> 5. f-string implicitly concatenated with a later literal (`_JoinedStr` stops at the f-string's quote):
>    `c = g(f"{d}" "(")`
> 6. class keywords (`_ClassDef`): `class A(B, metaclass=M, x=")"): pass`
> 7. `else` of `try/except/else/finally` (`_TryFinally`): an `else:` body holding `x = "("`
> 8. `rb`/`Rb` prefixes (string pattern `[uUbB]?[rR]?`): `x = rb"("`; the region starts after `r`
> 9. 3.14 t-strings: `TemplateStr`/`Interpolation` are unknown nodes: `f(t"{a}(", ")")`
> 10. 3.12+ nested f-strings that reuse the outer quote: `x = f"{f"{a}("}" ")"` (the string regex stops at
>     the inner quote)
>
> Suggested regression test: after walking any module, every AST node except context/operator nodes,
> `withitem` and f-string internals has a `region`, and every string literal's region covers its
> `ast` span. With that check, CPython's stdlib and a 1,200-file project pass once the visitors above are
> fixed. We carry these patches in living-architecture's `rope_patches.py` and will drop each when it
> lands upstream.

A second issue, title: **simplify.real_code blanks t-strings, so renames inside them edit the wrong offset**. Body:

> `simplify.real_code` replaces the text of every string except f-strings (`"f" in prefix`), and
> `get_any_string_pattern`'s prefix `[bBfFrRuU]{,4}` has no `t`. On Python 3.14 a t-string's interpolations are
> therefore blanked, and renaming `a` in `def h():\n    a = 1\n    f(t"{a}(", ")")` gives `t"{ab}("`. Accepting
> `t` in the prefix and keeping t-strings' text like f-strings' fixes it.

Each canary's comment links its issue: the walker canaries link the first, the `real_code` canary the second.

### D9. Tests and CI
- `test_rope_patches.py`:
  - a checked-in grammar corpus (every repro of the spec, the issue and D8, plus the edge cases: lambda
    kinds, PEP 695, nested f-strings, `=`/`!r`/format specs, comments and backslashes between pieces,
    non-ASCII). Each case asserts D1 and `write_ast(tree) == source`;
  - one canary per gap;
  - the cache reset;
  - the stdlib sweep: every `.py` under `sysconfig.get_paths()["stdlib"]`, excluding `site-packages`, and
    skipping files that are not UTF-8 or don't parse. It runs in the default suite, by the user's choice, so
    every Python in CI checks new grammar;
  - a sweep of this repo's `python/src` and `python/tests`.
- Guard, localization and compliance unit tests use monkeypatched original visitors, through rope's real
  `Rename` path, not only `get_patched_ast`.
- CI: add `"3.14"` to `ci.yml`'s Python matrix. The t-string tests are `skipif` below 3.14.

## Risks / Trade-offs

- [rope internals change between releases] → The canaries fail on an upstream fix, and the sweep fails on a
  regression. The patches use rope 1.15 internals, so the floor is `rope>=1.15`; CI tests the locked version.
- [A new Python's stdlib exposes a gap and turns the suite red] → This is the intended signal. Fix the gap in
  `rope_patches.py`.
- [Line fallback 3 is vague] → No known input reaches it. Fallback 2 still names the statement whenever a
  single statement fails alone.
- [`dr-compliance` slows down by about 8 ms per Python file] → Acceptable for a preflight; `--select` can
  exclude the check.

## Migration Plan

Versions move to 0.3.3 in every manifest. After merge, the user publishes the GitHub release; `publish.yml`'s
release check verifies versions and contract hashes. SLayer bumps its pin under DEV-2119. A `.ropeproject/`
left in a target repo by an earlier version is not removed.
