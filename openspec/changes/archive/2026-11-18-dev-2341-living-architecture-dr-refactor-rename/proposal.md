## Why

A rename leaves a string stale although the string names the renamed member through a static link: a Pydantic
validator's field name, a `model_fields` key, a `__slots__` entry, a name read with `getattr` from a constant tuple, a
`monkeypatch.setattr(module, "name", …)` target, a `Literal` value held in a constant. The run is clean, or the string
is one `leftover` among prose mentions, and the code then fails at import or at run time where the type checker does
not see it. DEV-2340 items 3, 23, 5b and 4 found each form in a real rename.

## What Changes

- A Pydantic field rename rewrites the field-name strings of `field_validator` and `field_serializer`, and the
  field names read from `model_fields` and `model_fields_set`.
- An attribute rename rewrites its entry in `__slots__` and `__match_args__`.
- A rename of a module-level symbol rewrites the member argument of a string-member form whose object is a project
  module.
- A string held by a name is followed to its literal sources: a once-bound local, module constant or class constant,
  and the elements of a once-bound display a loop iterates. A `Literal` member rename and a member rename both
  rewrite the source; every other read of it is listed with the new `refactor.unverified-read`.
- A TypeScript literal-member rename checks the edited program in memory and refuses on a new checker error it could
  not rewrite, as Python already does. Today it exits 0 on a program that no longer compiles.
- **BREAKING** A string-named access on an untyped receiver is the new check `string-blindspot`, with a variant for a
  call whose miss raises no error. `--select attr-blindspot` no longer reports these sites.
- `compliance.attr-required` and `compliance.attr-unselected` name either attribute check.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `refactor`: new requirements for field-name strings, class-body name tuples, module receivers, literal sources and
  the listing of unverified reads; the compliance check sets, the blind-spot refusal, the Python and TypeScript
  `--attr` checks and the literal-member rename change.

## Impact

- `shared/languages.yaml` (name-string forms, the `string-blindspot` check, the silent fact), `shared/findings.yaml`
  (three new templates, two changed), `shared/cli.yaml` (`--attr` help), then `scripts/sync-shared`.
- `python/src/living_architecture/refactor/` and `node/src/refactor/`: the form scan, the literal-source resolver,
  the literal-member rename, the compliance checks.
- `conformance/cases/` and `conformance/INVENTORY.md`: new cases per form; the goldens of every case printing a
  string form as `attr-blindspot`, and of `refactor-literal-narrowed-local` and
  `refactor-literal-import-routes-blindspot`, change.
- Versions: a minor bump of both packages and `plugin.json`.
- No architecture model or arc42 change.
