## Why

`move-symbol` and `move-module` already write every edit themselves (`move_edits.py`), but rope still finds and
resolves their references, supplies the moved region and the moved code's imports, locates the moved symbol, and holds
their project model and header text. These are the last rope uses after DEV-2310; they keep rope's walker alive for every
move, crash with tracebacks on locators rope casts wrongly, and break code around guarded imports, overloads and
namespace packages. This is step 5 of DEV-2306's plan; DEV-2312 then removes rope.

## What Changes

- **References from la's static resolver**: each name or attribute load spelling the moved name is resolved by Python's
  scoping over the project's own modules. The move planner keeps one scope model, the resolver's; its own is deleted.
- **The moved symbol located without rope**: a site on a top-level declaration of `--file` moves it. A site on an
  import binding or a reference (which rope followed into the declaring file), a method, local, parameter, module name,
  multi-name or block-bound assignment, or a repeated top-level binding refuses with `refactor.not-movable`, as the
  TypeScript twin does, instead of crashing. An `@overload` group moves as one unit.
- **The moved region and imports from the AST and `tokenize`**, reproducing rope's output on every existing golden,
  plus new rules where rope breaks code:
  - an import inside a block of the source is never removed;
  - a needed `TYPE_CHECKING` import is added under an `if TYPE_CHECKING:` block of the destination; one under any
    other guard refuses with the new finding `refactor.guarded-import`;
  - the source's `from __future__` imports the destination lacks are added;
  - a relative import inside the moved code is recomputed for the destination.
- **la's project model for moves**: snapshot texts, text edits and file moves through the shared `emit`; every
  inserted line and the moved text take the target file's newline convention.
- **Namespace packages**: the static resolver resolves through a directory without `__init__.py`; `move-module` moves
  one, and module renames rewrite chains through one.
- **Move texts from the shared contract** under neutral keys: `refactor.move-symbol-header`,
  `refactor.move-module-header`, `refactor.moved` (renamed from their `ts-` keys; texts unchanged).
- Moves start no language server. rope's only remaining part is the walker-gap check of a move's `checks` phase.
- Output stays byte-identical on every existing Python `move-symbol` and `move-module` golden.
- **Every Python refactor checks its output before writing** (second pass, design decisions 26–38): a written file
  must still parse and its bytes must decode to the intended text; a move also resolves the project as it would leave
  it and refuses with the new finding `refactor.resolution-changed` when a name would resolve differently. A case no
  edit rule covers then refuses instead of writing wrong code.

## Capabilities

### New Capabilities

### Modified Capabilities
- `refactor`: Python moves resolve statically without rope; `move-symbol` moves one top-level declaration (locators,
  movable forms, overload groups, region); moves' import rules for guarded, `__future__` and relative imports and the
  destination import order; namespace packages resolve for moves and module renames; every Python refactor checks its
  output before writing.

## Impact

- `python/src/living_architecture/refactor/`: `move_edits.py` (rewritten onto the static resolver), `rope_refactor.py`
  (moves leave rope's project, resources and `create_move`), `rename_map.py` (`source_bytes`, `change_set_writes`
  deleted), `static_resolver.py` (import statement and item per binding; namespace packages), `python_project.py`
  (namespace packages), `diff_render.py` (move text from the contract).
- `shared/findings.yaml`: three keys renamed, `refactor.guarded-import` added; `scripts/sync-shared`.
- Output checks: new `refactor/output_check.py` and `refactor/move_verify.py`; `rename_map.changes_of` and
  `rope_refactor._emit` build their writes through `output_check`; `python_project.ProjectLayout.resources`;
  `shared/findings.yaml` gains `refactor.resolution-changed`.
- `node/src/refactor/`: `typescript.ts`, `session.ts` use the renamed keys.
- `conformance/`: new Python adapter cases; `INVENTORY.md`.
- Tests: `python/tests/test_move_edits.py` onto the new entry points; `python/tests/test_contract.py` key names.
- Docs: `plugin/languages/python.md`, `docs/deterministic-refactoring.md`, `docs/how-it-works.md`,
  `docs/living-architecture-in-questions-and-answers.md`, `docs/refactoring-internals.md`.
- No model or arc42 change; no new dependency; rope stays installed until DEV-2312.
