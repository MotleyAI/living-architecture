## 0. Stage order and conventions (read first)

- [ ] 0.1 pr-tests does section 1 only; pr-implement does sections 2–7. While section 1 is open the stage is
      `pr-tests`.
- [ ] 0.2 Every new conformance case is a Python `adapter` case, listed in `conformance/INVENTORY.md` (design
      decisions 9, 24). A case whose output on today's (rope) code is valid Python that keeps every reference bound
      gets its golden from today's code with `LA_UPDATE_GOLDENS=1`, written in pr-tests BEFORE any production change,
      reason "new case" in the commit message, and its golden diff reviewed. Every other case is `golden: manual`,
      hand-written to the spec delta. Existing Python move goldens are never regenerated.
- [ ] 0.3 The differential (section 5) compares raw edits (span and new text), rendered stdout and stderr, and
      findings. On any difference not pinned by a `golden: manual` case: STOP and ask the user (design decision 2).

## 1. Tests (pr-tests)

- [ ] 1.1 Rope-equivalence fixtures (rope-written goldens where today's output is valid; record per case which kind
      it got and why): a top-level relative import read by the moved code; aliased imports (`import a.b as c`,
      `from m import n as o`) and a star import in the source; a package `__init__.py` as the source; a moved variable,
      a moved annotated multi-line variable; a decorated class with a comment between decorators and `#` lines above
      preceded by a blank line; a comment after the body; a form-feed / whitespace-only line after the body; EOF
      without a newline; a nonliteral and an augmented `__all__`; two star imports; imports read only by a decorator
      or a default value; mixed newlines (CRLF source → LF destination, LF source → CRLF destination without a final
      newline, a BOM source) with `--apply`. Verify: each passes on today's code; any case whose today's output turns
      out invalid is raised with the user before writing its golden.
- [ ] 1.2 Spec "Python moves resolve statically without rope": "No server for a symbol move" (unit test: the language
      server factory fails if called); "rope computes nothing" (unit test: every rope entry point used by moves today
      — `create_move`, `occurrences.create_finder`, `MoveGlobal._get_moving_region`,
      `_get_moving_element_with_imports`, `rope.base.project.Project`, `libutils.modname` — patched to raise, the
      walker-gap check left working; a move-symbol and a move-module run print their goldens); "Use through a package
      that binds the module itself" (three `__init__` variants: module level, inside `if`/`try`, `__getattr__`) and
      "Use through a submodule attribute only" as conformance cases. Verify: the rope-free unit test fails on today's
      code; record which conformance cases pass on today's code.
- [ ] 1.3 Spec "Python move-symbol moves one top-level declaration": conformance cases for "Import binding or reference
      as the locator" (both forms), each form of "Not movable", "Overload group moves as one", "Decorated class with
      leading comments", "Moved variable" (`golden: manual` where 0.2 says so). Verify: the not-movable and overload
      cases fail on today's code (traceback or broken output).
- [ ] 1.4 Spec "Python refactors resolve through namespace packages": every scenario as a conformance case
      (`golden: manual`), the module-rename one included. Verify: each fails on today's code.
