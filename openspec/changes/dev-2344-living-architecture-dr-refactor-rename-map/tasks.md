## 1. Tests first (pr-tests)

New conformance cases are paired (`python`, `typescript`), hand-written (`golden: manual`) and listed in
`conformance/INVENTORY.md`. The fixtures of DEV-2344's agent notes are the starting point.

- [ ] 1.1 `refactor-map-chain`: the member chain with `--apply`, in both entry orders (two cases or one per order):
      exit 0, files compared
- [ ] 1.2 `refactor-map-swap`: rewrite the existing Python case as a paired case that applies; add chain, swap and
      converging-name cases for parameters, locals and top-level names, each in both entry orders
- [ ] 1.2a `refactor-map-module-swap` (Python): modules `pkg/a.py` to `b` and `pkg/b.py` to `a`: each entry's wrapped
      `refactor.name-conflict` in `checks`; `refactor-map-module-chain` keeps refusing, its finding wrapped
- [ ] 1.3 `refactor-map-chain-kept`: the chain with `--keep` on the freed declaration: refused in `conflicts`, the
      finding wrapped for the entry renaming onto the kept name
- [ ] 1.4 `refactor-map-early-capture`: a member, a parameter, a local and a top-level entry each colliding in its
      declaring scope: four wrapped findings in `checks`, no `[references]` line; a Python case for a member declared
      through `self`
- [ ] 1.5 Early-check non-refusals: TypeScript (disjoint meanings, a legal merge, overloads, static beside instance,
      sibling blocks, `var` beside a block `let`, accessors, parameter properties) and Python (nested function,
      comprehension, nested class, `global` / `nonlocal`); a `--keep` on either declaration's line leaves the pair to
      `conflicts`
- [ ] 1.6 `refactor-map-unlocatable-entries`: item 16's map: `entry 2 (pkg/c.py:2:11)` and `entry 3 (pkg/c.py:2:5)`,
      and one case per locator form (`FILE:LINE`, `FILE SYMBOL`, `FILE offset N`, a Python module entry, merged
      duplicate indexes)
- [ ] 1.7 `refactor-map-refusal-once`: a stand-in and a `literal-unresolved` each printed once; a rules-only refusal
      exits 1 with and without `--fail-fast`; an entry failing while computed is wrapped under its group's line; a
      `--fail-fast` stop before `rules` lists the failure in the final report
- [ ] 1.8 `refactor-sites-project-relative`: `--project proj` from the directory holding it: `--keep`, `--with` and
      `--without`, each as a file, a directory (keep), a line and an absolute path; a path relative to the working
      directory is `refactor.site-missing`
- [ ] 1.9 `refactor-map-stand-in-two-entries`: item 5 with a read through the stand-in: `refactor.map-conflict` at the
      declaration and at the read, both twins
- [ ] 1.10 `refactor-map-conflict-no-name-check`: a map conflict beside a late name conflict: only the map conflict
- [ ] 1.11 Name-conflict attribution: a conflict wrapped for its entry; three entries meeting on one name (the latest
      entry's finding, the earliest's declaration); a retarget beside a rename; `rename` printing `entry 1 (...)`
- [ ] 1.12 Unit tests in both twins: site parsing against the project root; the entry wrapper and each locator form;
      the early check's decisions; exit status apart from printing; the Python keyword/key check on the names after
      every entry's edits
- [ ] 1.13 List every existing golden and test this plan changes (resolve failures, name conflicts, repeated
      refusals, converging names now refused in `checks`, `--keep` relative to a working directory) and get the
      user's approval to align them, naming each file

## 2. Shared contract

- [ ] 2.1 Add `refactor.entry-refusal` to `shared/findings.yaml` and the help texts to `shared/cli.yaml` (design
      decisions 19 and 20, verbatim)
- [ ] 2.2 Run `scripts/sync-shared`

## 3. Python twin

- [ ] 3.1 `Site.parse(raw, root)` resolves against the project root only; migrate the site checks, the line-keep
      check, `Keeps` and stand-in classification
- [ ] 3.2 One wrapper turning an entry's error or conflict into a `refactor.entry-refusal`; used by resolve, by the
      computing phases and by every name conflict (early, module, post-map, keyword/key, move)
- [ ] 3.3 `Conflict` carries its entry and the declaration it meets; attribution per design decisions 8 and 15
- [ ] 3.4 Remove the per-entry passes from `check_names`; one pass over all entries with every surviving move; each
      entry's first conflict, by entry index; no name check when a map conflict exists
- [ ] 3.5 The keyword/key check judged on the names after every entry's edits
- [ ] 3.6 The early own-scope check in `checks`, on the binding-site and member-declaration tables of the full check
- [ ] 3.7 Print once: refusals printed under a `[rules]` line are kept for the exit code and left out of the final
      report

## 4. npm twin

- [ ] 4.1 `Site.parse(raw, root)` and its callers, as 3.1
- [ ] 4.2 The entry wrapper, as 3.2
- [ ] 4.3 Conflicts carry their entry; the per-entry passes removed from `nameConflicts`; no name check when a map
      conflict exists, as 3.3 and 3.4
- [ ] 4.4 The early own-scope check, on the compiler's symbols (meanings, merges, static and instance sides)
- [ ] 4.5 Print once, as 3.7
- [ ] 4.6 A `--with` stand-in gets a full edit set per distinct new name of its group's entries

## 5. Docs and gates

- [ ] 5.1 `plugin/skills/deterministic-refactor/SKILL.md` (design decision 21, verbatim) and
      `docs/deterministic-refactoring.md` (chains, the early check, one print per refusal, site paths)
- [ ] 5.2 Update the approved goldens with `LA_UPDATE_GOLDENS=1` where they are not `golden: manual`, the reason in
      the commit message; review each diff
- [ ] 5.3 Local test scope green in both twins; `scripts/conformance-cross` for the changed cases; `la-arch-check`,
      the LikeC4 validation and `la-typecheck`; `ruff`, `basedpyright`, `npm run lint && npm run typecheck`
