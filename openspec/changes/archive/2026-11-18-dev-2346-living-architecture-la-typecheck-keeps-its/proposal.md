## Why

basedpyright's baseline matches an error by its rule and its column range under a path key. A script or a hand
edit that changes the text earlier on a baselined line, or moves the file, unmatches the entry, and `la-typecheck`
reports the error as new. `dr-refactor` realigns the baseline for its own edits; nothing does it for any other edit
(DEV-2340 item 24: in DEV-2318, 88 respelled constructor sites all came back as new errors).

Reproduced on `main` with basedpyright 1.40.2: with two baselined `reportArgumentType` errors on
`return f(1, "x") + len(3)`, changing the line to `return f(int(1), "x") + len(3)` makes `la-typecheck` exit 1 and
list both. The TypeScript baseline is keyed by file, code and message, so it is not affected.

## What Changes

- `la-typecheck` gains `--realign-from REF`: given a commit where the baseline matched, it moves each Python
  baseline entry to where its error is now (through the text diff of each file since `REF`, and through the renames
  git reports since `REF`), writes the baseline, then checks as usual.
- A really new error is never taken into the baseline: an entry moves only to a diagnostic whose range maps back to
  the entry's columns at `REF`, in an order consistent with the baseline's.
- `--realign-from` with `--write-baseline` is a usage error; a `REF` that is not a commit exits 2.
- A failing Python check without the flag, in a repo with a baseline, ends with a hint naming the flag.
- New shared texts `typecheck.bad-ref`, `typecheck.realign` and `typecheck.realign-hint`.
- The pure baseline pieces `dr-refactor` uses (entry matching and pairing, text edits, range mapping) move from
  `refactor` to `lang`, so both callers share one mapping rule. `dr-refactor`'s behaviour does not change.
- Architecture model: `typecheck -> changes` in both roots.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `typecheck`: the baseline contract names realignment as the one change besides shrinking; new requirements for
  `--realign-from` and for the hint.

## Impact

- `shared/cli.yaml`, `shared/findings.yaml` and every twin's snapshot (`scripts/sync-shared`); the contract hash.
- PyPI twin: `typecheck`, `lang`, `refactor` (imports only), `cli`.
- npm twin: `typecheck` (flag, `REF` validation, forwarding), `cli`.
- `architecture/model.c4`, `architecture/system.arc42.md` (regenerated diagrams).
- Conformance corpus: new `typecheck-realign-*` cases, the `typecheck-help` golden, and existing Python goldens
  that exit 1 with a baseline present (they gain the hint line).
- `docs/commands.md`.