- [ ] 1.5 Spec "Python moves rewrite each reference minimally", new scenarios: "Destination import order", "Import used
      only by the moved code inside a block stays", "TYPE_CHECKING import follows the moved code" (both forms),
      "Other guarded import refused" (produces `refactor.guarded-import`; add the template to `shared/findings.yaml`
      with design decision 12's approved wording and run `scripts/sync-shared`), "Relative import inside the moved
      code". Verify: each fails on today's code.
- [ ] 1.6 Spec "Refactors edit only at references", "Moved code between files of different line endings": covered by
      1.1's newline cases. Verify: listed in INVENTORY.md against this scenario.
- [ ] 1.7 Package-attribute fixtures (design decision 16): `import pkg.a` then `pkg.a.f`, a re-export chain, two
      bindings of one package attribute. Verify: record which pass on today's code; any rope output that rewrites a
      use the package binds is raised with the user.
- [ ] 1.8 Unit tests: `FileChanged` for a reference-only file and a child of a moved package changed between read and
      write (design decision 21); namespace-package identity (design decision 20: `src/` layout, nested namespace, a
      submodule in two portions → unresolved) on `static_resolver` / `ProjectLayout`. Verify: the namespace tests fail
      on today's code.
- [ ] 1.9 Align existing tests with the plan (design decision 10): `python/tests/test_contract.py:625-626` to the
      renamed keys; `python/tests/test_move_edits.py` to the new entry points (signature as section 4 defines it),
      same cases and expectations. Verify: both fail on today's code only on the renamed keys / entry points.

## 2. Shared contract

- [x] 2.1 Rename `refactor.ts-move-symbol-header` → `refactor.move-symbol-header`, `refactor.ts-move-module-header` →
      `refactor.move-module-header`, `refactor.ts-moved` → `refactor.moved` in `shared/findings.yaml`;
      `scripts/sync-shared`; `node/src/refactor/typescript.ts` and `session.ts` use the new keys. Verify:
      `scripts/sync-shared --check`, `npm run lint && npm run typecheck`, `npm test`, and `scripts/conformance-cross`
      over the TypeScript move cases pass.
- [x] 2.2 `diff_render.move_description` renders `refactor.moved`. Verify: module-rename goldens unchanged.

## 3. Static resolver

- [x] 3.1 Namespace packages (design decision 20) in the module finder / `ProjectLayout`. Verify: 1.8's namespace unit
      tests and 1.4's module-rename case pass.
- [x] 3.2 `Binder` records, per import binding, its statement, item index and whether it sits in the module body or a
      block (design decision 4). Verify: a unit test over a module with body-level and block-level imports.

## 4. Move planner on the resolver (new path beside the old)

- [x] 4.1 Rebuild the planner's scopes, use lookups, name-conflict checks, "binds module" and import drops on the
      resolver's `Module` (design decision 4); references for `move-module` and `move-symbol` from the resolver,
      rule 2 as design decision 16. Verify: `test_move_edits.py` passes against the new path.
- [x] 4.2 Locator and movability (spec; design decisions 5, 7, 17). Verify: 1.3's cases pass on the new path.
- [x] 4.3 Region (design decision 19). Verify: 1.1's region cases pass on the new path.
- [x] 4.4 Destination imports (design decision 25) with guarded, `__future__` and relative-import rules (decisions
      11–14) and source-side removal limited to the module body. Verify: 1.1, 1.5 pass on the new path.
- [x] 4.5 la's project model and newlines (design decisions 5, 15, 21): `Snapshot`, `TextEdit`, `FileMove`,
      `changes_of`, `emit` with `refactor.move-symbol-header` / `refactor.move-module-header`; `moved_code=True` for
      `move-symbol`. Verify: 1.1's newline cases and 1.8's `FileChanged` tests pass on the new path.
- [x] 4.6 Qualified self-reference inside the moved code (spec scenario "Qualified self-reference inside the moved code"), with a Python adapter conformance case listed in `conformance/INVENTORY.md`. Verify: the case passes and every existing move golden is unchanged.

## 5. Differential and switch

- [x] 5.1 Run old and new paths over every Python move conformance case, `test_move_edits.py`'s fixtures and section
      1's fixtures; compare as 0.3 says. Verify: no difference outside the `golden: manual` cases, or each one
      resolved with the user.
- [x] 5.2 Switch `rope_refactor.move_symbol` / `move_module` to the new path; delete `_RopeProject`, `resource`,
      `_destination`, `_rope_offset`, `rename_map.source_bytes`, `change_set_writes`, `_Scopes` / `_Scope` /
      `_Binding`, `_explicitly_binds`, `_module_object`, `_primary`, `_finder`, and every rope import in
      `move_edits.py` and `rope_refactor.py` except what the walker-gap check needs. Verify: 1.2's rope-free test
      passes; `rg -n "rope" python/src/living_architecture/refactor/move_edits.py` prints nothing.

## 6. Docs

- [x] 6.1 Apply design decision 6's approved wording verbatim to the five files. Verify: `rg -n "rope computes moves|rope for Python|with rope and" docs plugin` prints nothing.

## 7. Gates

- [x] 7.1 Local test scope (la:pr "Local test scope") passes: `uv run pytest` on the affected tests and the touched
      conformance cases; `uv run ruff check src tests`; `uv run basedpyright src tests`; `la-typecheck`.
- [x] 7.2 Enforcement bundle: `la-arch-check`, `npx likec4 validate` (or the lightest parse), `la-typecheck` against
      its baseline. Verify: all green.
- [x] 7.3 `openspec validate dev-2311-living-architecture-python-dr-refactor-moves --strict` passes.

## 8. Output checks: stage order (read first)

Sections 8–13 are a second pass on this change, planned after PR #60 was opened (design decisions 26–38, spec
requirement "Python refactors check their output before writing"). They replace further point fixes.

