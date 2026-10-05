# conventions Specification

## Purpose
The deterministic conventions gate (`la-check-conventions`) and the comment counter (`la-count-comments`) for
every supported language, with one report whichever twin runs them.

## Requirements

### Requirement: Files are routed to a language by extension
Each file's language SHALL be the shared languages-registry entry whose source extensions contain the file's
extension. A diff-derived file list SHALL include every changed file with a known extension, after the exempt
globs, and SHALL silently ignore other files. An explicitly given path (`--file`, `la-count-comments` arguments)
whose extension is unknown SHALL be skipped with one stderr warning naming it, and SHALL NOT affect the exit
code. Changed files SHALL be listed with NUL-delimited git output, so that paths containing spaces, non-ASCII
characters or a leading dash are checked under their real names; deleted files SHALL be excluded and a renamed
file SHALL be checked under its new path.

#### Scenario: Mixed diff routed per file
- **WHEN** the diff against the base changes `src/a.py`, `web/b.ts` and `README.md`
- **THEN** `src/a.py` is checked by the Python adapter, `web/b.ts` by the TypeScript adapter, and `README.md` is ignored without a message

#### Scenario: Explicit unknown extension skipped with a warning
- **WHEN** `la-check-conventions --file notes.md --file src/a.py` runs
- **THEN** stderr warns that `notes.md` is skipped, `src/a.py` is checked, and the exit code depends only on `src/a.py`

#### Scenario: Non-ASCII path checked
- **WHEN** the diff changes `src/données.py`
- **THEN** that file is checked and its violations are reported under its real name

#### Scenario: Rename across languages
- **WHEN** the diff renames `src/a.js` to `src/a.py`
- **THEN** only `src/a.py` is checked, by the Python adapter

### Requirement: Other-language files are analysed through a facts document
A twin SHALL analyse files of its own language in-process. For files of another language it SHALL request
facts from that language's twin with internal options, passing the ordered path list on stdin. A facts request
SHALL be served only natively: a twin asked for another language's facts SHALL exit 2 without starting any
other process. The served document SHALL be one JSON document valid against the shared conventions-facts schema,
carrying the language, version and contract hash and, per path in input order, its status (`ok`, `missing`,
`unreadable` or `syntax-error`), the failure line and message for failures, and for analysed files the
detections (line, rule, message id, values, and the text of the flagged line), the text-only and total line
counts, and the comment and doc line counts. The requesting twin SHALL treat a missing, malformed or
schema-invalid document, an identity mismatch, or a process ended by a signal as a protocol failure (exit 2 with
the shared message), and SHALL relay a non-zero exit's stderr and exit 2. An unreachable twin SHALL exit 2 with
the shared install hint.

#### Scenario: Same output from either twin
- **WHEN** `la-check-conventions --base main` runs through the PyPI twin and through the npm twin on the same mixed repo
- **THEN** both runs produce byte-identical stdout, stderr and exit codes

#### Scenario: Facts request for a non-owned language
- **WHEN** the PyPI twin receives a conventions facts request for `typescript`
- **THEN** it exits 2 without starting any other process

#### Scenario: Malformed conventions facts
- **WHEN** the other twin's facts run exits 0 but prints a document that fails the schema
- **THEN** the gate exits 2 with the shared protocol-failure message

#### Scenario: Twin unreachable for a mixed diff
- **WHEN** a Python repo's diff touches `web/b.ts` and no npm twin is on `PATH` and `npx` is absent
- **THEN** the gate exits 2 and stderr names the npm twin, its version and its install command

#### Scenario: Long path list
- **WHEN** a facts request carries more paths than fit in one command line
- **THEN** it succeeds and the facts keep the input order

