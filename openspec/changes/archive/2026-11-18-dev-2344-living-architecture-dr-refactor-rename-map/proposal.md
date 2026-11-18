## Why

`dr-refactor rename-map` refuses a chained rename, reports resolve-phase refusals without their entry, prints every
rules-phase refusal twice, resolves `--keep` against another base than `--with` / `--without`, and its twins disagree
on a stand-in two entries reach (DEV-2344, items 7, 16b, 18b, 26 and 27 of DEV-2340). On a 472-entry map each of these
cost a hand-made workaround or another 20 to 28 minute run.

## What Changes

- Name conflicts are checked once, on the code after the whole map. A chain or a swap of symbol names (members,
  parameters, locals, top-level names) applies. **BREAKING**: a swap in one scope, refused until now, applies.
- A collision the map alone decides, in the scope declaring an entry's symbol, is refused in `checks`, before any
  reference search.
- Every refusal of one entry (a resolution failure, a failure while computing, a name conflict) is printed as
  `refactor.entry-refusal`, naming the entry and its locator. **BREAKING**: these stderr lines change, for `rename`
  and `retarget` too.
- Each refusal is printed once: a group's under its `[rules]` line, the rest in the final report. **BREAKING**: the
  final report no longer repeats them.
- `--keep`, `--with` and `--without` resolve a relative PATH against `--project`. **BREAKING**: `--keep` no longer
  resolves against the working directory.
- With a `refactor.map-conflict`, no name-conflict check runs.
- TypeScript: a `--with` stand-in that entries with different new names reach is refused with
  `refactor.map-conflict`, as in Python.
- Module entries are unchanged: a chain of module names is still refused.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `refactor`: the rename-map name-conflict rule, the cheap checks, progress and the one-report rule, `--fail-fast`,
  `--keep`, stand-in classification sites, and the binding requirement's finding.

## Impact

- `shared/findings.yaml` (new `refactor.entry-refusal`), `shared/cli.yaml` (help of `--keep`, `--with`, `--without`),
  both twins' snapshots.
- Python twin: `refactor/rename_map.py`, `rename_union.py`, `bindings.py`, `member_namespace.py`, `sites.py`,
  `progress.py`, `module_rename.py`.
- npm twin: `refactor/rename.ts`, `bindings.ts`, `sites.ts`, `progress.ts`.
- Conformance corpus: new paired cases, and every golden pinning a resolve failure, a name conflict or a repeated
  refusal.
- `plugin/skills/deterministic-refactor/SKILL.md`, `docs/deterministic-refactoring.md`.
- No architecture model or arc42 change. Principles of `architecture/system.arc42.md` that apply: 1 (twins), 2 (texts
  from the shared contract), 3 and 4.
