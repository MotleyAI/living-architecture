## Context

See proposal.md (Why). Retarget today (DEV-2295, archived `2026-11-15-dev-2295-living-architecture-dr-refactor-names-symbols`,
decisions 7, 16, 29, 31 and 48) is the rename of ALIAS to TARGET's name minus ALIAS's own declarations, then
adjusted by syntactic special cases: Python `refactor/retarget.py` (`_shim_imports`, `_reexport_spans`,
`_through_bare_shim`, `_bare_shim`, `_duplicate`, `_bound_in_scope`, `_module_binds_other`) and `rename_map.py`
`_resolve_target` (refuses an import binding as target); TypeScript `src/refactor/rename.ts` (`resolveRetarget`,
`retargetEdits`, `keptBindings`, `shimImports`, `duplicateImport`). Probed on this branch: a star import from a
single-name shim and `pkg.compat.AcmeModel` are both rewritten to an unbound `Model` (Python); both twins refuse
SLayer's `FlightCatalog = FacadeCatalog` with `refactor.retarget-scope`.

Principles that apply (`architecture/system.arc42.md`; the `refactor` element has no arc42 of its own):
1. Twins — every rule lands in both twins, pinned by paired conformance cases run through both invoking twins.
2. Shared contract — the new `refactor.retarget-unbound` template lives in `shared/findings.yaml`; no CLI surface
   change.
3. Language-specific code only in `lang` and `refactor` — all new code is in `refactor`.
4. No target-repo code runs — resolution uses rope, la's own basedpyright and the bundled TypeScript checker.

Spec attachment: the existing `refactor` capability (metadata `specs` of `python.refactor`). No model, arc42 or
`index.yaml` edit.

## Goals / Non-Goals

**Goals:**
- A retarget never writes a name that is unbound, or bound to something other than TARGET, where it writes it.
- One import-adding mechanism per twin serves the imported target, star imports, shim bodies and shim importers.

**Non-Goals:**
- Rewriting a module-qualified access into a bare name (`pkg.compat.AcmeModel` → `Model`); an unbound one refuses.
- Removing an import left unused by the retarget (`import pkg.compat` after its last attribute use is kept).
- Sorting imports or formatting beyond the spans edited.
- Checking the target repo's import law for the edges an added import creates (its `la-arch-check` gate does).
- A cross-module target for a member alias.

## Decisions

Structural cause (design bias): retarget decides "is TARGET's name bound here" by an allow-list of syntactic forms,
and every unlisted form (star imports, module attributes, an imported target) falls through to "rewrite". Fix: one
rule for every rewritten site — after the edit the written name resolves to TARGET, already bound or bound by an import
the retarget adds; re-export sites stay; anything else refuses — with one import planner per twin replacing the
keep/shim special cases. Grounded in principles 1 and 2.

1. **What keeps the alias**: A) only the re-export sites (the `__all__` string, the import or export re-exporting
   ALIAS); a shim's body uses and importers through a shim are rewritten with TARGET imported; B) today's keep-set
   (re-export sites plus everything a kept re-export binds), extended to star and namespace imports. Took A: one rule,
   the one SLayer's importers need; B's keep-list is how the bug class arose. Replaces decision 48's "a reference that
   a kept re-export binds stays" (DEV-2295). (user)
2. **Module attribute whose module does not bind TARGET**: A) refuse with `refactor.retarget-unbound`, released by
   `--keep`; B) re-point the receiver to the home module; C) replace the qualified access by the bare target plus an
   import (raised by Codex). Took A: B falls back to refusing anyway, C changes the code's access style silently.
   (user)
3. **Skill and docs wording** (user, approved wording):
   - `plugin/skills/deterministic-refactor/SKILL.md`: "`retarget --file F --symbol OLD --target NEW` rewrites what
     resolves to the alias `OLD` to name `NEW`, its target declared or imported in the same class or module, imports
     `NEW` where a file lacks it, and leaves `OLD` and its re-exports in place."
   - `docs/deterministic-refactoring.md`: "`retarget` rewrites what resolves to a back-compat alias so it names the
     alias's target, importing the target where a file lacks it and leaving the alias and its re-exports."
4. **Home**: the module ALIAS's module imports TARGET from, as that import names it; never chased further along a
   re-export chain, so a package's public `__init__` is never bypassed for a private module. As the issue states.
   (default)
5. **Import placement**: in the block of the statement binding ALIAS — joining that block's earlier import from the
   home, else replacing ALIAS's sole-name import in place, else a new statement on the next line. Never sorted.
   Weighed: isort-style placement (repo-config dependent). (default)
