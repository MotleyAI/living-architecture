## 0. Stage order (read first)

- [ ] 0.1 pr-tests writes section 1 only; pr-implement does sections 2–4. While section 1 is open the stage is
      `pr-tests`. Before opening the PR, check DEV-2302's state in Linear: if it has merged, merge `origin/main` into
      this branch first (`git merge origin/main -m "Merge branch 'origin/main' into …"`; never rebase or stash) and
      re-run the local test scope.
- [x] 0.2 Every new conformance case is a Python `adapter` case with a hand-written golden (`golden: manual`), listed
      in `conformance/INVENTORY.md`. Existing Python rename / rename-map / retarget / `Literal` / `--attr` goldens are
      never regenerated; only `refactor-rename-unsure-include`'s warning line changes, by hand, to the approved text
      (design decision 17).

## 1. Tests (pr-tests)

- [x] 1.1 Conformance cases for "Every member occurrence kind" and "Every name occurrence kind" (spec), each also
      with a CRLF / lone `\r` / astral-character variant ("Positions after astral characters and CRLF in every
      kind"). Verify: goldens equal today's output (run against the current code before any implementation change;
      they must pass now, as they pin byte-identity).
- [x] 1.2 Conformance cases for overloads, `super()` and `Protocol` members, and the "Python diamond and mixin
      hierarchy" scenario. Verify: they pass on today's code, or, where today's rope hierarchy differs from the spec's
      definition, the difference is raised with the user before writing the golden.
- [x] 1.3 Conformance case "Import the checker cannot resolve" (a fixture whose `pyrightconfig.json` keeps the project
      root off basedpyright's search path while rope's source folders find `pkg.a`). Verify: passes on today's code
      (rope renames them today).
- [x] 1.4 Test in `python/tests/test_refactor.py` for "A module rope does not walk" (rename-walk refusal only where
      rope walks), with gaps made by `restore_rope_visitor`, since no shipped input reaches a walker gap. Verify: fails
      on today's code (today it refuses with `refactor.rope-walk`).
- [x] 1.5 `refactor-rename-unsure-include`: hand-edit the warning line to the approved text; new cases "Untyped
      receiver renamed on request" and "Skipped by default". Verify: the edited and new `--unsure include` cases
      fail on today's code; "Skipped by default" passes.
- [x] 1.6 Conformance case "Same verdict as a rename" (`dr-compliance --attr` positions = a member rename's
      blind-spot positions on one fixture). Verify: passes on today's code (both use `MemberScan` today).
- [x] 1.7 Conformance case "Unverified checker": the export preload's verified-version list, overridable for tests
      the way `test_pyright_patch.py` overrides the #11919 list, excludes the bundled version → `refactor.pyright-failed`,
      exit 1, no file changes. Plus a `python/tests/test_pyright_export.py` unit suite mirroring
      `test_pyright_patch.py`: anchors counted (exactly once, else `mismatch`), unverified version, outcome recording,
      and the startup self-test refusing when the command is missing. Verify: fails before the preload exists.
- [x] 1.8 Request-count tests (design decision 19) in `python/tests/test_rename_map.py` or a new
      `python/tests/test_occurrence_index.py`, counting `LanguageServer` requests by method: a one-entry and a
      ten-entry symbol map send the same number of export requests and no `references`/`hover`/`definition`
      request; a map with a rope-fallback entry; a map with two `Literal` entries; module rename and `move-module`
      start no server. Verify: fail on today's code.
- [x] 1.9 Cache tests (`python/tests/test_occurrence_cache.py`), each run with `LA_CACHE_DIR` under `tmp_path`:
      re-run with only `--without` flags added exports nothing and prints identical output; a source edit, an added
      import-shadowing module, a deleted file, a changed `pyrightconfig.json`, a changed file in a site-packages
      directory of the configured venv and a changed request each export anew; a truncated or invalid cache entry is
      a miss with identical output; no cache file is written under the project, with and without `--apply`;
      `LA_CACHE_DIR` unset resolves to the user cache directory (monkeypatched `XDG_CACHE_HOME`). Verify: fail on
      today's code.