### Requirement: The gate report is computed once in the invoking twin
Waivers, test-file classification, the tests-only filter, text-ratio, ordering and the verdict SHALL be computed
by the invoking twin from the facts. A waiver SHALL be the shared waiver pattern after the language's comment
prefix on the detection's line, and SHALL NOT apply to text-ratio. Violations SHALL be ordered by path across
languages, then by line and rule. Text-ratio SHALL be aggregated over two groups, `source` and `tests`, across
languages. The files label in the summary and verdict SHALL list the files label of each language with at least
one checked file, in language-id order, joined with ` and `, and SHALL be `source` when no file was checked.
The RED verdict's waiver example SHALL use the comment prefix of each language with at least one checked file, in
language-id order, joined with ` or `.
Single-language runs SHALL otherwise keep their current output byte for byte.

#### Scenario: One verdict for a mixed diff
- **WHEN** a diff has a violation in `src/a.py` and another in `web/b.ts`
- **THEN** both violations print in path order, followed by one summary naming `.py and TS/JS` and one verdict

#### Scenario: Ratio groups span languages
- **WHEN** a diff changes source files in both languages
- **THEN** one `source` ratio line covers the lines of both

#### Scenario: Empty change set
- **WHEN** the diff contains no file with a known extension
- **THEN** the summary and the clear verdict name `source` files

### Requirement: TypeScript import-not-top
In TS/JS files the gate SHALL flag a static import (`import` declaration including `import type`, or
`import x = require('y')`) that follows any other module-level statement, allowing only prologue directives
before imports; a top-level `require()` declaration ends the prologue. It SHALL flag a `require('…')` call with an
identifier callee that is not at module scope, by the ancestor allow-list of n/global-require. `export … from`,
dynamic `import()` anywhere, type-position `import('x')`, and imports inside `declare module` or namespace bodies
SHALL NOT be flagged.

#### Scenario: Import after code
- **WHEN** `src/a.ts` has `const x = 1;` followed by `import { y } from './y';`
- **THEN** the import's line is reported under `import-not-top`

#### Scenario: Directive prologue allowed
- **WHEN** `src/a.ts` starts with `'use client';` followed by imports
- **THEN** no `import-not-top` violation is reported

#### Scenario: require inside a function
- **WHEN** `src/a.cjs` calls `require('fs')` inside a function body
- **THEN** that line is reported under `import-not-top`

#### Scenario: Dynamic import allowed
- **WHEN** `src/a.ts` calls `await import('./b')` inside a function
- **THEN** no violation is reported

#### Scenario: Re-export at the bottom
- **WHEN** a barrel `src/index.ts` ends with `export * from './c';` after other statements
- **THEN** no violation is reported

### Requirement: TypeScript composite-assert
In TS/JS test files the gate SHALL flag `expect(X)`, `assert(X)` and `assert.ok(X)` where `X`, with parentheses
stripped, is a `&&` expression. `||` SHALL NOT be flagged.

#### Scenario: Composite expect
- **WHEN** `src/a.test.ts` contains `expect(a && b).toBe(true)`
- **THEN** that line is reported under `composite-assert`

#### Scenario: Not a test file
- **WHEN** `src/a.ts` contains `assert(a && b)`
- **THEN** no violation is reported

### Requirement: TypeScript raises-single-throw
In TS/JS test files the gate SHALL count call and `new` expressions in: the function argument of `expect(fn)`
followed by `toThrow`, `toThrowError`, `toThrowErrorMatchingSnapshot` or `toThrowErrorMatchingInlineSnapshot`;
the argument of `expect(x)` followed by `.rejects`; and the first argument of `assert.throws` or `assert.rejects`.
When the count exceeds one it SHALL flag the line where the asserting call starts. `.not.toThrow*` SHALL NOT be
flagged.

#### Scenario: Two calls under toThrow
- **WHEN** `src/a.test.ts` contains `expect(() => parse(load())).toThrow()`
- **THEN** that line is reported under `raises-single-throw` with 2 calls

#### Scenario: Rejects with one call
- **WHEN** `src/a.test.ts` contains `await expect(fetchIt()).rejects.toThrow()`
- **THEN** no violation is reported

#### Scenario: Negated matcher
- **WHEN** `src/a.test.ts` contains `expect(() => a(b())).not.toThrow()`
- **THEN** no violation is reported

### Requirement: TypeScript waivers
A trailing `// ALLOW(<rule>): <reason>` comment on the line where a flagged construct starts SHALL waive that
rule's violation there, except for text-ratio.

