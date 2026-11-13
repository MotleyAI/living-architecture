## 0. Calibration (read before tests and code)

- Probe scripts from planning: an LSP client driving `basedpyright-langserver --stdio` (`initialize`, `didOpen`,
  `textDocument/references`, `textDocument/rename`) was enough to reproduce every Context fact in design.md. The
  server sends `workspace/configuration` requests; answering each item with `null` keeps the project's own config.
- Test fixtures need `pydantic` resolvable by basedpyright. The PyPI twin's venv has it (a dependency). Check which
  `python` the conformance environment puts first on PATH (the twin's bin dir is before host tools) and that the
  server finds `pydantic` through it; if not, the fixture's `pyproject.toml` must name the venv in
  `[tool.basedpyright]`. Settle this before writing goldens.
- Forcing a language-server failure deterministically: `NODE_OPTIONS=--require /nonexistent.js` in the case's `env`
  makes Node exit at start (the la preload is appended after the inherited value). Confirm the exact behaviour before
  relying on it for the `refactor.pyright-failed` and `compliance.pyright-failed` goldens.
- The preload's existing protocol (`LA_PYRIGHT_PATCH_RESULT`, `LA_PYRIGHT_PATCH_VERSIONS`, result file) is reused for
  the server: it acts on `dist/pyright-langserver.js` exactly as on `dist/pyright.js`; the result is read after
  `initialize`.
- LSP positions are UTF-16 code units; convert against the snapshot text (design decision 19).
- Every new `findings.yaml` text and the changed `compliance.attr-blindspot` must be produced by a golden; the
  approved wordings are design.md decisions 35–38, verbatim.

## 1. Contract, architecture and packaging

- [ ] 1.1 Add `refactor.pyright-failed`, `refactor.unresolved-base`, `compliance.pyright-failed` and the new
      `compliance.attr-blindspot` (design decisions 35–38, verbatim) to `shared/findings.yaml`; remove
      `compliance.ts-attr-blindspot`; run `scripts/sync-shared`; verify `scripts/sync-shared --check`,
      `test_contract.py` and `test_sync_shared.py` pass.
- [ ] 1.2 Add `refactor -> lang` to the python root of `architecture/model.c4`; run `la-arch-diagrams` to refresh the
      embedded diagram in `system.arc42.md`; verify `la-arch-check` and LikeC4 validation pass.
- [ ] 1.3 Move `basedpyright==1.40.2` into `dependencies` in `python/pyproject.toml`, remove the `verify` extra,
      refresh `uv.lock`; verify `uv sync` and the packaging tests pass.

## 2. Tests (pr-tests stage)

- [x] 2.1 Unit tests for the language-server session in `python.lang`: start with the patch (result `patched`), the
      isolation environment and working directory, UTF-16 → character conversion (astral, BMP non-ASCII, CRLF, no
      final newline), failure to start, exit mid-session, an unpatched server, `workspace/configuration` answers.
- [x] 2.2 Preload tests: a fake `dist/pyright-langserver.js` defining the version module is patched like
      `dist/pyright.js`; the CLI bundle tests still pass.
- [x] 2.3 Unit tests for the rename union: per-declaration seeding under both hierarchy modes, span merge, overlap
      refusal, a file changed before the write aborts with nothing written, module renames untouched.
- [x] 2.4 Unit tests for the keyed-class rewrites: every target of "Python field renames rewrite typed dict keys"
      and "…keyword arguments of the owning class", each with its negative (Unknown, Any, type variable, other
      union, same-named field of another class, rebound `cls`, unrelated `model_construct`, alias, alias generator,
      non-plain literal, single-binding variable with each disqualifying use), nested containers, collisions.
- [x] 2.5 Unit tests for the `async def` patch (definition, override, inferred call, module-level function; each
      locator) and for `RefactoringError` → `refactor.cannot-rename`.
- [x] 2.6 Unit tests for Python `--attr`: each receiver kind of the spec, `Model | Unknown`, multiline and chained
      receivers, collapsing, ordering, dedup, server failure exit 2.
- [x] 2.7 Conformance adapter cases (python), one per scenario of the delta spec's Python requirements, including
      `refactor.pyright-failed`, `refactor.unresolved-base` and `refactor.cannot-rename` goldens, dry-run and apply
      variants for failures after rope computed its changes, the whole-tree snapshot for dry-runs, and the
      `sitecustomize` marker case; update the existing Python `--attr` golden to the new text and add the
      `compliance.pyright-failed` golden.
- [ ] 2.8 A TypeScript adapter case for contextually typed object-literal keys (renamed) next to an untyped literal
      (unchanged); confirm the existing TS `--attr` golden is unchanged under the shared template.
- [ ] 2.9 List every new case in `conformance/INVENTORY.md`, and retire the `ts-attr-blindspot` row in favour of the
      shared template; verify every findings template is produced by a golden.

## 3. Implementation

- [ ] 3.1 Extend the pyright#11919 preload to `dist/pyright-langserver.js`; verify 2.2.
- [ ] 3.2 Add the language-server session to `python.lang` (launch from la's environment, isolation environment,
      patch, UTF-16 conversion, `references` / `definition` / `typeDefinition` / `hover`, one session per command);
      verify 2.1.
- [ ] 3.3 Patch rope's function-header check for `async def` in `rope_patches.py`, with a comment naming the upstream
      rope issue (task 5.1) as its removal trigger; map `RefactoringError` to `refactor.cannot-rename`; verify 2.5.
- [ ] 3.4 Add the reference union to `rope_refactor.rename`: rope's edits as spans over one snapshot, basedpyright
      references for every renamed declaration, merge and validation, atomic write; verify 2.3 and the B1 scenarios.
- [ ] 3.5 Add the keyed-class rewrites and the `refactor.unresolved-base` refusal (syntactic prefilter, then type
      queries, cached base chains); verify 2.4.
- [ ] 3.6 Rewrite Python `--attr` in `compliance.py` on basedpyright with the shared template; switch the npm twin to
      the shared template id; verify 2.6 and 2.8.
- [ ] 3.7 Run the conformance cases of 2.7–2.9 through both twins (`scripts/conformance-cross` narrowed to them);
      verify they pass.

## 4. Docs

- [ ] 4.1 Replace the Refactoring section and the `attr-blindspot` bullet of `plugin/languages/python.md` with design
      decisions 39 and 40, verbatim.
- [ ] 4.2 Update `docs/deterministic-refactoring.md` and `docs/commands.md` (dr-refactor's basedpyright, the project
      environment, Python `--attr`) and any README mention of the `verify` extra; verify `la-check-conventions` and
      `la-count-comments` pass on the touched files.

## 5. Upstream

- [ ] 5.1 Open an issue on python-rope/rope with the `async def` repro and the root cause in
      `worder._RealFinder.is_a_class_or_function_name_in_header`; record its URL in the patch comment (3.3).
- [ ] 5.2 Open a PR on python-rope/rope with the fix and a test following rope's conventions; record its URL in the
      DEV-2287 handoff comment.

## 6. Verification

- [ ] 6.1 Run the enforcement bundle (`la-arch-check`, LikeC4 validation, `la-typecheck`) and the local test scope;
      fix until green.
- [ ] 6.2 Time a dry-run field rename (`SlayerModel.columns`) on the SLayer checkout and record the wall time and
      file count in the DEV-2287 handoff comment.
