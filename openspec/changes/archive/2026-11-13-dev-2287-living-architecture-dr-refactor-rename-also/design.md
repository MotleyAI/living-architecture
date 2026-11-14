## Context

See proposal.md (Why). Facts the design rests on, measured during planning (probes on scratch projects, rope 1.15,
basedpyright 1.40.2):

- rope's rename misses forward-reference strings, Pydantic field keyword arguments, calls through an annotated
  parameter (`a: A` → `a.sync_model(2)`), `super().name(...)`, and every dict-literal key. It renames calls through a
  class-body annotation (`self.store.sync_model`). On any `async def` it raises `RefactoringError` (rope's
  `worder._RealFinder.is_a_class_or_function_name_in_header` accepts only a `def`/`class` prefix), which today
  escapes as a traceback.
- basedpyright's `textDocument/references` from `A.get_model` / `A.sync_model` lists: the forward-reference strings in
  all four shapes, Pydantic keyword arguments including a subclass's and a `type[Model]` receiver's,
  `isinstance`-narrowed receivers, `super()` calls, receivers typed by `self.x: A`, a class-body `store: A`, a
  parameter `a: A`, a `make() -> A` return and an inferred `x = A()`.
- References are per declaration: from `A.get_model` they list neither the override `B.get_model` nor
  `b.get_model()`; from `B.get_model` they list only `B.get_model` and `b.get_model()`.
- basedpyright misses `cls(columns=...)` in a subclass classmethod, `Model.model_construct(columns=...)`, and every
  dict-literal key, including `TypedDict` keys (references on a `TypedDict` key list only the declaration).
- The TypeScript language service already renames contextually typed object-literal keys and leaves an untyped
  literal alone.
- basedpyright's interpreter discovery runs the project's `python3` as `-I -c <print version_info>` with a venv
  configured, and also `-c <print sys.path, prefix>` without one; its script strips the working directory from
  `sys.path`, so no project module is imported.
- `dist/pyright-langserver.js` embeds the same `"../pyright-internal/src/version.json"` module as `dist/pyright.js`,
  so the pyright#11919 preload can recognise and patch it the same way.
- SLayer (`slayer` + `tests`): 496 `model_copy(update={...})`, 179 `model_validate(<name>)`, 9 `model_dump`
  `include`/`exclude`, 2 aliased fields, no `TypedDict` mirroring a model.

Element principles that apply (`architecture/system.arc42.md`):

1. Twins: Python-only behaviour is pinned by Python adapter conformance cases; the TypeScript parity (contextually
   typed object-literal keys) is pinned by a TypeScript scenario and case; `--attr` shares one finding template.
2. Every user-facing text comes from `shared/findings.yaml`.
3. Language-specific code stays in `lang` and `refactor`: the language-server session and the patch preload in
   `python.lang`, the rename union, keyed-class rewrites and `--attr` in `python.refactor`.
4. No target-repo code runs. The language server runs the project's interpreter only to print its version and
   search paths, with the working directory removed from `sys.path`; la additionally starts it with its working
   directory outside the project and `PYTHONSAFEPATH=1`, `PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1`, and a
   test with a hostile repo-root `sitecustomize.py` pins it. The principle stays verbatim (decision 7).

The spec stays on the existing `refactor` capability owned by `python.refactor`. The model gains the arrow
`refactor -> lang` in the python root (the npm twin already has it); the embedded diagram in `system.arc42.md` is
regenerated with `la-arch-diagrams`.

## Goals / Non-Goals

**Goals:**

- After a Python rename, the type-check gate has nothing left to report: the rename's sites are a superset of the
  checker's references, by construction.
- Every rewrite beyond rope's and basedpyright's references is proven from types; anything unproven is left
  unchanged, never guessed.
- Identical inputs give identical output: one patched, pinned basedpyright, queried in a fixed order.

**Non-Goals:**

- Releasing or bumping versions, and pinning the release in SLayer: the bump PR and DEV-1607 do that (decision 6).
- Widening la-typecheck's verified basedpyright versions (DEV-2288).
- A Python `explicit-any` compliance check (DEV-2289).
- Dict keys that reach a model untyped (`Any`, `dict[str, Any]`, `**kwargs` forwarding, merges, loaded data),
  `model_dump()` result subscripts, and keys of aliased fields: listed in `plugin/languages/python.md` for the
  deterministic-refactor skill's grep step (decisions 5, 11).
- Pydantic dataclasses, `RootModel` and `TypeAdapter` as dict targets.
- A leftover report from `dr-refactor` (decision 5).
- Changing module renames, `move-symbol` or `move-module`.

## Decisions

1. **Engine: rope's edits ∪ basedpyright's references, plus own typed-flow rewrites** (user). Alternatives:
   basedpyright replaces rope for symbol renames (loses rope's override-declaration hierarchy and `--unsure`
   meanings, rewrites goldens, still needs the dict pass); rope only with an own pass resolving class occurrences
   (re-implements typing partially, misses `type[...]` and narrowed receivers). The union makes the mutator's sites a
   superset of the gate's references by construction and keeps every current rope behaviour.
