## 1. Tests (pr-tests stage; failing until implemented)

- [x] 1.1 New fixture `conformance/fixtures/refactor-references/` (Python, git-initialised as the existing
  `refactor-pkg` cases are): `pkg/sql/{__init__,client,dialects,engine_factory,engine}.py`, an empty
  `pkg/database/__init__.py`, and one file per shape under `tests/`. The shapes are: an importorskip-gated import, an
  interleaved `sys.path.insert`, an unsorted block, a single-line and a parenthesized multi-name from-import (a trailing
  comma, per-name comments), a function-local import with `# ALLOW(import-not-top)`, a chain through another module
  (`sql_client.engine_factory`), a self-alias, a dotted use with its own `import pkg.sql.client`, a package-attribute
  use through `import pkg.sql as sql_pkg`, a sibling's `from . import client`, a `from ..sql import client`, the
  moved module's own `from . import dialects`, and the import edit forms (a backslash continuation, a semicolon tail, a
  CRLF file, a file without a final newline, non-ASCII text before the import on its line). Verify by running today's
  `dr-refactor` on it and seeing the reflow and the self-alias crash.
- [x] 1.2 Python adapter cases (`golden: manual`, hand-written diffs per the spec scenarios):
  `refactor-move-module-references` (dry-run of `pkg/sql/client.py` → `pkg/database` over 1.1);
  `refactor-move-module-references-apply` (same with `--apply`, `expect.files` pinning the written files);
  `refactor-move-module-package-relative` (package `pkg/sql` → `pkg/database`, internal relative imports unchanged);
  `refactor-move-module-cross-top-level` (relative import becomes absolute);
  `refactor-rename-module-references` (`rename` of module `client` → `cli2` over 1.1, rope's current output).
  Verify that each fails today, except `refactor-rename-module-references`, which must pass today.
- [x] 1.3 `move-symbol` fixture overlay plus adapter cases (`golden: manual`): `refactor-move-symbol-references` moves `f`
  from `pkg/a.py` to `pkg/b.py`. It covers a gated importer, a multi-name split, a function-local import, an alias used
  only as `pa.f()`, an alias with a surviving `pa.g()`, a star-import consumer, `pkg/__init__.py` with
  `from pkg.a import f as public_f`, `pkg/a.py`'s `__all__` listing `"f"`, the source still calling `f` after the move,
  `f` using `os` and `sys`, and a destination with an unsorted, importorskip-gated block that already has `import sys`.
  Then the `refactor-move-symbol-name-conflict-{assignment,parameter,aliased-import,enclosing-scope}` cases: exit 1
  with the name-conflict finding on stderr, stdout empty, no file changed. Verify that each fails today.
- [x] 1.4 TS adapter cases (`golden: manual`, pinning today's npm output; run the commands first and check the diffs
  match the spec): `refactor-ts-move-symbol-split-in-place` and `refactor-ts-move-module-references` (a multi-name
  import, a statement between import groups, an unsorted block). Verify that they pass today.
- [x] 1.5 List every new case in `conformance/INVENTORY.md` under `dr-refactor` / `dr-refactor: TypeScript`, marked
  *(new)*. Verify `tests/test_conformance.py`'s inventory check passes.
- [x] 1.6 Python unit tests for the planner (new `python/tests/test_move_edits.py`). Cover rule classification by
  resolved object (rules 1–3, an explicit `__init__` binding versus an implicit package attribute); token-level import
  edits (comma and comment ownership, the parenthesized own-line removal, a semicolon tail, a backslash continuation,
  CRLF, no final newline); the new-statement position; byte-to-character offsets on non-ASCII lines; relative import
  recomputation (same package, parent, files moving together, across top-level packages); exact import removal; the
  leading import block (docstring, `__future__`, a gate); and the same-object check for added imports. Verify that
  they fail today.
- [x] 1.7 Codex review of the tests against this change (pr-tests Step 2); resolve findings with the user.

## 2. shared/

- [x] 2.1 `shared/findings.yaml`: add, after `refactor.rope-walk`, the approved wording `refactor.name-conflict: '{name}
  already names something else at {path}:{line}, so nothing was refactored'` (user, approved wording). Run
  `scripts/sync-shared`, and verify `scripts/sync-shared --check` passes and both snapshots' `CONTRACT_HASH` match.

## 3. Python twin

- [x] 3.1 New planner module in `python/src/living_architecture/refactor/`. It classifies each rope occurrence
  (`create_finder(..., imports=True)`, `get_primary_and_pyname()`) into rules 1–3 by resolved objects (design
  decisions 10 and 12). Verify the 1.6 classification tests pass.
- [x] 3.2 Import statement edits on `tokenize` tokens: a path rewrite, the removal of one name, an inserted
  statement after the statement's physical end line, and positions through `rope_patches.char_offset` (design 15 and
  16). Verify the 1.6 token and offset tests pass.
- [x] 3.3 Relative import recomputation (design 5 and 17). Verify the 1.6 relative tests pass.
- [x] 3.4 Rule-3 rewrites, the adjacent import, the exact removal (design 3 and 14), and the same-object check with the
  `refactor.name-conflict` refusal (design 11, exit 1, nothing written). Verify the 1.6 tests pass.
- [x] 3.5 `rope_refactor.move_module` builds its `ChangeSet` from the planner (`ChangeContents` per touched file,
  including the moved module's own relative imports, plus `MoveResource`). Verify the `refactor-move-module-*` cases
  and the existing `refactor-move-module-*` goldens pass.
- [x] 3.6 `rope_refactor.move_symbol` builds its `ChangeSet` from the planner. It reuses rope's moving region and
  `moving_code_with_imports` for what moves (design 6 and the Risks section). Destination imports go after the leading
  import block, the destination's import of the symbol is removed, and the source's `__all__` entry and remaining use
  are handled (design 13). Verify `refactor-move-symbol-*` and the existing `refactor-move-symbol-apply` golden pass.
- [x] 3.7 Check `docs/deterministic-refactoring.md`, the repo `README.md` and the `deterministic-refactor` /
  `arch-cleanup` skills for text that mentions the old reflow, or a workaround such as restoring import blocks after
  a move. Docs: align them. Skills: present the exact wording to the user before editing (never edit a skill
  unapproved). Verify with `rg -n -i "reflow|import block|restore.*import" docs plugin README.md`.

## 4. Verify

- [x] 4.1 Python: in `python/`, `uv run pytest -q`, `uv run ruff check src tests` and `uv run basedpyright src tests`
  are green.
- [x] 4.2 npm: in `node/`, `npm run lint && npm run typecheck`, `npm test`, and `npm run build && npm run conformance`
  are green.
- [x] 4.3 `scripts/conformance-cross`, `scripts/sync-shared --check` and `la-arch-check` are green.
- [x] 4.4 SLayer acceptance. Clone `~/GitHub/SLayer/slayer` `main` into the scratchpad, add an empty
  `slayer/database/__init__.py`, commit it there, and run `dr-refactor move-module --module slayer/sql/client.py --dest
  slayer/database` (a dry-run). Verify the diff holds only `slayer.sql.client` → `slayer.database.client` edits, plus
  any rule-3 adjacent import (design 8). It must not hoist the `importorskip`-gated imports in
  `tests/integration/test_integration_{clickhouse,sqlserver,snowflake}.py` or `tests/test_importer_source_names.py`,
  move the `importorskip` calls, or change `slayer/dbt/converter.py`. Record the outcome in a Linear comment on the
  issue.
