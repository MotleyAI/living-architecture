## Why

DEV-1607 renamed about 100 SLayer symbols with `dr-refactor`, and the hand work around the tool took longer than
the renames. Symbols were addressed by position (`--line`/`--col` went stale after each apply; `--name` guessed),
one per invocation with a full gate each, every rename broke the type-check baseline, deprecated aliases hid
old-name code, and `Literal` values, compound names and `dr-mock-lint` comparisons needed scripts. The fix is to
address symbols by a stable path, make a map of entries the unit of work, and make every refactor keep the
baseline aligned.

## What Changes

- **BREAKING**: `--name` is removed from `rename` and `move-symbol`; `--symbol Q` names a declaration by its path
  inside `--file` (`Class.method`, `func.<locals>.inner`, `Class.method(param)`, `Alias['value']`). No match or
  several exit 2 listing the candidates. `--offset`, `--line` and `--symbol` are mutually exclusive.
- `dr-refactor rename-map MAP`: a YAML list of rename and retarget entries, resolved against the pre-map code,
  computed on one snapshot with every DEV-2292 rename rule over the union, printed as one diff with one combined
  refusal report, and written all or nothing. `rename` and `retarget` are its one-entry forms.
- `dr-refactor retarget --file F --symbol ALIAS --target TARGET`: references resolving to an alias are rewritten to
  name its target in the same class or module; the alias stays.
- Every refactor (`rename`, `rename-map`, `retarget`, `move-symbol`, `move-module`) keeps the language's type-check
  baseline aligned, in dry-run and apply: Python through the configured basedpyright command, TypeScript through
  the bundled language service.
- A `Literal` member rename rewrites the strings the checker types by that literal type (Python: a checker probe;
  TypeScript: the language service's rename) and lists every other string equal to the old value as a leftover.
- With `--docs`, declarations whose name contains the old name as a word sequence are listed as leftovers.
- `dr-compliance --attr` is repeatable, one scan for every name.
- `dr-mock-lint` becomes a parsed command (`--help` works) with `--base BRANCH`, reporting only findings the base
  branch lacks.
- The CLI manifest gains an `exclusive` key (options of which at most one may be given).
- Skills `la:deterministic-refactor`, `la:make-refactor-target-compliant` and both language docs describe the new
  commands; the procedure uses the qualified locator and one map per gate.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `refactor`: qualified locators, rename maps, retarget, baseline alignment, `Literal` member renames, compound-name
  leftovers, repeatable `--attr`, `dr-mock-lint --base`; the routing, output-format, TypeScript locator, TypeScript
  move, dry-run, async and parameter-kind requirements drop `--name`.
- `twin-forwarding`: the forwarding requirement's `dr-refactor` scenario uses `--symbol`.
- `shared-contract`: the CLI manifest's `exclusive` key.

## Impact

- `shared/`: `cli.yaml` (`--symbol`, `exclusive`, `rename-map`, `retarget`, repeatable `--attr`, parsed
  `dr-mock-lint` with `--base`), `findings.yaml` (new `refactor.*` templates), `schema/rename-map.schema.json`;
  vendored snapshots via `scripts/sync-shared`.
- Python twin: `living_architecture.refactor` (locator, map engine, retarget, position maps, baseline aligner,
  `Literal` probe, compound names, mock-lint `--base`), `cli` (manifest `exclusive`); npm twin: `src/refactor`,
  `src/cli`, `src/lang/tsc.ts` exports.
- `architecture/model.c4`: `python { refactor -> typecheck; refactor -> changes }`, `typescript { refactor ->
  changes }`; diagrams in `architecture/system.arc42.md` regenerated.
- `conformance/cases/`: the cases using `--name` migrate to `--symbol`; new cases; `conformance/INVENTORY.md`.
- `plugin/skills/deterministic-refactor`, `plugin/skills/make-refactor-target-compliant`, `plugin/languages/*.md`,
  `docs/deterministic-refactoring.md`, `docs/commands.md`.
- Builds on DEV-2292 (and DEV-2289, merged into it); implementation starts once DEV-2292's implementation is merged
  into this branch; archives after both.
- Post-merge: a minor release, pinned in SLayer.