2. **basedpyright is a bundled, pinned dependency** (user): `basedpyright==1.40.2` moves from the `verify` extra into
   `dependencies`. It lives in la's own tool environment, not the project's; the project's gate may run another
   version or mypy. It reads the project's configuration and interpreter like the gate does. Alternative: derive the
   language server from `commands.typecheck.python` (brittle command surgery; no source with `typecheck: null` or
   mypy). DEV-2146 rejected bundling basedpyright as *the gate*; here it is only the reference engine.
3. **Extra flows: `model_construct`, `model_copy(update=)`, `model_dump`/`model_dump_json` `include`/`exclude`, and a
   dict variable bound once** (user), on top of the issue's core (`model_validate`, `Cls(**...)`, nested literals,
   `cls(...)`).
4. **TypedDicts and Pydantic models are one "keyed class" rule** (user). A model-field rename never touches a
   `TypedDict` or the reverse: nothing is linked by name.
5. **No leftover report** (user). The deterministic-refactor skill's gate already greps the string-only references
   after the apply, which lists exactly the unproven keys.
6. **The release bump and the SLayer pin are out of scope** (user). Releases go through the bump PR; DEV-1607 pins
   the release.
7. **system.arc42.md principle 4 is not edited** (user). Interpreter discovery runs no target-repo code; the evidence
   is in Context and pinned by the `sitecustomize` test.
8. **DEV-2288 tracks widening la-typecheck's verified versions** (user), raised because projects should not be forced
   onto la's basedpyright.
9. **The second issue comment's `--attr` gap is in scope** (user): Python `--attr` reports `Unknown`/`Any` receivers
   through basedpyright, at parity with the TypeScript twin. Avoiding `Any` remains the fix: the skill types each
   reported receiver.
10. **Upstream rope: the `async def` fix is already python-rope/rope#859** (user). Nothing is opened upstream; a
    comment on #859 confirms it fixes rename too, with the minimal `Rename` repro. The patch's comment names #859 as
    its removal trigger.
11. **A Python `explicit-any` check is a separate change** (user): DEV-2289, with its own worktree.
12. **The language server runs with la's pyright#11919 patch** (user). The preload in `python.lang` also patches
    `dist/pyright-langserver.js`, keyed on the same embedded version; an unpatched server is a failure. This needs
    the model arrow `refactor -> lang` (python root). Alternative: an unpatched server, whose answers can depend on
    analysis order.
13. **The union queries every renamed declaration** (default): the whole hierarchy rope renames, or only the located
    declaration with `--no-in-hierarchy`. References are per declaration (Context), so the union matches rope's
    hierarchy choice exactly.
14. **rope's `RefactoringError` prints `refactor.cannot-rename`** (default): the existing neutral text; the spec
    already forbids library text.
15. **Type facts come only from standard LSP requests** (codex): `references`; `definition` and `typeDefinition`
    give declaration locations, which are the identities compared (owner, subclass via the base chain, Pydantic's
    `model_construct`); `hover` is read only to detect an `Unknown` or `Any` member of a type. Formats are fixed by
    the exact bundled pin and pinned by tests. No internal pyright API.
16. **A key is rewritten only when the field's MRO lookup on the target class lands on a renamed declaration**
    (codex). A union other than one keyed class with `None`, a type variable, `Any` or `Unknown` leaves the key.
17. **`cls` and `model_construct` are resolved, not spelled** (codex): `cls` must be typed `type` of K or a
    subclass; `model_construct` must resolve to `BaseModel.model_construct`.
18. **Edits are spans over one snapshot** (codex): every file is read once, every edit is a character span in that
    text, spans may not overlap unless identical, and a file changed before the write aborts the whole run with
    nothing written. Rejected part (codex): an extra walker check for files with added edits — rope already scans
    every file containing the name, so the walker-gap guard covers them.
19. **LSP positions are UTF-16 and are converted against the snapshot** (codex).
20. **Aliased fields get no key rewrites, documented as a blind spot** (codex, narrowed): a field declaring `alias`
    or `validation_alias`, or a model with an `alias_generator`. Fails closed; SLayer has 2 such fields.
21. **The single-binding variable rule is a strict subset** (codex): one `name = {literal}` binding, no
    `global`/`nonlocal`, no capture by an inner scope, every load a direct sink argument; any other use, `del` or
    augmented assignment disqualifies.
22. **`--attr` output is canonical** (codex): the receiver's source text with whitespace runs collapsed, one finding
    per access position, sorted by path, line and column; `Unknown`, `Any` or a union containing either is reported.
23. **One language-server session per command, a syntactic prefilter, deduplicated and cached queries** (codex).
    Rejected part (codex): timing budgets in CI, which would be flaky; a manual SLayer timing is recorded instead.
24. **`refactor.unresolved-base` refuses only field renames** (codex, narrowed): keyed-class membership cannot be
    decided with an unresolved base; class, function, method and module renames proceed.
25. **A dry-run and a failure leave the whole tree unchanged, checked by snapshot** (codex); server logs and caches
    go outside the project.