- [x] 1.10 `python/tests/test_conformance.py` (runner): every case runs with `LA_CACHE_DIR` set to a fresh temporary
      directory (design decision 21). Verify: a test asserting the environment the runner passes fails before the
      change.
- [x] 1.11 Coordinate tests in `python/tests/test_language_server.py`: export ranges convert against the opened text
      with CRLF, lone `\r`, astral characters before and inside a line; a range that does not slice to the expected
      spelling raises `LanguageServerError`. Verify: fail before the export client exists.
- [x] 1.12 Existing tests that pin the old mechanism (per-occurrence LS calls, `MemberScan` probes, rope finders in
      `test_rename_union.py`, `test_rename_strings.py`, `test_compliance_attr.py`, `test_keyed_rename.py`,
      `fake_lsp_server.py` users): list each one that contradicts the plan and ask the user's approval to align it,
      naming the file and the change. Verify: approval recorded here before editing.
      Approved (user, 2026-11-16): `test_refactor.py`'s four walker-gap tests locate the rename in `pkg/gap.py`;
      `test_refactor_progress.py`'s walker-gap checks test becomes a two-entry map located in `pkg/g1.py` and
      `pkg/g2.py` (`test_walker_gaps_in_every_entry_module_refuse_in_the_checks`); `test_rename_union.py`'s two tests
      patch or hook `LanguageServer.export` instead of `references` (the first renamed
      `test_language_server_failing_during_the_export`).

## 2. The occurrence index (pr-implement)

- [x] 2.1 `shared/`: `languages.yaml` python gains the cache variable name (`LA_CACHE_DIR`) and the export preload's
      verified versions; `findings.yaml` `refactor.unsure-warning` and `cli.yaml` `--unsure` help get the approved
      wording (design decision 17); run `scripts/sync-shared`. Verify: `scripts/sync-shared --check` and the drift
      test pass.
- [x] 2.2 `python/src/living_architecture/lang/pyright_export.cjs`: the `CommandController` hook (design decisions 1–3,
      5), anchors counted, outcome recorded; wired into the language server's `NODE_OPTIONS` beside the #11919 preload
      (`lang/typecheck.py`), never into `la-typecheck`'s checker runs. Verify: 1.7 passes.
- [x] 2.3 The index client in `lang/` (request, UTF-16 range conversion and spelling check, records as pydantic
      models) and the startup self-test. Verify: 1.11 passes.
- [x] 2.4 The run-scoped lazy session (design decision 10) and the batched fact positions (decision 4), the
      string-member probe round (decision 5), the rope fallback batch (decision 6), candidate files (decision 12). Verify: 1.3 and 1.8 pass.
- [x] 2.5 The new resolver beside the old: every rule of `rename_union.py`, `keyed.py`, `member_scan.py`,
      `retarget.py`, `literal_rename.py` reading the index; hierarchy per design decision 8; `--unsure include` per
      decision 14; per-run text tables (decision 13). Verify: sections 1.1–1.6 pass.
