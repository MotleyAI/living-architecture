## 1. Tests first (pr-tests)

- [ ] 1.1 Add Python adapter conformance cases with the real checker, one per scenario of "Python baseline
  realignment" that a command run can show: `typecheck-realign-line-edit`, `-committed-edit`, `-beside-new-error`,
  `-new-in-added-text`, `-same-shape-out-of-order`, `-rename-edited`, `-rename-only`, `-nothing`, `-checker-failed`,
  `-malformed-baseline`. Git steps: `commit`, then `write:` / `rename:` for the edit. Hand-written goldens
  (`golden: manual`), `expect.files` on `.basedpyright/baseline.json`. Verify: each fails on the unknown option.
- [ ] 1.2 Add neutral cases `typecheck-realign-bad-ref` and `typecheck-realign-with-write`, a TypeScript case
  `typecheck-realign-ts-plain`, and a mixed case run through each twin (`scripts/conformance-cross`). Verify: fail.
- [ ] 1.3 Add hint cases: baseline present with a new error (hint), no baseline (no hint), failing realign run (no
  hint). Verify: the first fails for the missing line.
- [ ] 1.4 List every new case in `conformance/INVENTORY.md`; each new `findings.yaml` template has a golden.
- [ ] 1.5 Unit tests in `python/tests`: the backward mapping, order-consistent entry taking (identical-shaped
  entries, each used once, out-of-order refused), rename key moves and the merge onto a key with entries, a non-BMP
  character before the edit, and the moved functions under `living_architecture.lang`. Verify: fail on import.
- [ ] 1.6 npm twin unit tests (Vitest): the option is parsed, `REF` is validated, and the Python section is
  forwarded with `--realign-from REF`. Verify: fail.

## 2. Shared contract

- [ ] 2.1 `shared/cli.yaml`: add `--realign-from` (string, metavar `REF`) to `la-typecheck` with the approved
  help (design.md decision 15). `shared/findings.yaml`: add the three approved texts verbatim.
- [ ] 2.2 Run `scripts/sync-shared`; verify `scripts/sync-shared --check` passes and the drift test is green.
- [ ] 2.3 Update the `typecheck-help` golden (reason: new option) and verify the case passes in both twins.

## 3. PyPI twin

- [ ] 3.1 Move the pure baseline pieces from `refactor/baseline_align.py` and `refactor/position_map.py` to `lang`
  (design.md decision 5) with `dr-refactor` over the moved names, following the `la:deterministic-refactor`
  procedure. Verify: the `refactor-baseline-*` cases and `test_baseline_align.py` pass unchanged.
- [ ] 3.2 Add the commit check and any git read the realignment needs to `changes`; apply the approved model edit
  for the `python` root (design.md decision 6) with the import that needs it. Verify: `la-arch-check` passes.
- [ ] 3.3 Implement the realignment in `typecheck` over the `lang` pieces: renames, candidates, the two checker
  runs, the order-consistent backward mapping, the write and `typecheck.realign`, then the normal check. Verify:
  the 1.1 cases and 1.5 tests pass.
- [ ] 3.4 Wire the option in the CLI: the usage error with `--write-baseline`, `typecheck.bad-ref` before any
  header, the flag passed to a forwarded Python section only. Verify: the 1.2 cases pass.
- [ ] 3.5 Print `typecheck.realign-hint` after a failing plain Python check with a baseline file. Update the
  existing Python goldens that gain the line (reason: the hint) and review the golden diff. Verify: 1.3 passes.

## 4. npm twin

- [ ] 4.1 Parse the option, validate `REF` through `changes`, forward `--realign-from REF` with the Python section,
  leave the TypeScript check unchanged; apply the approved model edit for the `typescript` root. Verify: the 1.6
  tests and `npm run build && npm run conformance` pass.

## 5. Architecture and docs

- [ ] 5.1 Regenerate the `system` and `npm` diagrams (`la-arch-diagrams`). Verify: `la-arch-check` passes from
  either twin with `legacy_arrows.baseline` still 0.
- [ ] 5.2 Document `--realign-from` in `docs/commands.md`. Verify: the docs checks in the test suite pass.

## 6. Gates

- [ ] 6.1 Run the local test scope in both twins, `scripts/conformance-cross`, ruff, basedpyright, `npm run lint`
  and `npm run typecheck`, `la-typecheck`, and `npx likec4 validate`. Verify: all green.
