# deterministic-refactor

Rename and move Python code with automatic import/reference rewriting — and,
the actual point, a **deterministic check that the refactor left nothing
dangling**.

The rename tool (`rope`) is best-effort: no refactoring tool reliably rewrites
every type-annotated `obj.attr`, `super()` call, and subclass override. So it is
never trusted — it is *verified*. A strict type-check proves no dangling static
reference remains; `@typing.override` turns a missed override into an error; a
mock-spec lint turns a missed dynamic (mock) reference into a failure. Green ⇒
provably no dangling reference.

Tools (`pip install deterministic-refactor`):
- `dr-refactor` — rope mutator: `rename` / `move-symbol` / `move-module`
- `dr-mock-lint` — fail on mocks not bound to a spec
- `dr-compliance` — report the constructs that make a refactor un-verifiable

## What a fully compliant repo must fulfill

A repo is *refactor-verifiable* when a missed rename is **guaranteed to surface
as a failing check**. That holds only when:

1. **Target code is typed.** Functions annotated (params + return), class
   attributes annotated, and every variable/parameter that holds an instance of
   a class annotated. An unannotated `x.attr` is unresolvable, so a miss there
   is invisible — determinism is bought with type coverage. (`dr-compliance` +
   Ruff `ANN*` enforce this.)
2. **A type checker runs against the project's own environment.** mypy or
   basedpyright resolving imports via the project venv — the *same* interpreter
   the tests use — passing, or at a recorded baseline.
3. **Overrides are marked.** `@typing.override` on every override, with
   `reportImplicitOverride` (basedpyright) or mypy strict enabled, so a base
   rename that orphans an override is an error, not a silent break.
4. **Mocks are spec-bound.** No bare `Mock()`/`MagicMock()`/`patch()`; every
   double bound via `spec_set=` / `autospec=True` / a `Protocol` fake. A stale
   mock member then fails (`AttributeError`, or a type error for typed fakes).
   (`dr-mock-lint` enforces this.)
5. **The gate is wired into CI/pre-commit.** type-check (no new errors vs
   baseline) + `dr-mock-lint` + the test suite, on every change.

`dr-compliance` mechanically checks 1, 3-adjacent (via the type checker), and 4,
and reports each violation as `file:line: <kind>: <message>`.

## Using it on an existing repo

### 1. One-time setup

- Install the tools in a tooling venv (or `uvx deterministic-refactor`, or add
  to the dev group).
- Add a type checker to the project's dev dependencies, pointed at its venv —
  it must resolve imports the way the tests do:

  ```toml
  # pyproject.toml
  [tool.basedpyright]
  venvPath = "."
  venv = ".venv"
  pythonVersion = "3.11"
  typeCheckingMode = "standard"      # already errors on attribute access
  reportImplicitOverride = "error"
  ```

  (Equivalently `mypy --strict --python-executable .venv/bin/python`.)
- Add `dr-mock-lint <tests>` and the type checker to `.pre-commit-config.yaml`
  and CI. Record the current type-error set as the baseline — you do **not**
  need a clean whole repo, only "no *new* errors" per change.

The mutator (`rope`) does **not** belong in the project's dependencies — it
reads source and needs nothing installed. Only the verifier needs the env.

### 2. Keep every PR compliant — skill `make-diff-compliant`

Bring exactly the files a PR touches up to the five conditions before it merges,
so compliance grows monotonically with the diff instead of requiring a big-bang
migration. The skill runs `dr-compliance` on the changed files, adds the missing
annotations / `@override` / mock specs, and loops until the type checker and
`dr-mock-lint` are clean on the diff. See `skills/make-diff-compliant/`.

### 3. Do a refactor — skill `deterministic-refactor`

Locate the symbol with the editor/LSP → `dr-refactor` dry-run → apply → run the
gate (type checker shows no new errors, `dr-mock-lint` passes, tests pass, grep
the string-only references no static tool sees) → review the diff. See
`skills/deterministic-refactor/`.

### 4. Make a refactor's blast radius compliant first — skill `make-refactor-target-compliant`

Before renaming `X` or `X.attr`, close the blind spots the gate would otherwise
miss: code that *might* reference the target but is currently invisible to the
checker — untyped parameters/variables that could hold an `X`, classes whose
attribute names match the target ("right-looking" names), subclasses missing
`@override`. The skill drives `dr-compliance --attr <name>` to enumerate those
sites, annotates them, and re-checks until the blast radius is fully typed —
so the post-rename gate is sound. See `skills/make-refactor-target-compliant/`.
