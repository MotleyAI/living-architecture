# Shared contract

The source of truth both twins obey. Each package vendors a byte-copy of this directory (refreshed by
`scripts/sync-shared`) and loads only that copy at runtime.

| File | Defines |
|---|---|
| `schema/living-architecture.schema.json` | config keys, types, bounds, cross-field rules, defaults |
| `schema/index.schema.json` | the `architecture/index.yaml` shape |
| `findings.yaml` | every finding, verdict and hint, by id; the arch-check ids |
| `cli.yaml` | every command's options, positionals, subcommands and exit codes |
| `conventions.yaml` | conventions-gate rules and the waiver syntax |
| `languages.yaml` | per-language extensions, test globs, comment prefix, suppression syntax |
| `regex-subset.md` | the portable `issue_key_pattern` subset |
| `vectors/` | input/output vectors both test suites consume |
| `scripts/` | the review helpers (bash, `gh`, `jq`) |

## YAML profile

YAML 1.1 exactly as PyYAML's safe loader reads it: `yes`/`no`/`on`/`off` are booleans, sexagesimal and
`0`-prefixed octal integers are numbers, merge keys apply, and a duplicate mapping key takes the last value.

## Configuration

1. Parse with the YAML profile; a missing or empty file is an empty mapping.
2. Validate against the schema (JSON Schema 2020-12).
3. Fill defaults recursively: an absent property with a `default` takes it; an absent object whose
   sub-schema has defaulted properties is created and filled. Explicit values, including `false`, `0`, `[]`,
   `""` and `null`, are never replaced, and a `default` is never merged into an explicit object.

## Templates

`{name}` inserts a string as is and any other value as its canonical repr; `{name!r}` inserts the canonical
repr; `{{` and `}}` are literal braces. A multi-line template renders to several output lines.

## Canonical repr

Python's `repr` for normalized values only: str, int, float, bool, null, list, mapping. Strings use single
quotes unless they contain `'` and no `"`; `\\`, `\n`, `\r`, `\t` and the quote in use are escaped; other
non-printable characters become `\xNN`, `\uNNNN` or `\UNNNNNNNN`. Floats use the shortest round-trip form
(`1e+16`, `1.5e-07`, `inf`). Pinned by `vectors/repr.yaml`.

## Glob dialect

Matched against the POSIX repo-relative path, case-sensitively. A pattern is split on `/`; a `**` segment
matches zero or more whole path segments; inside any other segment `*` matches any run of characters
(dots included) and every other character is literal. Pinned by `vectors/glob.yaml`.

## Contract hash

`CONTRACT_HASH` in each snapshot is the hex sha256 of, for every file except `CONTRACT_HASH` in ascending
byte order of its POSIX relative path: the path, `NUL`, `1` if executable else `0`, `NUL`, the byte length in
decimal, `NUL`, the bytes.
