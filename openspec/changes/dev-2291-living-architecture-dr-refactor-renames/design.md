## Context

See proposal.md (Why). Facts measured during planning (scratch projects, rope 1.15, basedpyright 1.40.2, la 0.7.0):

- rope's `PyFunction.get_param_names` returns `args.args` plus `vararg`/`kwarg`; `get_parameters` builds the function
  scope's parameter names from it, and `evaluate` resolves a call's `name=` keyword through `get_parameters()`. So a
  keyword-only or positional-only parameter is unresolvable at its declaration, its body uses and its keywords, and
  `Rename(...)` raises `RefactoringError` (mapped to `refactor.cannot-rename`). `**kwargs` and plain parameters rename.
- A probe patching `get_param_names` to every kind in signature order made keyword-only renames rewrite the
  declaration, body and resolved keywords. But rope's `Arguments.get_pynames` binds call arguments by index into
  `get_param_names(special_args=False)`, and `soi._parameter_objects` builds the inference vector from it, so a
  keyword-only name in that list would receive surplus positional arguments meant for `*args`. Today rope also binds
  `def f(a, /, b)`'s first argument to `b`.
- rope's keyword lookup returns `**kwargs`'s or `*args`'s parameter for `f(kwargs=...)` / `f(args=...)`, and would
  return a positional-only one for a keyword that actually lands in `**kw`.
- A method-parameter rename covers no override, for any parameter kind: renaming `A.run(model_name)` rewrote
  `a.run(model_name=)` and the `super().run(model_name=)` keyword but left `B.run`'s parameter and
  `b.run(model_name=)`. basedpyright's references from a parameter list its body uses and the keywords of calls
  resolved to that one declaration.
- Renaming an implementation's parameter leaves every `@overload` stub's parameter unchanged.
- Renaming to a name the signature already holds produces `def g(*, dataset_name, dataset_name)`.
- rope builds no scope for a lambda: every lambda parameter is refused with `cannot-rename`.
- `TypeFacts._decorator` in `keyed.py` already resolves a method's decorators through basedpyright (not by spelling).

Element principles that apply (`architecture/system.arc42.md`):

1. Twins: the behaviour is Python-only (the npm twin routes `.py` sources to the PyPI twin), so it is pinned by
   Python adapter conformance cases.
2. Every user-facing text comes from `shared/findings.yaml`: only the existing `refactor.cannot-rename` and
   `refactor.name-conflict` are printed; `shared/` is unchanged.
3. Language-specific code stays in `refactor` (`python.refactor`); it already imports `lang`, so no model edge changes.
4. No target-repo code runs: rope and basedpyright analyse statically, as today.

The spec attaches to the existing `refactor` capability (owned by `python.refactor`); no architecture model or arc42
edit.

## Goals / Non-Goals

**Goals:**

- Remove the cause, not the instance: rope's function model knows every parameter kind, and a parameter has one
  definition of its renamed declarations, used for every kind.

**Non-Goals:**

- Lambda parameter renames: they stay a `cannot-rename` refusal, pinned by a scenario (decision 7).
- Body-capture conflict checks for renames of non-parameter symbols (decision 6).
- Keyword sites the checker cannot resolve: `**mapping` unpacking, `**kwargs` forwarding, `functools.partial`.
- Pairing a `.pyi` stub with its `.py` implementation in another file (rejected (codex), decision 11).
- Upstreaming the rope patch.
- The 0.8.0 release and the SLayer pin: post-merge steps in tasks.md (decision 8).

## Decisions

1. **Every parameter kind gets one contract** (user): declaration, body uses, resolved keyword sites, hierarchy and
   overload group, for positional-only, positional-or-keyword, keyword-only, `*args` and `**kwargs` alike.
   Alternative: keyword-only alone, as the issue words it (leaves the positional-only refusal unspecified and the
   positional override gap standing).