- [x] 2.6 Differential run (design decision 18): old and new resolver over every Python refactor conformance fixture
      and the listed edge fixtures, comparing normalized edit and finding sets. Any difference: stop and ask the user.
      Then delete the old path (rope occurrence search, per-occurrence LS queries, `MemberScan`'s per-query code,
      `_renamer`'s own server). Verify: no difference, or each one resolved by the user; the deleted code has no
      remaining caller.
- [x] 2.7 `dr-compliance --attr` on the index (design decision 15). Verify: every `compliance-attr*` conformance
      case and 1.6 pass.
- [x] 2.8 The whole-run cache (design decision 9) and the conformance runner's isolation (decision 21). Verify: 1.9
      and 1.10 pass.

## 3. Docs and gates (pr-implement)

- [x] 3.1 `plugin/languages/python.md` line 16 and `docs/deterministic-refactoring.md` lines 12–13 get the approved
      wording verbatim (design decision 17); any other doc sentence that says rope finds a rename's occurrences is
      raised with the user before editing. Verify: `rg -n "rope" plugin docs` reviewed.
- [x] 3.2 Local test scope per `/la:pr` (affected tests, every changed conformance case, the drift test), `uv run
      ruff check src tests`, `uv run basedpyright src tests`, `la-arch-check`, `npx -y @anthropic-ai/claude-code
      plugin validate plugin`. Verify: all green.

## 4. Verification on SLayer (dry run only)

- [ ] 4.1 `git archive` SLayer's branch `egor/dev-1607-rename-columns-to-fields-to-be-consistent-with` into a temp
      directory (its `.venv` symlinked in); run the DEV-1607 map (`openspec/changes/dev-1607-rename-columns-to-fields-to-be-consistent-with/rename-map.yaml`,
      flags from its header) as a dry run under `/usr/bin/time -v`, once cold and once with a warm cache. Nothing is
      written to the SLayer checkout. Verify: wall time and peak RSS recorded in a Linear comment on DEV-2301; target
      under 10 minutes cold, peak memory about one full check (3.8 GB). If missed, profile and raise the findings with
      the user before any fallback.
  - [ ] 4.1a Cold run 1 (2026-11-16, machine shared with other heavy sessions) MISSED: the export finished, then the
        rules phase stalled at group 6 (`measures`) and was stopped at ~29 min (node RSS 3.9 GB at that point). It
        reproduces with only the 11 `measures` entries (`--docs`, no site flags): stalled in `[rules]` for 10+ min.
        Next: profile that small map with `python -m cProfile` (py-spy has no ptrace permission here); suspects are
        the per-miss export fallback (`RunIndex._fact`, one request per position the export did not pre-collect)
        and the text rules (`_overlaps` scans every edit per mention). A `--keep`/`--with` flag whose site the subset
        does not touch refuses in checks, so drop the site flags for a subset run. Raise the findings with the user
        before any fallback.
  - [ ] 4.1b Already fixed: `fact_queries` took ~14 s over 854 files (nested re-walks), now one pass per file;
        export spans no longer recompute line starts per span.

## 5. Gaps from the DEV-2301 review comment (2026-11-16, "Three gaps in this plan")

- [ ] 5.1 Gap 1 (rope uses outside decision 7: `MemberCheck`'s `Hierarchy` in `member_namespace.py`, retarget's
      `definition`/`attribute_definition`/`_receiver_module`, source folders): a design decision for the user, not yet
      asked. Options: move them onto the checker (the conflict check's class graph onto `refactor/hierarchy.py`'s
      `ClassGraph`, a port of rope's source-folder rule, retarget lookups through index facts), or record them in
      decision 7 and the Impact list. Recommendation: move at least the class graph, so one member rename uses one
      class graph. Either way it is a plan edit needing the user's OK of the exact diff, plus the two differential
      fixtures the comment names (a library base declaring the new name; a project ancestor behind an unresolved base).
- [ ] 5.2 Gap 2 (a name, import or alias occurrence neither the checker nor rope resolves gets no outcome): not
      implemented. Plan: in `SymbolRename._index_edits`, each unresolved occurrence rope does not match becomes a
      leftover finding. Needs the user's approval of a new `shared/findings.yaml` template's wording, a conformance
      case and an `INVENTORY.md` entry; no existing golden changes (none of the samples holds such a site).
- [ ] 5.3 Gap 3 (retargeting a re-exported alias): already handled by the implementation, nothing to change unless
      the user asks. An entry's renamed declarations are what the checker resolves its site to (`_located`), so an
      alias entry matches every occurrence resolving through it; `refactor-retarget-reexport-form` and
      `refactor-symbol-import-binding` pass. Tell the user so when raising 5.1/5.2.
