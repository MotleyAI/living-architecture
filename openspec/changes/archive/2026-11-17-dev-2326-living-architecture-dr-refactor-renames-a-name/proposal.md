## Why

`dr-refactor` 0.11.0 refuses to rename any name bound by a tuple assignment (`ds_name, model_name = s.split(".", 1)`):
the toolkit's rope evaluator patch reads `a, model_name = …` as a call keyword and resolves it to nothing. Python
renames on `main` no longer go through rope's evaluator, so the refusal is gone there, but nothing specifies or tests
tuple-target renames, and the faulty patch is still installed. Probing it showed that moves, which still use rope's
occurrences, rewrite a use of a lambda, function or comprehension parameter that shadows an import alias.

## What Changes

- Python renames of a name bound by a tuple target (of an assignment in a function, at module level or in a class
  body, starred and nested targets included, or of a comprehension's `for` clause) are specified and pinned by
  conformance cases, by `--symbol` and by location, through `rename` and `rename-map`. A `name=` call keyword is never
  renamed with a same-named variable of the enclosing scope; a same-spelled binding in a nested scope is not renamed.
- Python `move-symbol` and `move-module` leave a use unchanged when the name it reads is bound, in the function,
  lambda or comprehension scope it is read in, by anything other than an import the move rewrites (a parameter of any
  kind, an assignment, a comprehension target). The source module of a `move-symbol` gets no import of the moved
  name for such a use. `global` and `nonlocal` names and a comprehension's first iterable resolve in the scope Python
  gives them.
- The rope evaluator patch (`get_primary_and_pyname_at`), whose call-keyword branch caused the refusal, is removed;
  the rope function-model and call-argument patches that moves still depend on stay.
- No release in this change: a separate release commit carries it, and SLayer's pin moves to that release.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `refactor`: two added requirements, Python renames of names bound by tuple targets and Python moves leaving
  names bound in a function-like scope unchanged.

## Impact

- `python/src/living_architecture/refactor/rope_patches.py` (evaluator patch removed; `every_parameter` moves out),
  `python_source.py` (gains `every_parameter`), `symbol_path.py`, `rename_union.py`, `retarget.py` (use it),
  `move_edits.py` (occurrence eligibility, `_Scopes` fixes).
- `python/tests/test_rope_parameters.py` (four evaluator-level tests removed), new unit tests, new conformance
  fixtures and cases under `conformance/`, `conformance/INVENTORY.md`.
- Python twin only; the npm twin forwards Python inputs to it. No `shared/` change, no version bump, no model or arc42
  change.