2. **The refusal is fixed in rope's function model, with two separate concepts** (default, revised by codex), as a
   patch in `rope_patches.py` beside the other rope model fixes, installed by `apply_rope_patches`:
   - the *positional binding vector* (`get_param_names`) is positional-only then positional-or-keyword parameters,
     then `*args`/`**kwargs` as today (special-argument handling and indices follow it);
   - keyword-only parameters join the *scope and keyword lookup* (`get_parameters`) only, with the object rope's
     parameter type-hint provider gives (docstring types; rope reads no parameter annotations) or unknown, never
     filled positionally;
   - keyword lookup at a call returns only a positional-or-keyword or keyword-only parameter (codex).
   Alternatives: one signature-ordered list (corrupts positional binding and inference); a `rename`-local special case
   (leaves rope's scope wrong for every other path).
3. **A parameter's renamed declarations** (user, via 1): the parameters named `old` of (a) every declaration of the
   enclosing method's renamed hierarchy, computed exactly as a method rename computes it and following
   `--no-in-hierarchy`, and (b) every member of each such declaration's overload group. Each is seeded into the
   existing basedpyright reference pass, which supplies the body uses and resolved keywords of each.
4. **Overrides are matched by parameter name** (default): an override whose parameter has another name, or that lacks
   it, is unchanged. The old name is the keyword contract; positions are not.
5. **Overload groups always follow** (user), with or without `--no-in-hierarchy`. A group is every same-named `def` of
   one module or class body when at least one carries a decorator basedpyright resolves to `typing.overload` or
   `typing_extensions.overload` (via the decorator resolution already in `TypeFacts`, extended with an overload
   kind). Locating at any member renames the whole group; the method hierarchy is computed from the group's
   implementation, or from the located `def` without one (codex).
6. **Name conflicts** (user): refused with `refactor.name-conflict` when any renamed declaration's function binds or
   reads the new name as a variable in its signature or body, nested scopes included, at a site the rename does not
   itself rewrite (so a rename to the old name is a successful no-op, codex). Attribute names and keywords of calls to
   other functions do not count. The reported site is the first by project-relative path, then character offset
   (codex). Not extended to non-parameter renames.
7. **Lambda parameters stay refused** (user) with `refactor.cannot-rename`; no tracker issue. rope has no lambda scope,
   and giving it one is a far larger intervention than the `def` fix.
8. **Release and SLayer pin are post-merge** (user): this change carries no version bump; tasks.md records the 0.8.0
   release and the pin on SLayer's DEV-1607 branch; DEV-2291 stays open until the pin lands.
9. **Python adapter conformance cases with generated goldens** (default, codex): every scenario has a case, goldens
   are written with `LA_UPDATE_GOLDENS=1` (new cases) and reviewed like code; none is `golden: manual`.
10. **Regression coverage for the rope patch** (codex): mixed-kind signatures for the binding vector and inference
    (`def f(a, /, b, *xs, c, **kw)`, positional plus keyword calls, an omitted defaulted keyword-only argument,
    instance/class/static receivers), and existing refactors (`move-symbol`, method rename) over such signatures.
11. **No `.pyi` stub pairing** (rejected (codex)): pairing a stub file with its implementation is a general rename
    concern; today's rename pairs none for any symbol.
12. **`plugin/languages/python.md` wording** (user, approved wording). Appended to the paragraph ending "…whose static
    target is that class.":
    "A parameter rename covers every parameter kind: its uses, `name=` keywords at calls the checker resolves, and the
    same-named parameter of each override and each `@overload` signature. It refuses a new name the function already
    uses."
    Added to "What a rename leaves unrenamed", after the string-only references bullet:
    "- for a parameter rename: keywords that reach it unresolved (`**kwargs` forwarding, `functools.partial`, a dict
    unpacked into the call). A lambda parameter is refused."

## Risks / Trade-offs

- [The rope patch changes behaviour shared by every rope path la uses] → the change to the binding vector only adds
  positional-only parameters in their true position; keyword-only parameters never enter it; decision 10's
  regression tests and the full suite cover rename and move-symbol.
- [A rope upgrade changes `PyFunction`'s internals] → rope is pinned; the patch's unit tests fail on drift.
- [The conflict check refuses a harmless rename (a dead read of a global)] → the finding names the site; the user
  renames it first.
- [Keywords reaching a function through `**kwargs` forwarding stay unrenamed] → documented in python.md
  (decision 12); the type-check gate reports the resulting unknown keyword where the target is typed.