#### Scenario: Waived import
- **WHEN** a late import in `src/a.ts` carries `// ALLOW(import-not-top): generated`
- **THEN** no violation is reported for it

### Requirement: TypeScript line sets
For TS/JS files, a text-only line SHALL be a non-blank line holding only comment text and whitespace, counting
every line a block or JSDoc comment spans and excluding lines with code; the total SHALL be all lines. For
`la-count-comments`, doc lines SHALL be the lines spanned by `/** … */` comments other than `/**/`, and comment
lines SHALL be the lines of every other comment, trailing comments included; each category SHALL count distinct
lines, and a shebang SHALL count as neither. Files SHALL be decoded as strict UTF-8 with a leading BOM ignored;
invalid UTF-8 SHALL be reported as `unreadable`. Line breaks SHALL be `\r\n`, `\n` and `\r`. A file with a
syntax error SHALL be reported with the first syntactic diagnostic's line and message, SHALL be excluded from
text-ratio, and SHALL still have its comment lines counted. The output format of `la-count-comments` SHALL be the
same as for Python.

#### Scenario: JSDoc counted as doc
- **WHEN** `la-count-comments src/a.ts` runs on a file with a 3-line JSDoc block and two `//` lines
- **THEN** it reports doc 3 and comment 2

#### Scenario: Trailing comment is not text
- **WHEN** a TS source line is `const a = 1; // note`
- **THEN** it does not count as a text-only line

#### Scenario: CRLF and BOM
- **WHEN** a TS file starts with a UTF-8 BOM and uses CRLF line breaks
- **THEN** its line counts equal those of the same file without the BOM and with LF line breaks

#### Scenario: Invalid UTF-8
- **WHEN** a changed `.ts` file contains an invalid UTF-8 byte sequence
- **THEN** it is reported as `unreadable`

### Requirement: Comment counts over a git range
`la-count-comments --range REF PATH...` SHALL compare each path's working-tree version with its version at `REF`,
using the base version's bytes unchanged, for every language.

#### Scenario: TS range
- **WHEN** `la-count-comments --range HEAD src/a.ts` runs after adding one JSDoc line
- **THEN** it reports a net added doc count of 1

### Requirement: The conventions gate enforces only the configured rules
`la-check-conventions` SHALL report findings only for rules listed in `conventions.rules`. With an empty
list it SHALL report no rule findings and exit 0. A file's `unreadable` or `syntax-error` finding SHALL be
reported iff at least one configured rule applies to that file. A waiver comment for a rule that is not
configured SHALL have no effect.

#### Scenario: One rule dropped
- **WHEN** the config sets `conventions.rules: [import-not-top]` and a changed source file breaches the text-ratio cap and has an import inside a function
- **THEN** only the `import-not-top` finding is reported and the command exits 1

#### Scenario: Test-only rules dropped
- **WHEN** the config sets `conventions.rules: [import-not-top, text-ratio]` and a changed test file has `assert a and b`
- **THEN** no `composite-assert` finding is reported

#### Scenario: Gate off
- **WHEN** the config sets `conventions.rules: []` and a changed file breaches every rule
- **THEN** the command reports nothing and exits 0

#### Scenario: Syntax error with the gate off
- **WHEN** the config sets `conventions.rules: []` and a changed `.py` file does not parse
- **THEN** no `syntax-error` finding is reported and the command exits 0

#### Scenario: Syntax error with a rule on
- **WHEN** the config sets `conventions.rules: [text-ratio]` and a changed `.py` file does not parse
- **THEN** the `syntax-error` finding is reported and the command exits 1

#### Scenario: Default keeps every rule
- **WHEN** the config does not set `conventions.rules` and a changed test file has `assert a and b`
- **THEN** the `composite-assert` finding is reported

#### Scenario: TypeScript test file
- **WHEN** the config sets `conventions.rules: [text-ratio]` and a changed `src/a.test.ts` has `expect(a && b).toBe(true)`
- **THEN** no `composite-assert` finding is reported
