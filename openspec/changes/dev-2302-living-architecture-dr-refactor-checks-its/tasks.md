## 1. Tests (pr-tests)

- [ ] 1.1 `shared/findings.yaml` and `shared/cli.yaml` hold the new texts and option exactly as design decisions 6, 20,
      24 and 25 word them; `scripts/sync-shared` run. (The contract is test input: the goldens below render from it.)
- [ ] 1.2 Re-bless the stderr goldens of every existing `dr-refactor` case for the progress lines
      (`LA_UPDATE_GOLDENS=1`, reason in the commit message); before committing, check that the golden diff holds only
      progress lines, the per-group refusal lines, and the scenario changes of the delta spec.
- [ ] 1.3 New paired conformance cases, one per scenario of "Refactors run in announced phases…", "Cheap checks run
      before any reference search" (except the Python-only ones), "Every refusal of a run…", "--fail-fast…", and the
      new or changed scenarios of the MODIFIED requirements: missing keep path; keep line past the end; keep holding
      no old name; three bad keeps; missing `--with`/`--without`; two unresolved entries; unresolved entry + bad keep;
      escaped-spelling keep; `--docs` prose keep with and without `--docs`; late unmatched keep + blind spot; two map
      conflicts; retarget refusal + blind spot; `--fail-fast`; default with two refused entries; unrelated entries
      sharing an old name, one refused; merged duplicate entries (header, labels); move-module phases; `--apply`
      phases with `[baseline]`/`[write]`; map-invalid entries 2 and 4 (both invoking twins). Each early-refusal case
      asserts no `[references]` line.
- [ ] 1.4 Adapter cases: TypeScript retarget with `--keep` on the removed duplicate import line; Python walker gaps in
      two candidate files at `checks`; Python checker probe failing with a fake command (exit code + stderr); Python
      language server that cannot start (fake, `checker-not-started`); Python mid-run `baseline-failed` with its cause
      (update `refactor-baseline-failed`); Python module rename with `--keep` on the module file.
- [ ] 1.5 A case pinned with `twin:` to the non-native twin proving progress and refusal lines survive forwarding byte
      for byte, including a refused run.
- [ ] 1.6 `conformance/INVENTORY.md` lists every new case and the new findings; every new `findings.yaml` template is
      produced by at least one golden.
- [ ] 1.7 Unit tests in both twins for the keep text over-approximation (escapes, NFKC, implicit concatenation, moved
      file, retarget target name, unresolved entry spelling no name) and the map loader returning every invalid index.

## 2. Contract and shared plumbing (pr-implement)

- [ ] 2.1 Both twins: a progress reporter writing the `refactor.progress-*` lines to stderr (flushed per line), and a
      refusal collector with exit code = highest finding code; every `dr-refactor` subcommand runs through the phase
      sequence of design decision 6.
- [ ] 2.2 Both twins: the map loader returns every invalid entry; both routing front ends report them before routing.

## 3. Python twin (pr-implement)

- [ ] 3.1 `rename_map.py`: `resolve` collects every failure (no raise); duplicates and convergence among resolved
      entries; one lazily started language server per run shared by the resolve fallback, the probe and compute.
- [ ] 3.2 `checks`: site existence, keep text check, walker probe over the candidate files (reuse the `dr-compliance`
      rope-walk walk), checker probes; one combined report.
- [ ] 3.3 Compute: `[references n/count]` in the prepare loop; rules and finish run group by group with per-group keep
      filtering and result lines; `WalkerGap`, `NameConflict`, `UnresolvedBase`, `not-stand-in` recorded per
      entry/site; retarget refusals join the final report; all keep, name and map conflicts collected; `--fail-fast`.
- [ ] 3.4 `rope_refactor.py`: moves and module renames through the same phases and collector; `_kept` reports every
      unmatched keep.
- [ ] 3.5 `lang/language_server.py` captures stderr; `LanguageServerError`, `CommandError`/`BaselineFailed` carry
      exit code, error and stderr; the `checker-*` cause lines printed after `pyright-failed`/`baseline-failed`.

## 4. npm twin (pr-implement)

- [ ] 4.1 `rename.ts`/`typescript.ts`/`session.ts`: the same phases, collector, keep text check (old names and retarget
      targets), site existence, per-target `[references]` lines, per-group `[rules]` lines with per-group keep
      filtering, retarget refusals joining the final report, every conflict collected, `--fail-fast`; moves through
      the phases.

## 5. Docs and gates (pr-implement)

- [ ] 5.1 `docs/deterministic-refactoring.md`: phases, progress, the combined report, `--fail-fast`, checker causes.
- [ ] 5.2 Local test scope per `/la:pr`, `uv run ruff check src tests`, `uv run basedpyright src tests`,
      `npm run lint && npm run typecheck`, `scripts/sync-shared --check`, `la-arch-check`. Verify: all green.

## 6. Verification on SLayer (dry run only)

- [ ] 6.1 In a `git archive` copy of SLayer's branch `egor/dev-1607-rename-columns-to-fields-to-be-consistent-with`,
      run its map with its flags plus `--keep architecture`: the run refuses in `checks` with `refactor.keep-unmatched`
      within seconds, before any `[references]` line. Nothing is written to the SLayer checkout. Record the outcome in
      a Linear comment on DEV-2302.
