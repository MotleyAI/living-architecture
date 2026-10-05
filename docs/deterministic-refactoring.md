# Deterministic refactoring

Rename and move Python or TypeScript code with automatic import/reference rewriting — and, the actual point, a
**deterministic check that the refactor left nothing dangling**.

The mutator is best-effort: no refactoring tool reliably rewrites every type-annotated `obj.attr`, `super()`
call, and subclass override. So it is never trusted — it is *verified*. A strict type check proves no dangling
static reference remains; marked overrides turn a missed override into an error; a mock lint turns a missed
dynamic (mock) reference into a failure. Green ⇒ provably no dangling reference.

Tools (both twins, routed by each file's language):
- `dr-refactor` — the mutator: `rename` / `move-symbol` / `move-module`. Python runs rope; TypeScript runs the
  bundled TypeScript language service, one per project of the tsconfig's reference graph.
- `dr-mock-lint` — fail on test doubles not bound to the real type
- `dr-compliance` — report the constructs that make a refactor un-verifiable

`dr-refactor` prints one unified diff per changed file (and a `rename from`/`rename to` pair per moved file);
it is a dry run unless `--apply` comes before the subcommand. Locate the symbol with `--line [--col]`
(1-based), `--offset` (0-based) or `--name` (first declaration, else first use).

## What a fully compliant repo must fulfill

A repo is *refactor-verifiable* when a missed rename is **guaranteed to surface as a failing check**. That holds
only when:

1. **Target code is typed.** Functions' parameters typed (Python: returns too), class attributes typed, and
   every variable/parameter that holds an instance of a class typed. An untyped `x.attr` is unresolvable, so a
   miss there is invisible — determinism is bought with type coverage.
2. **A type checker runs against the project's own environment** — basedpyright (or mypy) in the project
   venv, `tsc --noEmit` against the repo's `node_modules` — passing, or at a recorded baseline (`la-typecheck`).
3. **Overrides are marked**, so a base rename that orphans an override is an error, not a silent break:
   `@typing.override` with `reportImplicitOverride` (basedpyright) or mypy strict; the `override` modifier with
   `noImplicitOverride`.
4. **Test doubles are typed.** Python: no bare `Mock()`/`MagicMock()`/`patch()`, every double bound via
   `spec_set=` / `autospec=True` / a `Protocol` fake. TypeScript: `vi.fn<typeof real>()` (or an
   implementation), module factories typed against the module (`vi.mock(import('./m'), …)`,
   `jest.mock<typeof import('./m')>('./m', …)`), and no `as unknown as T` in tests.
5. **The gate is wired into CI/pre-commit**: `la-typecheck` (no new errors vs baseline) + `dr-mock-lint` + the
   test suite, on every change.

`dr-compliance` checks each file with its language's checks and reports each violation as
`file:line: <kind>: <message>`:

| Language | Checks |
|---|---|
| Python | `untyped-def`, `unannotated-attr`, `mock` |
| TypeScript | `tsconfig` (`strict`, `noImplicitAny`, `noImplicitOverride` enabled), `explicit-any`, `untyped-def` (implicitly-`any` parameters, as the type checker sees them), `mock` |

`--select` picks a subset; `--attr NAME` also reports `x.NAME` accesses on untyped receivers.

## Using it on an existing repo

### 1. One-time setup

- Install the tools (see the [README](../README.md#install)).
- Set up the type checker against the project's own environment. For Python, in the project's dev
  dependencies:

  ```toml
  # pyproject.toml
  [tool.basedpyright]
  venvPath = "."
  venv = ".venv"
  pythonVersion = "3.11"
  typeCheckingMode = "standard"      # already errors on attribute access
  reportImplicitOverride = "error"
  ```

  For TypeScript, `tsc` in `node_modules` and `strict` plus `noImplicitOverride` in the tsconfig.
- Record the current error set as the baseline (`la-typecheck --write-baseline`) — you do **not** need a clean
  whole repo, only "no *new* errors" per change — and add `la-typecheck` and `dr-mock-lint <tests>` to CI.

The mutators do **not** belong in the project's dependencies — they read source and need nothing installed.
Only the verifier needs the environment.

### 2. Keep every PR compliant — skill `make-diff-compliant`

Bring exactly the files a PR touches up to the five conditions before it merges, so compliance grows
monotonically with the diff instead of requiring a big-bang migration. The skill runs `dr-compliance` on the
changed files, fixes what it reports, and loops until `la-typecheck` and `dr-mock-lint` are clean on the diff.
See [`la:make-diff-compliant`](../plugin/skills/make-diff-compliant/SKILL.md).

### 3. Do a refactor — skill `deterministic-refactor`

Locate the symbol with the editor/LSP → `dr-refactor` dry-run → apply → run the gate (`la-typecheck` shows no
new errors, `dr-mock-lint` passes, tests pass, grep the string-only references no static tool sees) → review
the diff. See [`la:deterministic-refactor`](../plugin/skills/deterministic-refactor/SKILL.md).

### 4. Make a refactor's blast radius compliant first — skill `make-refactor-target-compliant`

Before renaming `X` or `X.attr`, close the blind spots the gate would otherwise miss: code that *might*
reference the target but is currently invisible to the checker — untyped parameters/variables that could hold
an `X`, classes whose attribute names match the target ("right-looking" names), unmarked overrides. The skill
drives `dr-compliance --attr <name>` to enumerate those sites, types them, and re-checks until the blast radius
is fully typed — so the post-rename gate is sound. See
[`la:make-refactor-target-compliant`](../plugin/skills/make-refactor-target-compliant/SKILL.md).

The per-language idioms the skills rely on are in [`plugin/languages/`](../plugin/languages/).