- [x] 8.1 PR #60 is open, so `/la:pr` detects `pr-review`. The user names the stage instead: `pr-tests` does section 9
      only; `pr-implement` does sections 10–13, then commits and pushes to the existing PR #60 (no new PR, no go-ahead
      gate). `pr-review` resumes only when sections 9–13 are all ticked.
- [x] 8.2 Rules that hold in every section: every new conformance case is a Python `adapter` case with
      `golden: manual`, hand-written, listed in `conformance/INVENTORY.md`; no existing golden is regenerated or
      edited, except the one case of task 9.10; the finding text and the spec requirement are applied verbatim from design decisions 28 and 29; on any
      existing case or test that starts failing, design decision 36 applies (STOP, show the user, change nothing).
- [x] 8.3 Do not touch what the earlier fixes added (`insert_after`'s inline suites, `_fill_emptied`, the coding
      header rule, `refactor.ambiguous-module`, the placement rules): they stay, and their goldens must stay green.

## 9. Output checks: tests (pr-tests)

Every test below must FAIL on the code as it is before section 10 (state for each how it fails); none may be skipped
or marked xfail. Unit tests drive the real CLI through `python/tests/refactor_cli.py` (`run`, `run_raw`) on a project
written with `project_files.write_project` under `tmp_path`.

- [x] 9.1 Add `refactor.resolution-changed` to `shared/findings.yaml` (after `refactor.unencodable`), text verbatim
      from design decision 28; run `scripts/sync-shared`; add the key and text to the table in
      `python/tests/test_contract.py` next to `refactor.unencodable`. Verify: `scripts/sync-shared --check` passes;
      `uv run pytest -q tests/test_contract.py` passes.
