## Why

The Python `dr-refactor` asks basedpyright one question at a time, again for every map entry: about eight
find-all-references requests (~19 s each) and ~3,000 per-occurrence hover and definition requests per entry, plus
per-entry walks for dict keys, blind spots and rope's occurrence search. SLayer's 158-entry DEV-1607 `rename-map` took
4 h 39 min (~106 s per entry), while one basedpyright run over all 1,607 files takes 132 s. Two resolvers (rope's
inference and basedpyright) also feed one edit set that must agree by hand.

## What Changes

- **An occurrence index, exported once per run.** A second verified preload adds an export command to la's patched
  basedpyright language server. One request walks the candidate files in-process and returns, for every occurrence of
  an old name, its kind, the declarations it resolves to (owning class, MRO, keyed kind), the receiver verdict, the
  expected class, and the facts the AST-driven rules need; string-member probes are answered by one batched second
  round. The number of export requests does not depend on the number of entries or occurrences.
- **Every rule reads the index**: references, the renamed hierarchy and stand-ins, blind spots, string members, patch
  targets, keyed edits, parameter and overload seeds. la writes every symbol-rename edit; rope locates and validates
  entries, renames modules, runs `move-*`, and resolves only the name, import and alias occurrences basedpyright
  leaves unresolved, in one batch.
- **One language server per run**, started only when needed; the entry-resolution fallback and `Literal` probes share
  it.
- **`--unsure include`** renames accesses whose receiver the checker types `Unknown`, `Any` or a union holding either;
  its warning and help text name the checker instead of rope.
- **`dr-compliance --attr`** reads the same index, so a rename and `--attr` give one blind-spot verdict.
- **A whole-run cache** outside the project (`LA_CACHE_DIR`, else the user cache directory) reuses the index when
  nothing that can change it has changed.
- A rename refuses with `refactor.rope-walk` only for modules rope still walks.
- Output is otherwise byte-identical: every existing Python rename, map, retarget, `Literal` and `--attr` golden stands.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `refactor`: "Python renames include every reference basedpyright resolves" (edits from the occurrence index, rope for
  unresolved sites), "Python refactors walk every source construct" (scoped to what rope walks), "Member renames refuse
  on unclassified stand-ins" (the Python hierarchy over the checker's MRO), "Python --attr reports Unknown and Any
  receivers" (one index); added: the occurrence index, its cache, and `--unsure include`.

## Impact

- `python/src/living_architecture/lang/`: new export preload and index client; `language_server.py` (export command,
  coordinates), `typecheck.py` (preload wiring).
- `python/src/living_architecture/refactor/`: `rename_map.py`, `rename_union.py`, `member_scan.py`, `keyed.py`,
  `literal_rename.py`, `retarget.py`, `compliance.py`.
- `shared/`: `findings.yaml` (`refactor.unsure-warning`), `cli.yaml` (`--unsure` help), `languages.yaml` (cache
  variable, export verification); twin snapshots via `scripts/sync-shared`.
- `plugin/languages/python.md`, `docs/deterministic-refactoring.md`.
- Conformance: new Python adapter cases, `refactor-rename-unsure-include`'s warning, the runner's cache isolation,
  `INVENTORY.md`.
- Python twin only; the npm twin's TypeScript refactors are unchanged.
