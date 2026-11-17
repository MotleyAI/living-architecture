## Context

See proposal.md (Why). State on `main` (after #54 and #56, both unreleased):

- Python renames (`rename_union`, `occurrence_index`, `rename_map`) never call rope's evaluator. Every tuple-target
  shape in the spec delta already renames correctly through `rename` and `rename-map`; released 0.11.0 refuses them.
- rope is still used by moves (`refactor/move_edits.py`): `occurrences.create_finder(..., keywords=False)` finds each
  occurrence of the moved name, and the planner reads its primary (`_primary`, `_module_object`) to decide what to
  rewrite (`_ModuleMove.rewrite_uses`, `_SymbolMove._rewrite_uses`) and whether the source module keeps a use
  (`_SymbolMove._outside`). `keywords=False` drops every occurrence rope's text heuristic calls a call keyword before
  it is evaluated.
- `rope_patches.py` patches rope's walker (kept), the `async def` header test (kept), rope's function model
  (`_get_param_names`, `_handle_special_args`, `_get_parameters`, `_KeywordOnlyName`) and call arguments
  (`_Arguments`, `_create_arguments`), and the evaluator (`_primary_and_pyname_at` over `_ParameterSites`).
- Differential runs of `move-symbol` and `move-module` with patches on and off (planning probes):
  - without the function-model and call-argument patches, uses of positional-only and keyword-only parameters
    shadowing an import alias are rewritten, and a module passed through a positional-only call is no longer
    followed (`m1 = ident(pkg.sub)`; `m1.thing.X`);
  - without only the evaluator patch, nothing changes, in any probe or in the full suite;
  - with every patch on, a lambda parameter shadowing an import alias is rewritten (`lambda sub: sub.thing.X` →
    `lambda sub: pkg.thing.X`; `lambda amod: amod.f()` → `lambda amod: pkg.c.f()`).
- `move_edits._Scopes` already models function, lambda, class and comprehension scopes and records every load with
  the scope it is read in, but ignores `global`/`nonlocal` and visits a comprehension's first iterable inside the
  comprehension scope.

Applicable architecture: the change sits in `python.refactor` (no arc42 file of its own); `system.arc42.md`
principles 1 (twins: Python-only adapter cases, run through both twins' bins by `scripts/conformance-cross`), 3
(language-specific code only in `lang` and `refactor`) and 4 (no target-repo code imported or run) apply. No import
edge between elements changes, so the model, `index.yaml` and arc42 stay as they are. The spec delta modifies the
existing `refactor` capability (listed in `python.refactor`'s `specs`); no new spec attachment.

## Goals / Non-Goals

**Goals:**
- Tuple-target renames specified and pinned (spec delta, first requirement).
- The evaluator patch, the site of DEV-2326's bug, removed; the patches moves depend on kept and still tested.
- Moves never rewrite a use whose name a function, lambda or comprehension scope binds (spec delta, rule 2).

**Non-Goals:**
- Execution-ordered binding resolution in module and class bodies (an alias rebound by assignment before a later
  use there). Not observed; DEV-2311's static resolver is the natural home.
- `for`-loop and `with … as (a, b)` targets (never affected), and a map refusal naming its entry.
- The release commit and SLayer's pin bump (post-merge, see tasks.md 7).
- The rest of rope's retirement (DEV-2311 moves, DEV-2312 dependency, walker contract, `rope_patches.py`).
- The blank-line layout of an import `move-symbol` adds to the source module (pinned by
  `refactor-move-symbol-apply`).

## Decisions

1. **Pin, don't re-fix, the rename bug.** #54 removed rope's evaluator from renames, which makes the whole class of
   rope-heuristic rename refusals impossible; this change specifies the behaviour and pins it with conformance cases
   that pass on `main` by design. (user)
2. **Delete only the evaluator patch.** Deleting every function-model and evaluator patch (planned first) was
   withdrawn after Codex finding 1 and the differential runs above: moves need the function-model and call-argument
   patches until DEV-2311. Rejected: keeping the evaluator patch and fixing it structurally (call keywords from
   `ast.keyword` positions) — no command reaches it. (user; codex)
3. **Test files.** `tests/test_rope_parameters.py` stays; only its four evaluator-level tests go
   (`test_keyword_lookup_resolves_only_keyword_bindable_parameters`,
   `test_defaulted_header_parameter_resolves_to_its_parameter`, `test_names_a_lambda_binds_resolve_to_nothing`,
   `test_keyword_of_an_unresolved_call_resolves_to_nothing`), with their `tests/durations/suite.json` entries.
   (codex)
4. **`every_parameter` moves to `python_source.py`**, the neutral AST helper module of `refactor`; `rename_union`
   and `retarget` import it there, and it replaces `symbol_path._every_parameter`. Locating `f(a)` by `--symbol` is
   covered for all five parameter kinds. (default; codex)
5. **Release separately.** No version bump here; a separate release commit (minor, since twin sources change)
   carries #54, #56 and this change, then SLayer's pin moves. DEV-2326 is Done only after that. (user; codex)
6. **Comprehension targets included** in the rename requirement, beyond the issue's assignment-only scope; they
   work on `main` and nothing guarded them. (user)
7. **Class-body tuple target included**, found while probing. (user)
8. **Spec wording binds by declaration**: "every reference bound to that declaration; a same-spelled binding in a
   nested scope is not renamed", with a shadowing scenario. (codex)
9. **Lambda-shadowing move bug fixed in this change** rather than xfailed against DEV-2311: it produces wrong code
   on `main`, `_Scopes` already holds the scope data, and the new goldens constrain DEV-2311. (user)
10. **Narrow lexical veto for moves** (user; codex findings 1–8 of the second pass):
    - One eligibility check, used by `_ModuleMove.rewrite_uses`, `_SymbolMove._rewrite_uses` and
      `_SymbolMove._outside`, so a shadowed occurrence neither gets rewritten nor makes the source module import the
      moved name.
    - It looks the occurrence's name up from the `_Scopes` scope its load is read in. When the first scope binding
      it is a function, lambda or comprehension scope (lexical for the whole body), the occurrence is skipped unless
      every binding of that name there is an import item the move rewrites (a function-local `import pkg.sub as
      sub` stays eligible). Module and class scopes are never vetoed (today's behaviour; execution order there is a
      non-goal).
    - `_Scopes` fixes, which every user of it gets: a `global`/`nonlocal` name does not bind in the declaring scope
      (it resolves to the module scope, or the nearest enclosing function scope, as Python does), and a
      comprehension's first iterable is visited in the enclosing scope.
    - The star-import path (`_star_imports`) keeps its own lexical-binding rejection; a lambda shadow case proves it.
    - Uses rope's finder misses because its scopes differ from Python's (a `def` header's defaults and annotations, a
      comprehension's first iterable) are found from `_Scopes`: each dotted chain rooted at an import binding,
      resolved from that binding's module path, joins rope's occurrences. (user)
    - Rejected: full binding resolution with execution order in module and class bodies (more work, no observed
      bug, DEV-2311's resolver is the right place); xfail against DEV-2311 (leaves wrong code on `main`).
11. **Conformance cases are Python adapter cases** on new fixtures (`refactor-tuple-targets`,
    `refactor-move-shadowing`), mirroring `refactor-rename-param-*`; goldens via `LA_UPDATE_GOLDENS=1` for the new
    cases, reviewed like code. (default)

## Risks / Trade-offs

- [A move rewrite the veto skips wrongly] → Function-local import, `global`, `nonlocal`, first-iterable, default
  and annotation cases pin the eligible side, alongside the shadowed side.
- [A function scope that both imports and assigns an alias] → The use is left unchanged (spec scenario); after the
  move it may name a module path that no longer exists. Rare, and the conservative side matches rule 2.
- [The kept function-model patches drift from rope] → Unchanged risk; their tests stay, and DEV-2312 deletes them.
- [DEV-2311 and DEV-2312 overlap] → DEV-2312 finds the evaluator patch and four tests already gone; DEV-2311 must keep
  the new move goldens byte-identical.
