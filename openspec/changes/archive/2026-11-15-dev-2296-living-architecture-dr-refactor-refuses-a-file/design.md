## Context

See proposal.md (Why). rope's `_PatchingASTWalker._JoinedStr` (rope 1.15.0, and unchanged on rope master and 1.15.2)
picks an f-string's opening delimiter as the first quote found in its text (shortest first, so `f"""` reads as
`f"`) and its closing delimiter as the last `len(q)` characters of the literal, where `q` is the longest quote run
found anywhere in its text. A `'''` or `"""` in the text therefore becomes the "closing quote", and the walk fails or
leaves the literal uncovered depending on the characters that happen to end the literal. Probed failures, every
supported Python version: `f"'''{y}"`, `f"{y}'''{y}"`, `f'{y}"""{y}'`, `"'''" f"{y}"`, `f"{{'''}} {y}"` and
SLayer's trampoline `f"#!/bin/sh\n'''exec' '{sys.executable}' …\n{body}"` (the only one of SLayer's ~1600 sources
on branch `egor/dev-1607-rename-columns-to-fields-to-be-consistent-with` at `5ea44799` that `rope-walk` lists).

Our `_joined_str` patch (`python/src/living_architecture/refactor/rope_patches.py`) wraps rope's visitor: it takes the
literal's region (the parser's on 3.12+, `consume_string` before), calls rope's `_JoinedStr`, then extends the
region over every implicitly concatenated piece. The coverage invariant (`coverage_violations`) and the scope-region
guard turn any remaining gap into the `refactor.rope-walk` refusal.

Upstream: python-rope/rope#844 (open, unreviewed) fixes the closing-delimiter choice. It is not worth filing a
separate rope issue; the canary points at #844.

Principles that apply (`architecture/system.arc42.md`; `python.refactor` has no arc42 of its own):
1. Twins — the behaviour is Python-only (the npm twin hands Python files to this twin); its conformance cases are
   `adapter` cases, like the existing rope-walk cases.
3. Language-specific code only in `lang` and `refactor` — the change is inside `refactor`.

Spec attachment: `refactor`, owned by `python.refactor`. No model or arc42 edit.

## Goals / Non-Goals

**Goals:**
- Symptom: a module holding an f-string whose text contains a triple quote is refused. Structural cause: rope reads
  an f-string's delimiters by searching the literal's text for quote characters. Fix the cause: delimiters come only
  from Python's own tokens, so no text inside a literal (or a comment between pieces) can ever be read as a
  delimiter, on every supported Python version and for t-strings too.
- Our f-string visitor no longer calls rope's `_JoinedStr`, so a rope release that changes it cannot reintroduce the
  gap.

**Non-Goals:**
- rope's text search for a replacement field's `{` (it can land on a `{{` or on a `{` in a plain piece of the same
  concatenation): the spec excludes f-string internals from coverage, and they do not affect the scope regions
  `dr-refactor` uses.
- The pre-3.12 region computation (`consume_string`), unchanged.

## Decisions

1. **Replace rope's `_JoinedStr` wholly, not just its closing-quote choice.** The visitor computes the region as
   today, derives both delimiters itself, positions the scanner at the region start, hands `[opening, *formatted
   values, closing]` to `_handle`, then extends the region (and the last sorted child) to the region end as today.
   Alternatives: patch only `end_quote_char` (rope#844's shape) — leaves `f"""` read as `f"` and the dependency on
   rope's evolving visitor. (default)
2. **Delimiters from Python's tokenizer over the region.** `tokenize` runs over the region text wrapped in
   parentheses; comments and line breaks are skipped. The opening delimiter is the first token's: an
   `FSTRING_START`/`TSTRING_START` token's text, or a `STRING` token's prefix and quote (matched anchored at the
   token's start). The closing delimiter is the last token's: an `FSTRING_END`/`TSTRING_END` token's text, or a
   `STRING` token's quote. Nested same-quote f-strings (3.12+) are nested token pairs, so the outermost first and last
   tokens are the literal's own. Alternative: `re.finditer` with the string pattern over the region — not a tokenizer:
   it matches quotes inside comments between pieces (`(f"{a}"  # """ …\n """x""")`) and mis-splits nested same-quote
   f-strings. (codex; it replaced the plan's regex split)
3. **The scanner starts at the region start.** `self.source.offset` is set to the region start before `_handle`, so
   the opening delimiter is consumed exactly there and never at an earlier match in text before the literal (a
   comment such as `# f"`). The parent's formatting text is unchanged, as it is computed from the child's region.
   (default)
4. **A region the tokenizer cannot read is a walker failure.** A `tokenize` error, or no string token in the region,
   raises `patchedast.MismatchedTokenError`, so the existing guard refuses it as `rope-walk`; no `IndexError` or
   `AttributeError` escapes. (codex)
5. **Tests assert the delimiters, not only coverage and round-trip.** The tail extension can mask a short closing
   match, so corpus tests also assert that the literal's first sorted child is its opening delimiter and its last
   sorted child starts with its last piece's closing delimiter (equals it for a one-piece literal). (codex)
6. **Boundary cases in the corpus.** Besides the issue's shapes: quotes and triple quotes inside comments between
   pieces (LF and CRLF), backslash continuations next to triple-quoted pieces, empty first/last pieces
   (`f"{a}" ""`, `f"{a}"""`), mixed plain/f pieces of different quote widths, nested same-quote single and triple
   f-strings (3.12+), multi-line triple-quoted f-strings, escaped quotes, non-ASCII text in a multi-line
   concatenation, mixed-case prefixes, t-strings (3.14). (codex)
7. **The exact trampoline repro goes into `compliance-rope-walk-clean`**, so the issue's command-level outcome
   (`dr-compliance --select rope-walk` prints nothing) is pinned by the conformance corpus, not only by unit tests.
   (codex)
8. **Extend the existing rope-walk conformance cases** (`compliance-rope-walk-clean`,
   `refactor-rename-rope-walk-constructs`) instead of adding cases: they are the corpus of this requirement's list.
   Goldens are `golden: manual`, edited by hand. (default)
9. **No rope issue is filed**: python-rope/rope#844 fixes exactly this; the new canary names it as the pointer for
   dropping the patch. (default; answers the user's question)
10. **Verification on SLayer**, dry run only, on a `git archive` copy of branch
    `egor/dev-1607-rename-columns-to-fields-to-be-consistent-with`: `dr-compliance --select rope-walk` over every
    source prints nothing, and a `rename-map` of `StorageBackend.get_model`, `StorageBackend.get_model_or_builtin`
    and the `StorageBackend.get_model(name)` parameter (any new names) finishes without `rope-walk`. Nothing is
    written to SLayer. (default, from the issue)

## Risks / Trade-offs

- [Python's tokenizer changes token kinds again (as 3.12 and 3.14 did)] → the visitor accepts `STRING` and every
  `*STRING_START`/`*STRING_END` kind the running Python defines; the stdlib walk test runs on every CI Python.
- [The region before 3.12 comes from rope's string regex, which could include a non-string tail] → unchanged
  behaviour; a tokenizer failure on it is refused as `rope-walk` (decision 4), never a crash.
