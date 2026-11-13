# Python idioms

The skills stay language-neutral; this is what they mean for a Python repo. Concrete facts (globs, suppression
syntax, waiver, baseline file) come from `la-config get lang.python.<key>`.

## Environment

Run every tool in the project env (the `.venv` the tests use, e.g. `uv run …`), so third-party types resolve.
The type checker is basedpyright (`commands.typecheck.python`, default `basedpyright`); a subdirectory project
sets `basedpyright -p <dir>`, and a checker that is not basedpyright-compatible sets `null`. `la-typecheck`
patches basedpyright in memory for pyright#11919, so pin a verified version (today `1.40.2`) and keep
`NODE_OPTIONS` in the command; otherwise it exits 2.

## Refactoring

`dr-refactor` runs rope, plus the basedpyright bundled with la for every reference the type checker resolves.
Its project scope (`--project`) must include `tests/` so test imports are rewritten too, and it must run in the
project's environment (the `python` on PATH, or the venv in `[tool.basedpyright]`) so third-party types
resolve. Move destinations must exist: a new package is a directory with an `__init__.py`.

A rename rewrites every reference the type checker resolves, across the renamed hierarchy: calls through
annotated or inferred receivers, `super()` calls, forward-reference strings, and keyword arguments of dataclass
and Pydantic fields. For a field of a Pydantic model or `TypedDict`, it also rewrites the keys of dict literals
whose static target is that class. A parameter rename covers every parameter kind: its uses, `name=` keywords at
calls the checker resolves, and the same-named parameter of each override and each `@overload` signature. It
refuses a new name the function already uses.

What a rename leaves unrenamed:
- `x.NAME` where the checker types `x` as `Unknown` or `Any`: `dr-compliance --attr NAME` lists these, so type
  them first (it misses only a subscript or call receiver typed `Model | Any` whose `Model.NAME` is itself `Any`);
- string-only references: `importlib`, `getattr(`, `__all__`, `patch("dotted.path")`, entry points, config
  paths;
- for a parameter rename: keywords that reach it unresolved (`**kwargs` forwarding, a dict unpacked into the
  call). A lambda parameter is refused.
- for a field rename: dict keys that reach the model untyped (through `Any` or `dict[str, Any]`, `**kwargs`
  forwarding, merges, loaded data, a module-level variable), a dict passed by position to an instance method
  whose receiver is not provably its class or an instance (a local `s = Service()`: annotate it or pass by
  keyword) or to a method with a decorator other than `staticmethod`, `classmethod` or `override`, consumers of
  `model_dump()` keyed on the old name, keys and keyword arguments of a field with an
  alias, and keys on a model with an alias generator. Fixtures in a legacy format, validated through a migrating
  `mode="before"` validator, are rewritten like any other typed dict: restore their old keys by hand.

## Compliance fixes (`dr-compliance`)

- `untyped-def` → annotate every parameter and the return.
- `unannotated-attr` → annotate the attribute (class-body `x: T`, or `self.x: T = ...`).
- `mock` → bind the double to a spec: `create_autospec(X, spec_set=True)`, `MagicMock(spec_set=X)`,
  `patch(..., autospec=True)`, or a `Protocol` fake.
- `attr-blindspot` → type the named receiver (its parameter, variable, element type or the return it comes from)
  with the owning class or its `Protocol`, so the checker no longer infers `Unknown` or `Any`.
- `rope-walk` → rope cannot walk this construct, so `dr-refactor` refuses the file. It is a rope bug, not a source error: report it with the named line; rewriting the construct is only a stopgap.
- Overrides carry `@typing.override`, so a renamed base method orphans them visibly.

## Imports

`if TYPE_CHECKING:` and optional-dependency `try:` import wrappers are fine for `import-not-top`;
`TYPE_CHECKING`-only imports never count as architecture edges.

## Suppressions

A per-line suppression with a reason, `# pyright: ignore[<rule>]`, solves a new type error only when the
checker is wrong or the wrongness is deliberate. The baseline is `.basedpyright/baseline.json`.