- [x] 9.2 Conformance case `refactor-move-symbol-builtin-rebound-in-destination` (scenario "Moved code reads a builtin
      the destination rebinds"). Copy the layout of `conformance/cases/refactor-move-symbol-unencodable-destination/`.
      Fixture: `pkg/__init__.py` empty; `pkg/a.py` = `def count(items):\n    return len(items)\n`; `pkg/b.py` =
      `len = 3\n`. Args: `--apply move-symbol --file pkg/a.py --symbol count --dest pkg/b.py`. Expect exit 1, `files`
      `pkg/a.py` and `pkg/b.py` unchanged, empty `stdout`, `stderr` exactly the four lines `[resolve]`, `[checks]`,
      `[references]`, `pkg/b.py:2: len would not resolve as it does now, so nothing was refactored; move it by hand`.
      Verify: fails today (the tool exits 0 and moves the function).
- [x] 9.3 Conformance case `refactor-rename-unencodable` (scenario "Rename into an encoding that cannot hold the new
      name"). Fixture: `pkg/__init__.py` empty; `pkg/a.py` = `# coding: ascii\nvalue = 1\nprint(value)\n`. Args:
      `--apply rename --file pkg/a.py --symbol value --new-name valué`. Expect exit 1, `pkg/a.py` unchanged, empty
      `stdout`, `stderr` = the progress lines this rename prints before its changes are built, then
      `pkg/a.py cannot hold its new text in its encoding ascii, so nothing was refactored`. Take the progress lines
      from a run of the same fixture with `--new-name valu` (dry run), keeping only the lines printed before the diff;
      write the file by hand. Verify: fails today with a `UnicodeEncodeError` traceback.
- [x] 9.4 List both cases in `conformance/INVENTORY.md`: one new row under the `dr-refactor` section, starting
      `*(new)* Python refactors check their output before writing:`, exit `1`, saying what each case pins, with
      both case ids in backticks in its Cases column (rows hold several ids; the test checks ids). Verify:
      `uv run pytest -q tests/test_conformance.py -k "inventory or builtin_rebound or rename_unencodable"` collects
      them, and only the two new cases fail.
- [x] 9.5 New `python/tests/test_output_check.py`, unit tests of `output_check.checked_write` (design decision 27) over
      a `Snapshot` of a `tmp_path` project: (a) a text that encodes, decodes to itself and parses returns a
      `FileWrite` whose `old` is the file's bytes and `new` its encoded text, a byte order mark kept; (b) a text the
      file's encoding cannot hold raises `RefactorError` with the `refactor.unencodable` message naming the file and
      its encoding; (c) scenario "New bytes that decode to another text are refused": file `# coding: latin-1\nx =
      "é"\n`, new text `# coding: utf-8\nx = "é"\n` raises `refactor.unencodable` naming the file and `utf-8`; (d)
      scenario "Output that does not parse is refused": a file that parsed, new text `def f(:\n`, raises
      `refactor.unparsable` naming the file; (e) a file that did not parse before is not parse-checked; (f) a
      non-Python file (`notes.md`) is not parse-checked. Verify: all fail today with `ModuleNotFoundError`.
- [x] 9.6 In `python/tests/test_output_check.py`, the same scenario end to end, once per path: a `move-symbol` with
      `living_architecture.refactor.rope_refactor.symbol_move_texts` monkeypatched to return the real texts with
      `"def f(:\n"` appended to the destination's; a `rename` with `living_architecture.refactor.rename_map.apply_edits`
      (the name `changes_of` calls) monkeypatched to return the real result plus `"def f(:\n"`. Each exits 1 with the `refactor.unparsable` line naming that file, prints nothing on
      stdout, and leaves every file's bytes unchanged, with and without `--apply`. Verify: both fail today (exit 0,
      broken file written with `--apply`).
- [x] 9.7 New `python/tests/test_move_verify.py`, end-to-end through the CLI with the planner's texts monkeypatched
      (`rope_refactor.symbol_move_texts`, `rope_refactor.module_move_texts`) so each test injects one planner fault
      into an otherwise correct move; each asserts exit 1, the exact `refactor.resolution-changed` line, empty stdout
      and unchanged bytes, with and without `--apply`:
      (a) scenario "A read left without its binding is refused": `pkg/a.py` has `import os` and `def f(): return
      os.sep`; move `f` to `pkg/b.py`; the patch removes the `import os` line from the destination text → the finding
      names `pkg/b.py`, the line of `os.sep`, and `os.sep`;
      (b) scenario "A use that would run before the moved declaration is refused": `pkg/b.py` = `from pkg.a import
      f\nX = f()\n`; the patch rewrites the destination text to `X = f()\n\n\ndef f():\n    return 1\n` → names
      `pkg/b.py`, line 1, `f`;
      (c) scenario "A re-export that would change is refused": `pkg/__init__.py` = `from pkg.a import f`, `pkg/a.py`
      and `pkg/c.py` both define `f`; move `pkg/a.py`'s `f` to `pkg/b.py`; the patch sets the `pkg/__init__.py` text to
      `from pkg.c import f\n` → names `pkg/__init__.py`, line 1, `f`;
      (d) a missed importer: `pkg/use.py` = `from pkg.a import f\nf()\n`; the patch drops `pkg/use.py` from the
      returned texts → names `pkg/use.py`, line 2 (the old text's line, design decision 33), `f`;
      (e) `move-module` with the patch dropping an importer's rewrite: `use.py` = `import pkg.a\npkg.a.f()\n`, move
      `pkg/a.py` to an existing `dst/` → names `use.py`, line 2, `pkg.a.f`;
      (f) scenario "An export list that would change is refused": `pkg/a.py` = `__all__ = ["f"]` and `def f()`, no
      star importer; the patch returns the source text with `__all__ = ["f"]` kept → names `pkg/a.py`, line 1,
      `__all__`;
      (g) no false refusal: for each of (a)–(f) the same move without the patch exits 0; and, also without a patch,
      a project that holds `link.py`, a symlink to its own `pkg/c.py`, moves a symbol with exit 0 (skip where the
      platform cannot create symlinks).
      Verify: (a)–(f) fail today (exit 0); (g) passes today and must keep passing.
- [x] 9.8 In `python/tests/test_move_verify.py`: the check creates nothing under the project root (compare a recursive
      listing before and after a dry run and after a refused `--apply`), removes its temporary directory (patch
      `tempfile.TemporaryDirectory` in `move_verify` to record the path, assert it is gone, also after a refusal), and
      starts no language server (reuse the `no_server` fixture of `tests/test_rope_free_moves.py`; move it to
      `tests/conftest.py` if it is not importable). Verify: the temporary-directory test fails today
      (`ModuleNotFoundError`).
- [x] 9.9 Unit tests of the fingerprint in `python/tests/test_move_verify.py` (design decisions 31–32), on small
      projects through `MoveProject`: a maximal chain `pkg.a.f.attr` yields one read whose value is the declaration of
      `f` and whose tail is `attr`; a builtin is `("unbound", name)`, a parameter `("opaque", name)`; order is
      `deferred` in a function body, `bound` / `not-yet` at module level on either side of the binding, `annotation`
      for an annotation, and a star import before the read counts as a binding; a declaration's canonical value is the
      same after blank lines are inserted above it and after its file moves (through `final`); a nested declaration is
      `("local", name)`; a read of `TYPE_CHECKING` from `typing` is left out; the exports are the strings of a literal `__all__`, None
      without one. Verify: fail today (`ModuleNotFoundError`).
- [x] 9.10 The one golden that changes (design decision 36, user-approved): in
      `conformance/cases/refactor-move-symbol-qualified-self-reference-declaration/` set `expect.exit: 1`, replace
      `stdout: ignore` by an empty `stdout` file, make the expected `files/` equal the fixture (`pkg/a.py`,
      `pkg/b.py` unchanged), write `stderr` by hand as decision 36 gives it, and reword `note` and the case's
      `INVENTORY.md` text to say it is refused. Add case `refactor-move-symbol-qualified-self-reference-lambda`: the
      old fixture without `, first=pkg.a.f`; expected `pkg/b.py` = the docstring line, two blank lines, `def f(n,
      step=lambda k: f(k)):` and its body with `f(n - 1)`, no `import pkg.a`; `pkg/a.py` keeps only `g`; exit 0;
      listed in `INVENTORY.md` beside its sibling. Verify: the changed case fails today (exit 0); the lambda case
      passes today.
- [x] 9.11 Scenario "A stub that does not parse is refused", in `python/tests/test_output_check.py`: a module rename
      with `--stub` on a project whose `living-architecture.yaml` sets `refactor.python.moved_module_stub` to text that
      does not parse once filled (build the project as `tests/test_rename_map_modules.py` does for its stub tests);
      exits 1 with `refactor.unparsable` naming the old module path, nothing written or moved. Plus unit tests of
      `checked_create`: a parsing Python text returns a `FileWrite` with `old=None`; a non-Python path is not parsed.
      Verify: fails today (exit 0, the broken stub is written).

## 10. Validity check (pr-implement)

- [x] 10.1 New `python/src/living_architecture/refactor/output_check.py` with `checked_write` and
      `checked_create` exactly as design decision 27 describes; `ModuleRename.stub` returns `checked_create`'s result.
      Verify: 9.5 and 9.11 pass.
- [x] 10.2 `rename_map.changes_of` builds each write with `checked_write`; `rope_refactor._emit` does too and
      `rope_refactor._encoded` is deleted. Verify: 9.3 and 9.6 pass; `rg -n "snapshot.encode\(" python/src` shows only
      `output_check.py` and `python_project.py`, and `rg -n "FileWrite\(" python/src/living_architecture/refactor`
      shows no Python-file write built outside `output_check.py` (the baseline's in `baseline_align.py` and the
      `unchanged` reads in `rope_refactor.py` are not Python-file writes).
- [x] 10.3 Run every Python `dr-refactor` conformance case and `tests/test_rename*.py`, `tests/test_refactor*.py`,
      `tests/test_retarget.py`, `tests/test_move_edits.py`, `tests/test_rope_free_*.py`. Verify: all pass with no
      golden touched; otherwise design decision 36.

## 11. Resolver comparison (pr-implement)

- [x] 11.1 `ProjectLayout.resources()` in `python_project.py` (design decision 30), with a unit test in
      `tests/test_python_project.py`: ignored and symlinked entries are left out, directories are flagged.
- [x] 11.2 New `python/src/living_architecture/refactor/move_verify.py`: the copy and `writer.apply` into a temporary
      directory, then `MoveProject` over it (design decision 30). Verify: 9.8 passes.
- [x] 11.3 In `move_verify.py`: the fingerprint and canonical values (design decisions 31, 32, 34). Keep each function
      small (Sonar's cognitive-complexity limit applies); no dataclasses, Pydantic `BaseModel` for any record type.
      Verify: 9.9 passes.
- [x] 11.4 In `move_verify.py`: `verify` with the signature of design decision 35, the comparison and the
      choice of the first difference (design decision 33), raising `RefactorError` with
      `refactor.resolution-changed`. Verify: unit-level parts of 9.7 pass when `verify` is called directly.
- [x] 11.5 `rope_refactor._emit` calls `verify` between building the writes and `emit` (design decision 35);
      `move_symbol` and `move_module` pass what it needs. Verify: 9.2 and 9.7 pass.
- [x] 11.6 Run every Python `move-symbol` and `move-module` conformance case (112 cases named `refactor-move-*`) and
      `tests/test_move_edits.py`, `tests/test_rope_free_moves.py`. Verify: all pass with no golden touched since section 9 (9.10's case now passes as a refusal). Any other case that
      now refuses is design decision 36: STOP and show the user the case and both fingerprint entries.
      Six refused; resolved with the user as design decision 40.

## 12. Cost and docs (pr-implement)

- [x] 12.1 Measure (design decision 37): from `python/`, `uv run dr-refactor --timings move-symbol --file
      src/living_architecture/lang/position_map.py --symbol map_range --dest
      src/living_architecture/refactor/text_edits.py` (dry run), three runs each on the commit before section 11 and
      after it. Write both `total` medians here. Over the limit of decision 37: STOP and ask.
      Measured 2026-11-18 (236 files): `total` median 0.08 s without the comparison, 2.65 s with it; 1.61 s once each
      file is parsed once (decision 40).
- [x] 12.2 Docs: in `docs/refactoring-internals.md` and `plugin/languages/python.md`, where moves are described, add
      what the two checks do and what a `resolution-changed` refusal means for the caller (move it by hand, or report
      it). Show the exact wording to the user and get an OK before editing either file.
- [x] 12.3 Spec scenario "Existing refactors unchanged": add its row to `conformance/INVENTORY.md` only if the
      inventory has a place for corpus-wide statements; otherwise 10.3 and 11.6 are its evidence, recorded here.
      The inventory has rows per branch only, so 10.3 and 11.6 are the evidence.

## 13. Gates (pr-implement)

- [x] 13.1 Local test scope (la:pr "Local test scope"): the tests of sections 9–11, the files `la-affected-tests`
      prints, every `refactor-*` conformance case; `uv run ruff check src tests`; `uv run basedpyright src tests`;
      `la-typecheck`. In `node/`: `npm run lint && npm run typecheck && npm test` (the vendored `shared/` snapshot
      changed).
- [x] 13.2 `scripts/sync-shared --check`; `la-arch-check`; `la-doctor --contract-hash` equals the hash of `shared/`.
- [x] 13.3 `openspec validate dev-2311-living-architecture-python-dr-refactor-moves --strict` passes.
- [x] 13.4 Commit and push to PR #60. The commit message states the three goldens changed on purpose (9.10 and the
      two of decision 40), the new cases, and that their goldens are hand-written
      (`golden: manual`), as AGENTS.md requires.
