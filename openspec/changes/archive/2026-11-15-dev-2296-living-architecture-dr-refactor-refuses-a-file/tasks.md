## 0. Stage order (read first)

- [x] 0.1 This branch starts from the DEV-2295 branch tip (`egor/dev-2295-living-architecture-dr-refactor-names-symbols`)
      and carries its unarchived change; leave that change and its tests alone. The diff from `main` therefore already
      holds DEV-2295's tests, so `/la:pr` stage detection can pick `pr-implement`: while section 1 is open, the stage
      is `pr-tests`. pr-tests writes only the tests below; pr-implement does sections 2–3.

## 1. Tests (pr-tests)

- [x] 1.1 `python/tests/test_rope_patches.py` CORPUS gains the f-string forms of design decision 6 and the issue's
      shapes (the trampoline line; `'''` inside `"…"` with formatted values before, after and around; `"""` inside
      `'…'`; each triple quote inside the other kind of triple-quoted f-string; a triple quote in a plain piece before
      and after an f-string; `rf`/`Rf`/`fR` prefixes; `{{'''}}`), version-marked where the syntax needs 3.12 or 3.14.
      Verify: they fail before the fix on at least the shapes listed in design.md Context.
- [x] 1.2 A test over those f-string cases asserting the delimiters (design decision 5): the literal's first sorted
      child equals its opening delimiter (`f"""` for a triple-quoted f-string, never `f"`), and its last sorted child
      starts with the last piece's closing delimiter, equal to it for a one-piece literal. Verify: fails before the fix.
- [x] 1.3 Canary in `test_unpatched_rope_still_needs_the_patch` style: unpatched rope still crashes or leaves a gap on
      `x = f"'''{a}"`, with a comment to drop the patch when python-rope/rope#844 is released. Verify: passes now.
- [x] 1.4 A unit test that a region the tokenizer cannot read raises `patchedast.MismatchedTokenError` from the
      f-string visitor (design decision 4), never `IndexError`/`AttributeError`. Verify: fails before the fix.
- [x] 1.5 Conformance `compliance-rope-walk-clean`: `python/src/constructs.py` gains the exact trampoline line
      (inside a function using `sys` and `body`) and `f'{a}"""{b}'` plus the other 3.11-valid shapes of 1.1; golden
      stays empty stdout, exit 0 (`golden: manual`). Verify: the case fails before the fix.
- [x] 1.6 Conformance `refactor-rename-rope-walk-constructs`: the renamed `field` is also used inside the trampoline
      f-string and inside `f'{…}"""{…}'` in `pkg/use.py`; hand-edit `stdout` so every occurrence is renamed, and set
      `files/pkg/use.py` to the new fixture (a dry run leaves it unchanged) (`golden: manual`). Verify: the case fails
      before the fix.
- [x] 1.7 `conformance/INVENTORY.md`: the `rope-walk` and "rename across annotated parameters and f-strings" rows name
      f-strings holding triple quotes. Verify: the inventory test passes.

## 2. Implementation (pr-implement)

- [x] 2.1 Replace `_joined_str` in `python/src/living_architecture/refactor/rope_patches.py` per design decisions 1–4:
      region as today; delimiters from `tokenize` over the region wrapped in parentheses (first/last string token,
      `FSTRING_*`/`TSTRING_*` kinds the running Python defines); scanner set to the region start; `[opening,
      *formatted values, closing]` to `_handle`; the existing region/last-child extension; tokenizer failure or no
      string token raises `MismatchedTokenError`. Drop `_rope_joined_str`. Update the module docstring only if it
      stops being true. Verify: section 1 passes on every Python of the CI matrix the machine has (3.11–3.14), and
      `test_stdlib_is_walked_fully` / `test_this_repo_is_walked_fully` stay green.
- [x] 2.2 Local test scope per `/la:pr` (affected tests plus the two conformance cases), `uv run ruff check src tests`,
      `uv run basedpyright src tests`, `la-arch-check`. Verify: all green.

## 3. Verification on SLayer (dry run only)

- [x] 3.1 `git archive` SLayer's branch `egor/dev-1607-rename-columns-to-fields-to-be-consistent-with` into a temp
      directory; `dr-compliance --select rope-walk` over every `.py` file prints nothing and exits 0 (before the fix it
      lists only `tests/test_release_gate.py:231`).
- [x] 3.2 In that copy, a `dr-refactor rename-map` dry run renaming `StorageBackend.get_model`,
      `StorageBackend.get_model_or_builtin` and the `StorageBackend.get_model(name)` parameter (any new names) exits
      without `refactor.rope-walk`. Nothing is written to the SLayer checkout. Record the outcome in a Linear comment
      on DEV-2296.
