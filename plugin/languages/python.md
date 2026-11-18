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

`dr-refactor` resolves a rename's occurrences with the basedpyright bundled with la and computes every rename and move itself.
Its project scope (`--project`) must include `tests/` so test imports are rewritten too, and it must run in the
project's environment (the `python` on PATH, or the venv in `[tool.basedpyright]`) so third-party types
resolve. Move destinations must exist: a new package is a directory with an `__init__.py`.

`dr-refactor` checks its output before it writes. It refuses when an edited file would no longer parse or its
encoding cannot hold the new text. A move also refuses with `FILE:LINE: NAME would not resolve as it does now`
when a name would mean something else after it. Nothing is written in either case. Move that declaration by
hand; if the move looks correct to you, report the line.

A rename rewrites every reference the type checker resolves, across the renamed hierarchy: calls through
annotated or inferred receivers, `super()` calls, forward-reference strings, and keyword arguments of dataclass
and Pydantic fields. For a field of a Pydantic model or `TypedDict`, it also rewrites the keys of dict literals
whose static target is that class. A parameter rename covers every parameter kind: its uses, `name=` keywords at
calls the checker resolves, and the same-named parameter of each override and each `@overload` signature. It
refuses a new name the function already uses.

A rename also rewrites a member named by string on an object the checker types: `getattr`, `setattr`, `hasattr`,
`delattr`, `monkeypatch.setattr` / `delattr` and `patch.object` (also `mocker.patch.object`), and each segment of a
`patch`, `mocker.patch` or `monkeypatch.setattr` / `delattr` target that resolves statically to a renamed
declaration. A field rename also rewrites the field's name in `field_validator` and `field_serializer` and where it is
read from `model_fields` or `model_fields_set`; an attribute rename its entry in `__slots__` and `__match_args__`; a
rename of a module-level symbol the member string of those calls on a project module
(`monkeypatch.setattr(mod, "name", …)`). A member rename refuses while a receiver of the old name is `Unknown` or `Any` (`--allow-blindspots`
overrides) or a class outside the hierarchy declares the old name (`--with` / `--without`).

A rename of a `Literal` member (`--symbol Alias['value']`) rewrites each string the checker types by that
`Literal`: arguments, assignments, returns, comparisons, `in` tests and `match` cases. Where the checker
needs the old value at a name, it rewrites the one literal that name holds (a once-bound local, module constant or
class constant, the elements of a constant tuple a loop reads) and lists every other read of that name as
`unverified-read`. It refuses (`literal-unresolved`) where the name has no such literal: bound twice, a conditional
value, declared in a stub. `retarget` refuses
while a subclass overrides the alias. `--apply` keeps `.basedpyright/baseline.json` aligned by running
`commands.typecheck.python` over the files it changes.

What a rename leaves unrenamed:
- receivers `--allow-blindspots` let through; `dr-compliance --attr` misses only a subscript or call receiver typed
  `Model | Any` whose `Model.NAME` is itself `Any`;
- string-only references: `importlib`, `__all__`, entry points, config paths, strings equal to a renamed `Literal`
  member that the checker does not type by it (`str` variables, `argparse` `choices`; each listed as a `leftover`),
  a member named by a string the rename cannot follow to one literal (`getattr(obj, name)` with `name` a parameter or
  bound twice), and a `patch` target that
  does not resolve into the project (listed as a `leftover`);
- mentions in comments, docstrings, messages and prose files: all of them without `--docs`; with it, the ones it
  lists as `leftover`;
- for a parameter rename: keywords that reach it unresolved (`**kwargs` forwarding, a dict unpacked into the
  call).
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
- `explicit-any` → a real type (a dict of known keys becomes a `TypedDict` or a Pydantic model), or `object`
  narrowed where it is used.
- `mock` → bind the double to a spec: `create_autospec(X, spec_set=True)`, `MagicMock(spec_set=X)`,
  `patch(..., autospec=True)`, or a `Protocol` fake.
- `attr-blindspot` → type the named receiver (its parameter, variable, element type or the return it comes from)
  with the owning class or its `Protocol`, so the checker no longer infers `Unknown` or `Any`.
- `string-blindspot` → the same fix, for a member named by a string (`getattr(x, "NAME")`,
  `x.model_fields["NAME"]`). A line ending `and a miss raises no error` (`hasattr`, `getattr` with a default) fails
  silently after a rename, so fix it first.
- `rope-walk` → rope cannot walk this construct, so `dr-refactor` refuses a move whose files include it. It is a rope bug, not a source error: report it with the named line; rewriting the construct is only a stopgap.
- Overrides carry `@typing.override`, so a renamed base method orphans them visibly.

## Imports

`if TYPE_CHECKING:` and optional-dependency `try:` import wrappers are fine for `import-not-top`;
`TYPE_CHECKING`-only imports never count as architecture edges.

## Suppressions

A per-line suppression with a reason, `# pyright: ignore[<rule>]`, solves a new type error only when the
checker is wrong or the wrongness is deliberate. The baseline is `.basedpyright/baseline.json`.
