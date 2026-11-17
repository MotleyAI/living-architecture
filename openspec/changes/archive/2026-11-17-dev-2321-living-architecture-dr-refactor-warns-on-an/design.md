## Context

See proposal.md (Why). Where the exact site decisions sit today:

- Python (`refactor/rename_map.py`): `references` (`SymbolRename.prepare`) resolves the renamed declarations and the
  `--with` / `--without` classification (`matched_sites`). The edits are built in `rules`: `_index_edits`, keyed,
  member-string and target edits, then `finish()` (`--docs` mentions). Each group's keeps are applied in `_keep`,
  and after the group loop `_imports` plans the retargets' imports. `report()` then runs `conflicts` and, only after
  that, `site_findings()` (`not-stand-in`, `Keeps.unmatched()`), and only when no entry failed.
- TypeScript (`node/src/refactor/rename.ts`, `runEntries`): `references` produces the language-service edits.
  Stand-in classification, scans, `--docs` and `keep(group, keeps)` run per group in `rules`. `planImports` and the
  site findings run in the block after the group loop, with the site findings after `conflicts`.
- Python module rename (`refactor/rope_refactor.py`, `_module_rename`): `_kept` filters rope's change set by the
  keeps after the reference search. `[conflicts]` follows, and every `--with` / `--without` is refused after it.
- The up-front keep check (`keep_checks` + `sites.keep_spells` in Python, `checks` + `sites.keepSpells` in TS) is
  textual and covers whole-path keeps and line keeps alike.

The edit sets are complete only after every group's rules, the import planning and the keep filtering, in both
twins. The issue's "end of `references`" isn't reachable (decision 1).

## Goals / Non-Goals

**Goals:**
- One *site resolution* step per twin, at the single point where every entry's edits are final, deciding every keep
  and stand-in site exactly, printing the warnings and stopping on a refusing site finding.
- A cheaper up-front refusal for comment-only line keeps.
- Identical output in both twins on every shared input (conformance).

**Non-Goals:**
- Retarget's planned imports honouring `--keep` (DEV-2322). Site resolution runs after import planning, so a keep
  covering only a planned import is refused (line keep), and a whole-file keep can't meet one: a kept file's sites
  aren't rewritten, so no import is planned there.
- A type-based up-front keep check (a declaration outside every renamed hierarchy): it needs checker facts, so it
  isn't cheap.
- Excluding strings from the up-front check: several rules rewrite strings without `--docs`.
- A Python filter dropping every comment edit without `--docs`: it would drop correct type-comment rewrites.
- A version bump (releases bump separately).

## Decisions

1. **Site resolution at the end of the computation, before `conflicts`, in both twins** (user). The alternative
   was per-group decisions during `rules`: a line keep decided after the last group whose old name its line spells.
   It would refuse earlier on average, but it depends on a hand-kept invariant (every edit of a group starts on a
   line spelling its old name) that every edit source (retarget, keyed, mentions, planned imports, TS
   language-service edits) would have to keep true, and the refusal point would differ per keep, so goldens would
   depend on the map's shape. The issue's "end of `references`" isn't possible: the edit sets are not complete
   there in either twin.
2. **A refusing site finding always stops before `conflicts`** (user). The alternative was stopping only under
   `--fail-fast` (opt-in; the issue's `--keep-going` doesn't exist). A site finding is a usage error about the
   command line, like the `checks`-phase site findings that already stop the run, and `conflicts` over a
   mis-specified keep set gives findings the corrected command may not reproduce. This amends the one-report
   requirement: name and map conflicts aren't computed after such a stop.
3. **Tighter up-front check: without `--docs`, comment spellings don't count, except Python type comments**
   (user; type-comment exception (codex)). The alternative was leaving the check as is. Neither twin rewrites a
   comment without `--docs` (TS drops comment edits explicitly; Python's only comment rule is the `--docs` mention
   pass), except that the checker resolves names inside PEP 484 type comments, so those count as code. The check
   only refuses keeps that can't match.
4. **Wording** (user, approved wording):

       refactor.keep-unmatched: '--keep {site} matches nothing this rename touches, so nothing was refactored'
       refactor.keep-unmatched-near: '--keep {site} matches nothing this rename touches; the nearest edited line is {path}:{line}, so nothing was refactored'
       refactor.keep-unneeded: 'WARNING: --keep {site} matches nothing this rename touches'
       refactor.not-stand-in: '{site} is not a stand-in of this rename, so nothing was refactored'

   `WARNING:` is uppercase to match `refactor.unsure-warning` (the issue wrote `warning:`). `refactor.computed-stand-in`
   is unchanged.
5. **Whole-path keeps get no up-front textual check**: all of their matching is left to site resolution, which
   also covers moves (a kept moved module or package) (default; rationale corrected (codex): a whole-path keep
   spelling no old name can still match a move).
6. **Warnings at site resolution**, on stderr in command-line order, after the last `[rules]` line and before
   `[conflicts]` (or before the final report on a stop); not repeated in the final report (default).
7. **Nearest edited line**: among the edits the run writes in the kept file (after every keep), by each edit's start
   line; ties go to the earlier line; no edited line gives plain `keep-unmatched` (default).
8. **`computed-stand-in` (TS)** is decided and stops at site resolution like `not-stand-in`; text unchanged (the
   issue names only the two) (default).
9. **Python module rename**: `--with` / `--without` refused in `checks` (a module has no stand-ins; the earliest
   point it is known); keeps resolved after `_kept`, before `[conflicts]`, the nearest edited line taken from the
   kept change set's edits (default).
10. **Site resolution is skipped** after a `--fail-fast` stop and, in Python, when an entry failed while computing (a
    partial computation, as today's `sites = [] if failed`) (default).
11. **Explicit order in both twins** (codex): every group's rules → retarget import planning → final keep filtering
    → site resolution (stand-in sites, keeps, warnings) → stop if a site finding refuses → `[conflicts]`. In
    Python, `_imports` already ends `rules()`, so site resolution runs after `rules()` returns; in TS, `planImports`
    moves ahead of site resolution.
12. **Retarget's planned imports ignoring `--keep`** is out of scope and filed as DEV-2322 (user). Fixing it needs
    a placement design (an import beside a kept statement, or a refusal), not a filter.
13. **No version bump** in this change (default).

## Risks / Trade-offs

- [The comment rule's premise breaks if a producer starts editing inside comments without `--docs`] → the paired
  cases pin a comment-only keep with and without `--docs`, a trailing comment, a multi-line comment / JSDoc and a
  Python type comment. A future comment-editing rule fails those cases first.
- [Stopping at site resolution hides name and map conflicts until the re-run] → accepted (decision 2). The re-run
  computes them over the corrected keep set.
- [Existing goldens change (keep and not-stand-in cases)] → each realigned golden is reviewed against this design.
  The commit message states the reason.
- [The Python twin skips site resolution when an entry failed] → unchanged behaviour. Those runs refuse anyway, and a
  keep's match is unknowable on a partial computation.
