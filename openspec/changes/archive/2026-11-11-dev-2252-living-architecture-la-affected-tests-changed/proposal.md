## Why

The `/la:pr` stage skills run the repo's full non-integration suite locally after every change. On a large repo
that is minutes per iteration, repeated many times per PR, for tests the change cannot affect. CI runs the full
suite on every push, so the local run only needs to cover what this change can break; anything the local
selection misses, CI catches.

## What Changes

- New command `la-affected-tests --base BRANCH`: prints, one repo-relative POSIX path per line, the test files a
  change can affect, covering only the exact parts: test files the change added or modified, and test files whose
  import closure (type-only imports included) reaches a changed or deleted file. It never runs tests.
- Import resolution is file-based in both languages and needs no architecture index or config: Python matches
  dotted names against every repo file (any directory may be an import root); TypeScript resolves specifiers under
  each file's nearest `tsconfig.json`.
- Both twins implement it natively for their own language; a two-language change is the union, the other
  language's part computed by the other twin through an internal `--language` request.
- New `changes` node in both twins: base-ref resolution and the git change listing move out of the conventions
  gate, which keeps its behaviour; `la-check-conventions` and `la-affected-tests` share it. Test-file
  classification moves into the shared contract module.
- `/la:pr` skills: a new "Local test scope" section in `pr`, and `pr-tests`, `pr-implement`, `pr-review` run only
  the tests in that scope locally instead of the full suite.
- `/la:pr` skills: pushing the change's own branch no longer needs the user's go-ahead; only opening a PR does.

## Capabilities

### New Capabilities
- `affected-tests`: the `la-affected-tests` command — its surface, the changed set, the import graph and its
  resolution rules per language, the reverse walk, the output and exit codes, and the twin split.

### Modified Capabilities
- `twin-forwarding`: `la-affected-tests` joins the neutral commands that reach the other language only through
  language requests.

## Impact

- `shared/`: `cli.yaml` (new command), `findings.yaml` (new `affected.*` texts; git texts move to `changes.*`),
  a new schema for the internal request/response documents; snapshots re-synced in both twins.
- Python twin: new packages `living_architecture.changes` and `living_architecture.affected`; `lang` gains the
  all-imports scans and file resolution; `conventions.gate` uses `changes`; `contract` gains `is_test_file`.
- npm twin: the same split under `node/src/changes`, `node/src/affected`, `node/src/lang`, `node/src/contract`.
- `architecture/model.c4`: nodes `changes` and `affected` with their arrows in both roots; regenerated diagrams in
  `architecture/system.arc42.md`.
- `plugin/skills/pr`, `pr-tests`, `pr-implement`, `pr-review`; `docs/commands.md`, `docs/how-it-works.md`.
- Conformance corpus: new git-scripted cases for the command, listed in `conformance/INVENTORY.md`.
