## Why

A long `dr-refactor` run is silent until it ends, and can then fail for a reason it could have seen at the start: a
158-entry SLayer map ran 4 h 39 min and exited 2 on `--keep architecture matches nothing this rename touches`. Every
check raises where it fires, the first error wins, and checks that need no references run after the expensive work.

## What Changes

- Every `dr-refactor` subcommand runs in announced phases (`resolve`, `checks`, `references`, `rules`, `baseline`,
  `write`) and prints its progress on stderr: each phase as it starts, each entry as its reference search starts, and
  each entry's result (`clean`, or its refusals) as soon as it is done. Always on.
- The cheap checks run before any reference is resolved, in the `checks` phase: unresolved and invalid map entries,
  `--keep`/`--with`/`--without` sites that do not exist, keeps whose sites hold no old name, Python walker gaps in the
  candidate files, and probes that the checkers run. A failure there refuses at once, listing every failure.
- Every refusal of a run is collected and reported in one report, never one per run; the exit code is the maximum
  of the findings' codes.
- New `--fail-fast` option on `rename`, `retarget` and `rename-map`: stop at the first refusal found after the checks.
  The default computes every entry and reports every refusal.
- A failed external checker (the configured Python type checker, the basedpyright language server) prints its cause
  after its finding: exit code and stderr, the start error, or its error answer.
- New findings: `refactor.progress-*`, `refactor.site-missing`, `refactor.checker-*`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `refactor`: progress reporting, the phase order with early checks, one combined refusal report, `--fail-fast`, and
  checker failure causes.

## Impact

- `shared/findings.yaml`, `shared/cli.yaml` (new option), synced into both twins.
- Python twin: `refactor/` (`rename_map.py`, `rename_union.py`, `rope_refactor.py`, `sites.py`, `map_file.py`,
  `baseline_align.py`, a new progress reporter and refusal collector), `lang/language_server.py` (captured stderr,
  carried cause), `typecheck` (`CommandError` carries the exit code).
- npm twin: `refactor/` (`rename.ts`, `session.ts`, `typescript.ts`, `index.ts`, `map.ts`, `sites.ts`).
- Conformance: every `dr-refactor` case's stderr golden re-blessed for the progress lines; new cases per early
  refusal, combined report, `--fail-fast` and checker cause; `conformance/INVENTORY.md`.
- `docs/deterministic-refactoring.md`.
