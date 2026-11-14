## Why

The Python `dr-refactor rename` refuses every keyword-only and positional-only parameter with `cannot-rename`,
because rope's function model lists only positional-or-keyword parameters plus `*args`/`**kwargs`. Even where a
parameter does rename, a method parameter skips the overrides and `@overload` signatures of its function, and a new
name the function already uses yields invalid code or silently captures its uses. SLayer passes almost every argument
by keyword, so its vocabulary rename (DEV-1607) is blocked on this.

## What Changes

- rope's function model lists positional-only parameters in its positional binding vector and keyword-only parameters
  in its scope and keyword lookup (a rope patch); a `name=` keyword resolves only to a positional-or-keyword or
  keyword-only parameter, never to a positional-only one, `*args` or `**kwargs`.
- A parameter of any kind renames its declaration, every use in its function and every `name=` keyword at calls the
  checker resolves to a renamed declaration, located at any of them.
- A method parameter rename covers the same-named parameter of every declaration in the method's renamed hierarchy
  (following `--no-in-hierarchy`), and every parameter rename covers the same-named parameter of each member of the
  function's `@overload` group.
- A parameter rename whose new name a renamed function already binds or reads is refused with
  `refactor.name-conflict`; a lambda parameter is refused with `refactor.cannot-rename`.
- `plugin/languages/python.md` states what a parameter rename covers and leaves unrenamed.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `refactor`: Python renames gain parameters of every kind, their hierarchy and overload groups, keyword-site
  resolution limited to keyword-bindable parameters, the parameter name-conflict refusal and the lambda refusal.

## Impact

- Code: `python/src/living_architecture/refactor/` (`rope_patches.py`, `rename_union.py`, `keyed.py` for
  overload resolution).
- Tests: Python unit tests, new adapter (python) conformance cases with `conformance/INVENTORY.md` rows.
- Docs: `plugin/languages/python.md`.
- No `shared/` change (existing findings only), no architecture model change, no new dependency.
- Downstream: release 0.8.0 after merge, pinned in SLayer's DEV-1607 branch (not part of this change's diff).
