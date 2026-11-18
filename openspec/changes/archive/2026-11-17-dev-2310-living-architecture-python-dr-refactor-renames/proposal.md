## Why

After DEV-2301 the checker's occurrence index finds every occurrence of a Python rename, yet `rename`, `rename-map`
and `retarget` still run rope for everything around it: the project model, locating each entry, the fallback for names
the checker leaves unresolved, the new-name conflict check's class graph, retarget's lookups and module renames. rope is
a second, weaker resolver beside basedpyright, its offsets live in a newline-normalised text that la converts in both
directions, and a name neither resolver understands is skipped with no trace. DEV-2306 measured that la's static
resolver and the AST give rope's answer for each of these roles; this change moves the rename path onto them (steps 1–4
of DEV-2306's plan). Moves keep rope until DEV-2311; DEV-2312 removes it.

## What Changes

- **la's own project model** for renames: la's file list, snapshot texts, text edits plus a file-move list, a verbatim
  port of rope's source-folder, module-name and module-lookup rules, and la's own diff rendering. The newline-normalised
  text and its offset conversions go.
- **Entries located without rope**: kind and canonical key from the AST, import bindings and references through the
  static resolver, else the language server's definition; a Python keyword as the new name refuses as today.
- **Unresolved names**: the static resolver replaces rope for the occurrences the checker resolves to nothing; an
  occurrence it also cannot resolve is listed with the new finding `refactor.unresolved-name` (stderr, exit unchanged).
- **The new-name conflict check** reads the checker's class graph through the occurrence index (library bases
  included); retarget's lookups move to the static resolver.
- **Module renames without rope**: sites from import syntax plus the static resolver, rope's self-alias rule kept, the
  existing name-taken and binding checks unchanged.
- **Walker gaps**: renames no longer run the walker-gap check (rope walks no module of a rename); moves keep it.
- **`--offset`** counts characters of the file as read, CRLF included, as the npm twin and `shared/cli.yaml` define it.
- Output stays byte-identical on every existing Python `rename` / `rename-map` / `retarget` golden.

## Capabilities

### New Capabilities

### Modified Capabilities
- `refactor`: rope plays no part in a Python rename; unresolved names resolve statically and are listed when nothing
  resolves them; module-rename sites and the self-alias rule are specified; walker gaps are checked for moves only;
  rename refusals no longer name rope; `--offset` counts raw characters.

## Impact

- `python/src/living_architecture/refactor/`: `rename_map.py`, `rename_union.py`, `retarget.py`, `member_namespace.py`,
  `locators.py`, `literal_rename.py`, `baseline_align.py`, `rope_refactor.py` (module rename and `emit` move out of
  rope's types), `patch_targets.py` (source folders), `static_resolver.py`, `symbol_path.py`, `hierarchy.py`,
  `occurrence_index.py`; `lang/pyright_export.cjs` and `lang/language_server.py` (one new batched fact kind).
- `shared/findings.yaml`: `refactor.unresolved-name`; `scripts/sync-shared`.
- `conformance/`: new adapter cases and one paired case; `INVENTORY.md`.
- Python unit tests that build rope objects for renames.
- No model or arc42 change; no new dependency; rope stays installed.