6. **Import spelling mirrors the import it replaces or follows**: absolute or relative (Python, relative computed
   from the importing file's package), the extension style of the specifier (TypeScript), a bare package specifier as
   ALIAS's module spells it; a Python package's home is its module name (`pkg`, never `pkg.__init__`). (default; the
   package rule from codex)
7. **Re-export form**: for `from M import T as ALIAS` / `export { T as ALIAS } from 'M'`, `--target T` matches the
   imported name `T` in that statement; TARGET is `(M, T)` with no local binding in ALIAS's module, so a use of ALIAS
   in that module's own body gets `T` imported like any unbound site. (default; codex)
8. **A member alias still needs a same-class target.** (default)
9. **Resolution decides identity, position decides binding**: TARGET's identity is its declaration set and what an
   import of it resolves to through any chain (TypeScript `getAliasedSymbol`; Python the checker's definition); a
   binding counts for a rewritten use only when it dominates the statement binding ALIAS there (same block and
   earlier, or an enclosing block), so TARGET is bound exactly where ALIAS was, on every path — conditional, `try`,
   loop and function-local imports included. A `TYPE_CHECKING`-only binding counts only for an ALIAS binding under
   `TYPE_CHECKING` too. Weighed: checker resolution at the use (accepts a `TYPE_CHECKING` or later-branch binding for a
   runtime use). (codex)
10. **`refactor-retarget-scope` repurposed**: its current shape (ALIAS in `compat.py`, TARGET imported from
    `core.py`) is now accepted; the case becomes a member alias whose target is in another class. (default)
11. **An import of ALIAS from M stays on M when M exports TARGET**: Python M declares it, lists it in `__all__`, or
    imports it `as` its own name (the PEP 484 re-export convention); TypeScript M's exports hold it. Otherwise ALIAS
    leaves that import and TARGET is imported from home. SLayer's `catalog.py` imports `FacadeCatalog` without
    exporting it, so its importers are re-pointed; a public re-export layer exporting both names (the existing
    `refactor-map-retarget-reexport-shim` golden) is kept. Weighed: always re-pointing to the home (bypasses a public
    re-export layer, contradicting decision 4). (default)
12. **TypeScript meanings**: the bound and shadowed checks resolve the meaning each rewritten site needs (type or
    value); an added import is type-only when every use it serves is a type use; TARGET's identity is the full set of
    its declaration keys, not the first. Cases: `typeof`, `extends`, merged declarations, a type and an unrelated
    value of one spelling. (codex)
13. **`--keep` before import planning**: kept references keep ALIAS; an import of ALIAS stays while a kept reference
    needs it; an added import serving only kept references is not added; a `retarget-shadowed` or `retarget-unbound`
    refusal on a kept line is dropped. `retarget-override` is unchanged (the override's declaration line does not make
    the calls safe). (codex; the refusal release is user decision 2)
14. **Imports planned once across the map**: every retarget entry's import needs are collected per file and block
    and emitted once per home (SLayer's five aliases → one `from slayer.facade.catalog import ...`), using TARGET's
    final name when another entry renames it. (codex)
15. **Re-export surface**: `__all__` by plain, annotated or augmented assignment, `.append` or `.extend`; TypeScript
    `export { }`, `export type { }`, `export { } from`. Cases for each. (codex)
16. **Edits touch name spans only**: multiline parenthesised imports, trailing commas, comments and TypeScript import
    attributes of the edited statement are preserved; a new statement carries none. (codex)
17. **Conformance coverage**: every form above is a paired case (both languages, both invoking twins), including a
    multi-entry SLayer-shaped case; the real SLayer dry run is extra acceptance evidence, not the regression test.
    (codex)
18. Rejected (codex): none; all seventeen findings were folded (finding 1's option C rejected by the user, decision 2).
19. **Spec delta as REMOVED + ADDED**: the requirement is replaced under a new name, "Retarget rewrites references to
    an alias and keeps every name bound", because a MODIFIED block may not drop the scenario "Single-name shim kept with
    its importers", whose behaviour decision 1 reverses. Weighed: keeping that scenario's name over the opposite
    behaviour (misleading). (default)

## Mechanisms

- **Site classification** (both twins): each rename edit of ALIAS is one of: ALIAS's own declaration (dropped),
  re-export site (dropped), import specifier of ALIAS, bare reference (TypeScript shorthand included), module
  attribute, member access. One outcome per site (DEV-2292's outcome model): rewrite, rewrite-with-import-need,
  keep, or refusal.
- **Import planner** (one per twin): input — per file, the import needs `(block, anchor statement, home, exported
  name, meaning)` and the ALIAS imports to drop; output — text edits. Runs after `--keep`, once over all retarget
  entries of a map, before conflict detection.
- **Target record**: home module, exported name, local name in ALIAS's module, declaration keys (identity).

## Risks / Trade-offs

- [An added import creates a module edge the target repo's model does not license] → the target repo's
  `la-arch-check` in the refactor gate reports it; the retarget does not check it.
- [Initialisation order shifts] → the file already imported the home transitively through ALIAS's module, so no new
  import cycle appears; the test suite in the gate catches order effects.
- [Python relative-import arithmetic differs between twins] → only the Python twin computes Python spellings; the
  shared vectors are not needed, but paired cases pin relative and package homes.
- [Existing goldens change] → `refactor-map-retarget-single-name-shim` (decision 1) and `refactor-retarget-scope`
  (decision 10) are re-blessed with that reason; `refactor-map-retarget-reexport-shim` stays (decision 11).

## Migration Plan

None beyond the behaviour change (decision 1); release note names decision 48's reversal.
