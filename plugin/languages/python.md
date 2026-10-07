# Python idioms

The skills stay language-neutral; this is what they mean for a Python repo. Concrete facts (globs, suppression
syntax, waiver, baseline file) come from `la-config get lang.python.<key>`.

## Environment

Run every tool in the project env (the `.venv` the tests use, e.g. `uv run …`), so third-party types resolve.
The type checker is basedpyright (`commands.typecheck.python`, default `basedpyright`); a subdirectory project
sets `basedpyright -p <dir>`, and a checker that is not basedpyright-compatible sets `null`.

## Refactoring

`dr-refactor` runs rope. Its project scope (`--project`) must include `tests/` so test imports are rewritten
too. Move destinations must exist: a new package is a directory with an `__init__.py`. For refactors that hinge
on third-party types, run `dr-refactor` under the project's venv Python. rope reflows imports: run the
formatter (ruff/black) afterwards.

Known rope misses the type-check gate catches: receivers narrowed by `isinstance` rather than annotation
(e.g. `other.attr` inside `__eq__`), and constructor keyword arguments of dataclass/Pydantic fields
(`Cls(attr=...)`). A stale `from old import X` or `old_mod.X` surfaces even in untyped code — module members
resolve without annotations.

String-only references no static tool sees: `importlib`, `getattr(`, `__all__`, `patch("dotted.path")`, entry
points, config paths, and — for a Pydantic field rename — `model_copy(update={"NAME": ...})` / `model_dump`
consumers keyed on the old name.

## Compliance fixes (`dr-compliance`)

- `untyped-def` → annotate every parameter and the return.
- `unannotated-attr` → annotate the attribute (class-body `x: T`, or `self.x: T = ...`).
- `mock` → bind the double to a spec: `create_autospec(X, spec_set=True)`, `MagicMock(spec_set=X)`,
  `patch(..., autospec=True)`, or a `Protocol` fake.
- `attr-blindspot` → annotate the named parameter with the owning class (or its `Protocol`).
- Overrides carry `@typing.override`, so a renamed base method orphans them visibly.

## Imports

`if TYPE_CHECKING:` and optional-dependency `try:` import wrappers are fine for `import-not-top`;
`TYPE_CHECKING`-only imports never count as architecture edges.

## Suppressions

A per-line suppression with a reason, `# pyright: ignore[<rule>]`, solves a new type error only when the
checker is wrong or the wrongness is deliberate. The baseline is `.basedpyright/baseline.json`.
