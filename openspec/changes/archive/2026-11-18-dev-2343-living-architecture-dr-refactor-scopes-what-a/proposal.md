## Why

A rename's edits to prose (`--docs`) and to literals have one scope: every mention of the word in a declaring file,
every matching literal. That is too wide in places (another class's docstring, a versioned stored document), stuck in
one (a docstring two map entries reach is refused in Python and silently listed in TypeScript), and too narrow in
others (strings in a mini-language such as Cypher are never respelled). The only control is a per-file or per-line
`--keep`. DEV-2343 covers DEV-2340 items 9, 22, 10 and 12.

## What Changes

- `--docs` resolves every mention once over all entries of a run, to one entry or to a listed `leftover`, in both
  twins. A code-marked bare mention inside a class is rewritten only for that class's own member; outside any such
  class only when every declaration of the old name in the file is renamed to one name.
- **BREAKING** The "opens its string before `:`, `(` or whitespace" code mark is removed: a plain word in a string is
  rewritten only when qualified.
- **BREAKING** A docs mention two map entries reach is no longer refused with `refactor.map-conflict` (Python) nor
  listed for every entry regardless of class (TypeScript): it is resolved by its owning class, else listed.
- New flag `--docs-pick PATH:LINE[=ENTRY]` on `rename` and `rename-map`: rewrites the listed mentions on that line.
- New flag `--keep-literal KEY` on `rename` and `rename-map`: a dict or object literal holding the key KEY is kept
  whole from every rewrite.
- New config key `refactor.string_forms`: patterns declaring strings of a mini-language that carry a class or
  module-level symbol's name; such strings are respelled with the symbol, with or without `--docs`.
- Declined: a declaration for untyped document bodies (REST `json=`, MCP arguments). They stay `--docs` leftovers,
  resolved by `--docs-pick` or by typing the body (design.md, decision 7).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `refactor`: the `--docs` requirement changes (owning class, no string-opening mark, one resolution over all
  entries); three requirements are added (`--docs-pick`, `--keep-literal`, declared string forms).

## Impact

- `shared/`: `cli.yaml` (two flags on `rename` and `rename-map`), `findings.yaml` (four findings),
  `schema/living-architecture.schema.json` and `config.yaml` (`refactor.string_forms`), `regex-subset.md` (names the
  second key that uses the subset); every twin's snapshot through `scripts/sync-shared`.
- Python twin: `refactor/mentions.py`, `rename_union.py`, `rename_map.py`, `outcomes.py`, `sites.py`, config loading.
- npm twin: `refactor/mentions.ts`, `rename.ts`, `outcomes.ts`, `sites.ts`, config loading.
- `conformance/`: new cases, and deliberate golden updates where a case pins the string-opening rewrite or a docs
  `map-conflict`.
- Docs and skill: `docs/deterministic-refactoring.md`, `docs/configuration.md`, `docs/refactoring-internals.md`,
  `plugin/skills/deterministic-refactor/SKILL.md`.
- Versions: a minor bump of both packages and `plugin.json` (tool inputs change).
- Architecture: no model or arc42 change. System principles 1 (twins identical), 2 (surfaces only from the shared
  contract) and 3 (language-specific code only in `lang` and `refactor`) apply.