26. **Every added or changed finding has a golden** (codex): `refactor.pyright-failed`, `refactor.unresolved-base`,
    `compliance.pyright-failed`, the changed `compliance.attr-blindspot`, and `refactor.cannot-rename` from the
    Python twin; `compliance.ts-attr-blindspot` is retired. `refactor.file-changed` (decision 41) needs a concurrent
    edit no corpus case can make, so it is pinned by a unit test and listed in `UNPRODUCED_BY_DESIGN`.
27. **Each precondition and fail-closed branch is a named scenario** (codex), with dry-run and apply variants for
    failures that occur after rope computed its changes.
28. **The interpreter probe is isolated** (codex): server working directory outside the project,
    `PYTHONSAFEPATH=1`, `PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1`, pinned by the `sitecustomize` test.
29. **A key is rewritten only as a plain literal, name characters only** (default): no implicit concatenation,
    escape or f-string; the prefix and quotes stay.
30. **A key or keyword collision reuses `refactor.name-conflict`** (default).
31. **The Pydantic method names (`model_validate`, `model_construct`, `model_copy`, `model_dump`,
    `model_dump_json`) stay in code** (default): adapter knowledge, not contract parameters.
32. **The `verify` extra is removed** (default): basedpyright is a plain dependency now.
33. **TypeScript gets no code change beyond the shared `--attr` template id** (default): its language service already
    renames contextually typed keys.
34. **Before-validators are ignored** (default): a legacy-format fixture validated through a migrating
    `mode="before"` validator is rewritten like any other typed dict; python.md says so.
35. **`refactor.pyright-failed`** (user, approved wording):
    `'basedpyright could not find the references, so nothing was refactored'`
36. **`refactor.unresolved-base`** (user, approved wording):
    `'{name} has a base basedpyright cannot resolve at {path}:{line}, so nothing was refactored; run dr-refactor in the project environment'`
37. **`compliance.attr-blindspot`** (user, approved wording), shared by both twins:
    `'{path}:{line}: attr-blindspot: {receiver}.{attr} — {receiver} is {type}, so a rename of .{attr} is unverifiable'`
38. **`compliance.pyright-failed`** (user, approved wording):
    `'basedpyright could not type the receivers of .{attr}'`
39. **`plugin/languages/python.md`, Refactoring section** (user, approved wording), replacing the text from
    "`dr-refactor` runs rope." to the end of the string-only paragraph:

    > `dr-refactor` runs rope, plus the basedpyright bundled with la for every reference the type checker resolves.
    > Its project scope (`--project`) must include `tests/` so test imports are rewritten too, and it must run in the
    > project's environment (the `python` on PATH, or the venv in `[tool.basedpyright]`) so third-party types
    > resolve. Move destinations must exist: a new package is a directory with an `__init__.py`.
    >
    > A rename rewrites every reference the type checker resolves, across the renamed hierarchy: calls through
    > annotated or inferred receivers, `super()` calls, forward-reference strings, and keyword arguments of dataclass
    > and Pydantic fields. For a field of a Pydantic model or `TypedDict`, it also rewrites the keys of dict literals
    > whose static target is that class.
    >
    > What a rename leaves unrenamed:
    > - `x.NAME` where the checker types `x` as `Unknown` or `Any`: `dr-compliance --attr NAME` lists these, so type
    >   them first;
    > - string-only references: `importlib`, `getattr(`, `__all__`, `patch("dotted.path")`, entry points, config
    >   paths;
    > - for a field rename: dict keys that reach the model untyped (through `Any` or `dict[str, Any]`, `**kwargs`
    >   forwarding, merges, loaded data), consumers of `model_dump()` keyed on the old name, and keys of a field with
    >   an alias or on a model with an alias generator. Fixtures in a legacy format, validated through a migrating
    >   `mode="before"` validator, are rewritten like any other typed dict: restore their old keys by hand.
40. **`plugin/languages/python.md`, compliance fix** (user, approved wording):
    "`attr-blindspot` → type the named receiver (its parameter, variable, element type or the return it comes from)
    with the owning class or its `Protocol`, so the checker no longer infers `Unknown` or `Any`."
41. **`refactor.file-changed`** (user, approved wording), exit 1, nothing written:
    `'{path} changed while dr-refactor ran, so nothing was refactored'`

## Risks / Trade-offs

- [The PyPI install grows by basedpyright and its Node wheel] → accepted (decision 2); la-typecheck users already
  install it for the gate.
- [A rename is slower: one workspace analysis per run] → one session, prefilter and caches (decision 23); a manual
  SLayer timing is recorded in tasks.
- [basedpyright's `hover` text format may change on upgrade] → it is used only to detect `Unknown`/`Any`, the pin is
  exact, and the scenarios fail on a format change, so an upgrade is a deliberate, tested step.
- [The bundled basedpyright differs from the project's gate version] → a reference only ours finds is still a real
  reference; one only theirs finds is reported by the gate.
- [Run outside the project's environment, Pydantic does not resolve] → field renames refuse with
  `refactor.unresolved-base` (decision 24); `--attr` over-reports, which is visible.
- [Legacy-format fixtures get rewritten] → documented in python.md (decision 34).
