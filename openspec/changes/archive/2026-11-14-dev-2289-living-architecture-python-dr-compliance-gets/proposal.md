## Why

The TypeScript `dr-compliance` reports every `any` type; the Python twin reports no explicit `Any` at all, so a
Python repo learns where `Any` blinds a rename only through `--attr NAME`, one attribute at a time. Python
`dr-compliance` needs the same `explicit-any` check, in its default set, so the diff-compliance sweep drives `Any`
out of the code a refactor touches.

## What Changes

- Python `dr-compliance` gains the `explicit-any` check: one finding per reference in the file that resolves, by
  static analysis of the source alone, to `typing.Any` or `typing_extensions.Any` — annotations at any depth,
  string forward references, type comments, and every other type expression (`cast`, `TypeVar` bounds, aliases,
  generic calls and bases). First-party re-exports of `Any` are followed through the project's own modules.
- `explicit-any` joins Python's default check set: `untyped-def`, `unannotated-attr`, `explicit-any`, `mock`,
  `rope-walk`. A default run on a file that references `Any` now reports it; on any other file the output is
  unchanged.
- The `compliance.explicit-any` template becomes shared by both twins, taking the language's spellings of the any
  type and the safe top type from two new language facts. TypeScript's output is byte-identical.
- The `dr-compliance` help, `docs/deterministic-refactoring.md` and `plugin/languages/python.md` list the check and
  its fix.

## Capabilities

### New Capabilities

### Modified Capabilities
- `refactor`: Python's compliance check set adds `explicit-any`, and a new requirement specifies the Python
  `explicit-any` check.

## Impact

- `shared/languages.yaml` (Python check list, `any_type`, `top_type`), `shared/findings.yaml`
  (`compliance.explicit-any` parameters), `shared/cli.yaml` (`dr-compliance` help), and every twin's snapshot.
- Python twin: a new check module in `living_architecture.refactor`, wired into `compliance.py`.
- npm twin: `node/src/refactor/compliance.ts` passes its spellings to the template.
- Docs: `docs/deterministic-refactoring.md`, `plugin/languages/python.md`.
- Tests and conformance: Python unit tests, contract tests of both twins, new Python adapter cases, and
  `compliance-select-other-language-check` switched to a TypeScript-only id.
