# shared-contract Specification

## Purpose
The single contract both native implementations (the PyPI and npm twins) obey. Parameters, defaults,
user-facing wording and the command surface are defined once as shared data. A conformance corpus pins every
observable output so the twins cannot drift.

## Requirements

### Requirement: YAML is read with one fixed profile
The YAML files the tools read (`living-architecture.yaml`, `living-architecture.local.yaml`, `architecture/index.yaml`
and the bundled `shared/` data) SHALL be read as YAML 1.1 as PyYAML's safe loader reads them, within a closed tag set:
`yes`/`no`/`on`/`off` are booleans. A scalar the safe loader cannot construct (an impossible date such as
`2024-13-01`, or `!!int`/`!!float` content that is not a number) SHALL be a YAML error, reported like any other
invalid YAML, never a crash.

A mapping that repeats a key SHALL be a YAML error, at any depth, including inside an anchored mapping. Two keys
of one mapping are the same key when their loaded values, normalized (a timestamp to its ISO string), are equal
under these rules: two strings are equal when their code points are; `null` equals only `null`; booleans, integers
and floats compare as exact numbers, `false` and `true` counting as `0` and `1` and `-0.0` as `0`; `.inf` and
`-.inf` equal only themselves; a NaN equals a NaN; a string never equals a number or `null`. An alias key counts
as the value it resolves to. A second merge key (a plain `<<` or a `!!merge` node) in one mapping SHALL be a
repeated key too. A key that a merge brings in SHALL NOT count: an explicit key overriding a merged one, and keys
shared by the mappings of one merge, stay as PyYAML merges them. The error SHALL be worded by the shared
`yaml.duplicate-key` template, naming the key (the first occurrence's normalized value, as its canonical repr) and
the 1-based lines where the two occurrences start (an alias key where the alias stands). With several repeats, the
error SHALL name the repeat that comes first in the document, paired with the first occurrence of that key.

The tag set SHALL be `!!str`, `!!int`, `!!float`, `!!bool`, `!!null`, `!!timestamp`, `!!seq`, `!!map` and
`!!merge`, in any spelling (shorthand, verbatim or through a `%TAG` handle); a non-specific `!` on any node SHALL
resolve as if the node were untagged, and on a scalar as if the scalar were plain whatever its style. Any other tag
(`!!binary`, `!!set`, `!!omap`, `!!pairs`, the `!!value` a plain `=` resolves to, a local or unknown tag) SHALL be a YAML error, as SHALL a merge key (a plain `<<` or a `!!merge`
node) anywhere but a mapping key, and a mapping key that is a sequence or mapping, directly or through an alias. An
anchor or alias name SHALL consist of ASCII letters, digits, `-` and `_`, and end at whitespace or one of
``?:,]}%@` ``; any other character there SHALL be a YAML error. A raw NEL (U+0085), U+2028 or U+2029 anywhere in
the input SHALL be a YAML error; the `\N`, `\L` and `\P` escapes in a double-quoted scalar SHALL NOT. For every such file a repo actually writes, both twins SHALL load the same value or both SHALL report a YAML error;
YAML no real config uses, such as a `!!merge`-tagged sequence or mapping as a key, is outside this guarantee.

#### Scenario: YAML 1.1 boolean
- **WHEN** the config sets `reviewers: {codex: no}`
- **THEN** the resolved `reviewers.codex` is `false`

#### Scenario: Duplicate key
- **WHEN** a mapping in the config repeats a key
- **THEN** every command that reads it, through either twin, reports invalid YAML in the config naming the key and
  both lines, and exits as for any other YAML error

#### Scenario: Duplicate key at depth
- **WHEN** a YAML input holds `r: {s: {t: 1, t: 2}}`, or an anchored mapping that repeats a key
- **THEN** both twins report the duplicate key `'t'` (or the anchored mapping's key) with both lines

#### Scenario: Keys equal by loaded value
- **WHEN** a mapping holds the keys `a` and `"a"`, `0x1` and `1`, `1` and `1.0`, `1` and `true`, `false` and `0`,
  `~` and `null`, `-0.0` and `0`, `1:30` and `90`, `9007199254740992` and `9007199254740992.0`, `!!int "1"` and
  `1`, two `.nan` keys, or a timestamp and the quoted string of its ISO form
- **THEN** both twins report a duplicate key

#### Scenario: Keys that differ
- **WHEN** a mapping holds the keys `!!str 1` and `1`, `9007199254740993` and
  `9007199254740992.0`, or `.inf` and a large integer
- **THEN** both twins load every key

#### Scenario: Repeated merge key
- **WHEN** a mapping holds two `<<` merge keys
- **THEN** both twins report the duplicate key `'<<'` with both lines

#### Scenario: Merge override is not a duplicate
- **WHEN** a mapping merges `*base` holding `y: 2` and sets `y: 3` itself, or merges two mappings that both hold `x`
- **THEN** both twins load the mapping as PyYAML merges it

#### Scenario: Alias key
- **WHEN** a mapping holds the key `*k`, where `&k s` anchors the scalar `s`, and the key `s`, in either order
- **THEN** both twins report the duplicate key `'s'` with the line of the alias and the line of the other key

#### Scenario: Several repeats
- **WHEN** a mapping holds `a` on lines 1, 2 and 3
- **THEN** both twins report the duplicate key `'a'` at lines 1 and 2

#### Scenario: Unconstructible scalar
- **WHEN** the config holds `2024-13-01` as a plain scalar
- **THEN** every command that reads it reports invalid YAML in the config and exits as for any other YAML error

#### Scenario: Unconstructible scalar beside a duplicate key
- **WHEN** a YAML input holds a scalar the safe loader cannot construct and also repeats a mapping key
- **THEN** both twins report the scalar as invalid YAML, not the duplicate key

#### Scenario: Tag outside the closed set
- **WHEN** the config sets `reviewers: !!set {codex}`, or any value tagged `!!binary`, `!!omap` or `!!pairs`
- **THEN** every command that reads it, through either twin, reports invalid YAML in the config and exits as for any
  other YAML error

#### Scenario: Merge key outside a mapping key
- **WHEN** a YAML input holds `<<` as a plain value or sequence item, or a `!!merge` node as a value
- **THEN** both twins report a YAML error

#### Scenario: Quoted or string-tagged merge spelling is a plain key
- **WHEN** a mapping has the key `'<<'` or `!!str <<` with a mapping value
- **THEN** both twins load it as the literal key `<<` and merge nothing

#### Scenario: Collection as a mapping key
- **WHEN** a mapping key is a sequence or mapping, written inline or as an alias of an anchored collection
- **THEN** both twins report a YAML error

#### Scenario: Non-specific tag
- **WHEN** a YAML input holds `! 12`, `! '12'`, `! [1]` or `! {a: 1}`
- **THEN** both twins load the integer `12` (twice), the list `[1]` and the mapping `{a: 1}`

#### Scenario: YAML 1.1 anchor names
- **WHEN** an anchored scalar `&k s` is aliased as a flow mapping key directly followed by a colon (`{*k: a}`)
- **THEN** both twins load the mapping `{s: a}`, and an anchor named `a.b` is a YAML error in both

#### Scenario: Non-ASCII line breaks
- **WHEN** a YAML input contains a raw NEL, U+2028 or U+2029 (as a line break, after an anchor name, or inside a scalar)
- **THEN** both twins report a YAML error, and `"\N\L\P"` loads to those three characters in both

### Requirement: Issue-key patterns use the portable regex subset
`issue_key_pattern` SHALL be accepted only when it uses the portable subset documented in the contract:
- literals
- character classes including `\d`, `\w`, `\s`
- quantifiers including `{m,n}`
- anchors
- groups
- alternation

Lookbehind, named groups, inline flags, and possessive or atomic constructs SHALL be rejected as a
configuration error. Accepted patterns SHALL be applied with full-match semantics. A tag id containing any
non-ASCII character SHALL never match, in every twin.

#### Scenario: Default pattern accepted
- **WHEN** no `issue_key_pattern` is configured
- **THEN** the default `[A-Z][A-Z0-9]+-\d+` is used and `[target: ABC-123]` tags are accepted

#### Scenario: Non-portable construct rejected
- **WHEN** `issue_key_pattern` is `(?<=X)[A-Z]+-\d+`
- **THEN** loading the configuration fails with a configuration error naming `issue_key_pattern`

#### Scenario: Non-ASCII tag id never matches
- **WHEN** `issue_key_pattern` is `\w+-\d+` and an arc42 principle carries `[target: ÄBC-123]`
- **THEN** both twins report `enforced-tags.target-mismatch` for it

### Requirement: User-facing texts come from the shared findings registry
Every finding line, gate verdict and hint that a command prints SHALL be rendered from a template in the
shared findings registry, identified by a stable id. A `{name}` placeholder SHALL insert the value as text.
A `{name!r}` placeholder SHALL insert the canonical repr defined by the contract. That repr covers only
normalized values (string, integer, float, boolean, null, list, mapping). It SHALL match Python's `repr`
for those values, including quote selection and escapes, and it is pinned by shared test vectors. Every
registry template SHALL be exercised by at least one conformance case.

#### Scenario: Registry coverage
- **WHEN** the test suite runs
- **THEN** it fails if any template id in the findings registry is not produced by at least one conformance golden

#### Scenario: Repr of a string containing a quote
- **WHEN** a `!r` placeholder receives the string `it's`
- **THEN** it renders as `"it's"`, matching the shared repr vector

#### Scenario: Repr of a non-scalar YAML value
- **WHEN** `index.yaml` sets `legacy_arrows.baseline: [1, 2]`
- **THEN** the `baseline-ratchet` finding renders the value as `[1, 2]`, byte-identical to the frozen golden

### Requirement: Command surfaces come from the shared CLI manifest
The set of `la-*` and `dr-*` commands, and each command's subcommands, options, types, choices, repeatability,
required options and positionals, SHALL be defined by the shared CLI manifest. Each installed command SHALL
build its parser from it. Parsing SHALL accept no abbreviated long options and SHALL honour `--`. A usage
error SHALL exit 2. A command declared `passthrough` SHALL hand its raw arguments to its handler. Options the
manifest marks internal SHALL be accepted but omitted from help. The manifest SHALL declare, for each
language-specific command, the languages whose twin implements it natively; a command declaring none is
neutral. The manifest SHALL mark the commands exempt from the format check (`la-arch-migrate`, `la-doctor` and the
review shims); every other command SHALL run the format check, and a format refusal SHALL exit 2 in every command.
Each package's installed entry points SHALL be exactly the manifest's command set, and every command a
skill references SHALL be in the manifest.

#### Scenario: Entry points match the manifest
- **WHEN** either twin's test suite runs
- **THEN** it fails if that package's installed commands (console scripts or `bin` entries) differ from the manifest's commands in either direction

#### Scenario: Abbreviated option rejected
- **WHEN** `la-check-conventions --bas main` runs through either twin
- **THEN** it exits 2 as a usage error

#### Scenario: Accepted invocation vector
- **WHEN** `la-check-conventions --file a.py --file b.py --exclude 'gen/*'` runs
- **THEN** both files are checked, `gen/*` is exempt, and the exit code and stdout equal the golden

#### Scenario: Internal option hidden
- **WHEN** `la-doctor --help` runs
- **THEN** the help text does not mention `--twin`, and `la-doctor --twin` is still accepted

#### Scenario: Skill references only real commands
- **WHEN** a SKILL.md mentions an `la-*` or `dr-*` command absent from the manifest
- **THEN** the skills test fails naming the command

#### Scenario: Every non-exempt command runs the format check
- **WHEN** either twin's test suite runs each manifest command not marked exempt in a repo whose config declares no `format`
- **THEN** each exits 2 with the missing-format message, and no exempt command is refused by it (`la-doctor` reports
  the missing format as one of its problems instead)

### Requirement: Test-file classification uses the shared glob dialect
Classifying a file as a test file SHALL use the test globs that the shared languages registry declares for
the language. Matching SHALL use the contract's single glob dialect:
- matched against the POSIX repo-relative path
- case-sensitive
- `*` matches within one path segment
- `**` matches zero or more whole segments

For Python, classification SHALL give the same result as today for every path. For TypeScript the globs SHALL
be `**/*.test.*`, `**/*.spec.*`, `**/__tests__/**/*`, `**/__mocks__/**/*`, `**/tests/**/*` and
`**/test/**/*`.

#### Scenario: Python test-file parity
- **WHEN** the classifier runs over the shared vector set (including `tests/x.py`, `a/test/b.py`, `test_x.py`, `pkg/x_test.py`, `conftest.py`, `testing/x.py`, `atest_x.py`, `Tests/x.py`)
- **THEN** each result equals the pre-restructure classification recorded in the vectors

#### Scenario: TypeScript test-file classification
- **WHEN** both twins classify the shared TypeScript vector set (including `src/a.test.ts`, `src/a.spec.tsx`, `src/__tests__/a.ts`, `src/__mocks__/a.ts`, `test/a.ts`, `src/testing/a.ts`, `src/latest.ts`, `src/contest.ts`)
- **THEN** each result equals the vector's expected classification

### Requirement: Vendored contract snapshots match the shared source
Each twin SHALL load its contract only from its own vendored snapshot of `shared/`. Each snapshot SHALL be
byte-identical to `shared/`, with file modes preserved, and SHALL carry a contract hash. `la-doctor` SHALL
report that hash, and both twins' hashes SHALL be equal.

#### Scenario: Stale snapshot detected
- **WHEN** a file under `shared/` changes and a twin's snapshot is not re-synced
- **THEN** that twin's test suite fails and names the sync command

#### Scenario: Built artifact carries the contract
- **WHEN** the wheel is built and installed into a clean environment outside the checkout
- **THEN** every command loads its contract, a review shim runs its bundled script, and `la-doctor` reports the same contract hash as the source tree

#### Scenario: Packed npm package carries the contract
- **WHEN** `npm pack` output is installed into a clean prefix outside the checkout
- **THEN** every command loads its contract, a review shim runs its bundled script, and `la-doctor --contract-hash` prints the same hash as the PyPI twin

### Requirement: Observable outputs reproduce the conformance goldens
Every case in the conformance corpus SHALL be reproduced byte-exactly: exit code, stdout and stderr, after
normalizing only the temporary repo root to `<ROOT>`. Cases SHALL run in a fixed environment (`LC_ALL=C`,
`TZ=UTC`, a fixed terminal width, fixed git identity and dates) with no network access. A case's `languages`
SHALL name the languages of its fixture, and every listed language's overlay SHALL be applied. Each case SHALL
declare one of three kinds:
- **neutral**: one expected output, independent of fixture language
- **paired**: one variant per listed language, each with its own overlay, and expected outputs that are shared
  or per-language
- **adapter**: one language only

The twin that invokes the command SHALL be chosen independently of the fixture languages, and the expected
output SHALL NOT depend on it. Each twin's own suite SHALL run, through its own entry points, the cases whose
fixture languages are none or only its own language, and whose command that twin implements natively; a
cross-twin run SHALL run every case through each twin's entry points.
`--help` text, parser error wording, and runtime-supplied error detail (OS errors, YAML library messages)
SHALL be excluded from byte comparison; a twin SHALL NOT imitate another runtime's error wording.

#### Scenario: Golden reproduced
- **WHEN** a twin's suite executes a case applicable to it
- **THEN** the exit code, stdout and stderr equal the committed golden byte-for-byte

#### Scenario: Golden drift is reported, not rewritten
- **WHEN** an output differs from its golden during a normal test run
- **THEN** the run fails with a diff and leaves the golden untouched; goldens are written only in the explicit update mode

#### Scenario: Git-history case is deterministic
- **WHEN** a case builds its repo from the declared history (commits, branches, a local bare `origin`, and staged, unstaged, untracked, deleted and renamed files) and runs `la-check-conventions --base main`
- **THEN** the changed-file set and the output equal the golden on every supported Python version

#### Scenario: Cross-twin run
- **WHEN** the cross-twin run executes a TypeScript-fixture case through the PyPI twin and a Python-fixture case through the npm twin
- **THEN** each output equals the case's golden byte-for-byte

#### Scenario: Multi-language fixture
- **WHEN** a case lists `languages: [python, typescript]` with kind `neutral`
- **THEN** both the `python/` and `node/` overlays are applied to one repo before the command runs

#### Scenario: OS error detail is the runtime's own
- **WHEN** `la-arch-check` cannot read `architecture/index.yaml`, or `la-arch-diagrams` cannot read a mapped arc42 doc (missing, or a directory), through either twin
- **THEN** both twins exit with the same code, and stderr starts with the contract prefix (`arch_check: ` / `la-arch-diagrams: `) followed by the runtime's own wording, which names the offending path when the file is missing, with no CPython errno text in the npm twin

### Requirement: Configuration parameters are defined only by the shared schemas
Every key, type, constraint and default of `living-architecture.yaml` SHALL be defined only by the shared
JSON Schema for that file, the keys `living-architecture.local.yaml` may set SHALL be defined only by the
shared local schema (which references the main schema's definitions of those keys), and both file names
SHALL come only from the shared contract. Every key and type of `architecture/index.yaml` SHALL be defined
only by the shared index schema, and every key and type of a node's model metadata SHALL be defined only by
the shared node schema. A resolved configuration SHALL equal the input with schema defaults filled in
recursively. Filling SHALL also fill absent parent objects, and SHALL keep explicit `false`, `0`, empty
lists and empty strings. A missing file or an empty file SHALL resolve to all defaults. The index schema
SHALL NOT constrain the values whose problems the arch-check reports as findings (`legacy_arrows`,
`diagrams`, `view_depth`).

#### Scenario: Missing config resolves to schema defaults
- **WHEN** a repo has no `living-architecture.yaml` and `la-config show` runs
- **THEN** it prints the resolved configuration built only from the schema defaults, byte-identical to the frozen golden, and exits 0

#### Scenario: Partial nested config is completed
- **WHEN** the config sets only `reviewers: {sonar: {project_key: o_r}}` and `la-config show` runs
- **THEN** every other key, including `reviewers.codex` and `tracker`, carries its schema default

#### Scenario: Explicit falsy values are kept
- **WHEN** the config sets `conventions: {exempt: [], rules: []}` and `reviewers: {codex: false}`
- **THEN** the resolved configuration keeps the empty lists and `false` rather than substituting defaults

#### Scenario: Unknown key is rejected
- **WHEN** the config contains a key the schema does not define and `la-config show` runs
- **THEN** the command exits 1 and its error names the offending key

#### Scenario: Enumerated value is enforced
- **WHEN** the config sets `tracker: jira`
- **THEN** validation fails, the command exits with the configuration-error code, and the error names `tracker`

#### Scenario: Local schema follows the main schema
- **WHEN** a value is valid for `tracker` or `reviewers.codex` in `living-architecture.yaml`
- **THEN** the same value is valid in `living-architecture.local.yaml`, and a value the main schema rejects is rejected there too

#### Scenario: A finding-level index problem stays a finding
- **WHEN** `index.yaml` sets `legacy_arrows.baseline: -1` and `la-arch-check` runs
- **THEN** it reports the `baseline-ratchet` finding and exits 1, exactly as the frozen golden records, not a schema error with exit 2

#### Scenario: Node metadata validated by the node schema
- **WHEN** a node's model metadata carries a key the shared node schema does not define
- **THEN** `la-arch-check` exits 2 and its error names the element and the key

### Requirement: Repo languages
A registered language SHALL be a repo language when its `commands.typecheck` entry is set explicitly to a
command, or when the repo has one of the language's marker files at the root and at least one file of that
language (tracked, or untracked and not ignored, minus `conventions.exempt`). Every command that depends on the
repo's languages SHALL use this one definition.

#### Scenario: Stray script is not a language
- **WHEN** a repo with `pyproject.toml` and no `tsconfig.json` tracks `docs/static/app.js`
- **THEN** the repo languages are `python` only

#### Scenario: Typecheck turned off keeps the language
- **WHEN** a repo with `tsconfig.json` and `.ts` files sets `commands.typecheck.typescript` to `null`
- **THEN** `typescript` is still a repo language

### Requirement: Language facts through la-config
`la-config get languages` SHALL print the repo languages as a JSON list in registry id order, and SHALL exit 2
outside a git repository. `la-config get lang.<language>.<key>` SHALL print a registry fact for any registered
language, for the public keys `source_extensions`, `source_globs`, `test_globs`, `declaration_globs`,
`comment_prefix`, `suppression`, `waiver`, `baseline_file` and `markers`. `source_globs` SHALL be one glob per
source extension in the contract glob dialect, and `waiver` the language's waiver comment
(`<comment prefix> ALLOW(<rule>): <reason>`). Lists SHALL print as JSON and strings as text. Any other
language or key SHALL exit 2 with the unknown-key message. `la-config show` SHALL be unchanged.

#### Scenario: Repo languages of a mixed repo
- **WHEN** `la-config get languages` runs in a repo with Python and TypeScript files and both markers
- **THEN** it prints `["python", "typescript"]`

#### Scenario: A fact for a language the repo lacks
- **WHEN** `la-config get lang.typescript.suppression` runs in a Python-only repo
- **THEN** it prints `// @ts-expect-error — <reason>`

#### Scenario: Internal registry field refused
- **WHEN** `la-config get lang.python.runner` runs
- **THEN** it exits 2 with the unknown-key message

### Requirement: Doctor checks each repo language's executables
`la-doctor` SHALL report a missing executable for `node` and for `npx` when TypeScript is a repo language.
Outside a git repository it SHALL skip the language-dependent checks. A repo without TypeScript SHALL get
today's output.

#### Scenario: TypeScript repo without node
- **WHEN** `la-doctor` runs in a TypeScript repo with no `node` on PATH
- **THEN** it reports `node` missing and exits 1

#### Scenario: Python repo unchanged
- **WHEN** `la-doctor` runs in a Python-only repo with no `node` on PATH
- **THEN** its output equals today's golden

### Requirement: Skills are language-neutral
A SKILL.md SHALL contain no language-only token from the shared skill-leak list; language idioms SHALL live
only in `plugin/languages/<language>.md`. Every `la-config get <key>` a SKILL.md names SHALL be a valid key
(with `<language>` standing for any registered language). Both twins' suites SHALL enforce these rules.

#### Scenario: Leaked token
- **WHEN** a SKILL.md mentions `basedpyright`
- **THEN** the skills test fails in both suites naming the skill and the token

#### Scenario: Unknown config key
- **WHEN** a SKILL.md says `la-config get lang.<language>.runner`
- **THEN** the skills test fails naming the key

### Requirement: la-doctor checks the tools' minor series against the calling plugin
`la-doctor --plugin DIR` SHALL resolve DIR against the working directory and read the nearest
`.claude-plugin/plugin.json` file at or above it, skipping a missing entry or one that is not a regular file. When
none exists it SHALL report `doctor.plugin-not-found`; when an entry on the way cannot be inspected (any other
stat or read error) it SHALL report `doctor.plugin-unreadable`. When the file is not valid UTF-8 JSON (no BOM, no
`NaN`/`Infinity`) whose top level is an object with a string `version` that is free of lone surrogates and consists
of ASCII digits, a dot, ASCII digits, a dot and at least one more character, it SHALL report
`doctor.plugin-invalid`.

Otherwise it SHALL compare the plugin version's major and minor with the installed tools' as integers (leading
zeros insignificant, any number of digits), ignoring whatever follows. Equal SHALL be healthy. Different SHALL
report `doctor.version-mismatch`, naming the installed version, the plugin's version, the plugin's
`<major>.<minor>` as written, and the invoking twin's own install command (its language's `install` template at
the plugin's version), so its cases are pinned to the invoking twin. `la-doctor` SHALL NOT accept `--expect`.
Every skill that uses an `la-*` or `dr-*` command SHALL run `la-doctor --plugin <this skill's base directory>` as
its preflight.

#### Scenario: Version read from the enclosing plugin
- **WHEN** `la-doctor --plugin <plugin>/skills/pr` runs and `<plugin>/.claude-plugin/plugin.json` declares the installed version
- **THEN** it reports healthy and exits 0

#### Scenario: Same series, other patch
- **WHEN** the plugin version has the installed major and minor and a different rest (`.999`, `.0-rc1`, or the same numbers with leading zeros)
- **THEN** it reports healthy and exits 0

#### Scenario: Different series
- **WHEN** the plugin version's major or minor differs from the installed tools', e.g. `0.0.0`
- **THEN** it prints `installed la tools are <installed>, but plugin 0.0.0 needs 0.0.x; reinstall them with: <install>` with `<install>` the invoking twin's install command at `0.0.0`, and exits 1

#### Scenario: Series compared beyond machine integers
- **WHEN** a component of the plugin version has more digits than a 64-bit float represents exactly
- **THEN** both twins compare it exactly and report the same result

#### Scenario: Version not of the form major.minor.rest
- **WHEN** the plugin version is `0.4`, `v0.4.1`, `0.4.`, uses a non-ASCII digit, or is `😀`
- **THEN** it prints `<path> is not valid JSON with a "version" of the form <major>.<minor>.<rest>` and exits 1

#### Scenario: No plugin manifest
- **WHEN** no `.claude-plugin/plugin.json` exists at or above DIR
- **THEN** it prints `no .claude-plugin/plugin.json at or above <DIR>` and exits 1

#### Scenario: Expect flag removed
- **WHEN** `la-doctor --expect 0.4.1` runs through either twin
- **THEN** it exits 2 as a usage error

### Requirement: A release that changes the tools raises the minor version
The tool inputs SHALL be every file under `shared/`, `conformance/`, `python/src/`, `node/src/` and
`node/scripts/`, `node/tsconfig*.json`, and `python/pyproject.toml`, `python/uv.lock`, `node/package.json` and
`node/package-lock.json` compared with the package's own version substituted. For a version V, the previous
release SHALL be the highest `vX.Y.Z` tag reachable from HEAD whose version is below V; tags of any other form
SHALL be ignored. When the tool inputs differ between the previous release and HEAD, V's major or minor SHALL be
greater than the previous release's.

`scripts/release-check <tag>` SHALL fail, naming the previous release and the changed inputs, when the tag's
version breaks this rule; it SHALL also fail when HEAD is not the tag's commit, when the repository is shallow, or
when no previous release is reachable. The Python test suite SHALL apply the rule to the repository's current
version whenever no tag for that version exists, skipping without reachable release tags except on GitHub Actions,
where it SHALL fail instead.

#### Scenario: Tool change released as a minor
- **WHEN** a file under `python/src/` changed since `v0.4.1` and `scripts/release-check v0.5.0` runs on the tagged commit
- **THEN** the rule passes

#### Scenario: Tool change released as a patch
- **WHEN** a file under `node/src/` or a dependency in `node/package.json` changed since `v0.4.1` and `scripts/release-check v0.4.2` runs on the tagged commit
- **THEN** it exits 1 naming `v0.4.1` and the changed inputs

#### Scenario: Unchanged tools released as a patch
- **WHEN** only `plugin/`, `docs/` and the package versions changed since `v0.4.1` and `scripts/release-check v0.4.2` runs on the tagged commit
- **THEN** the rule passes

#### Scenario: Previous release chosen numerically
- **WHEN** `v0.9.0` and `v0.10.0` are both reachable and the new version is `0.10.1`
- **THEN** the previous release is `v0.10.0`

#### Scenario: History incomplete
- **WHEN** `scripts/release-check` runs in a shallow clone, with no reachable release tag, or on a commit other than the tag's
- **THEN** it exits 1 naming the problem

#### Scenario: Bump PR checked before tagging
- **WHEN** the repository's version has no tag yet and the tool inputs changed since the previous release without a minor bump
- **THEN** the Python test suite fails

### Requirement: A duplicate key is reported naming the file, the key and both lines
Every command that reads `living-architecture.yaml`, `living-architecture.local.yaml` or `architecture/index.yaml`
SHALL fail on a duplicate key in it, through either twin, with a message naming the file and carrying the
`yaml.duplicate-key` wording, and SHALL never fall back to defaults or ignore the file:
- a config file SHALL be a config error naming the file, as for any other invalid YAML in it;
- `la-arch-check` SHALL report every YAML error in `architecture/index.yaml` as a setup error naming
  `architecture/index.yaml`, and exit 2;
- `la-arch-diagrams`, `la-arch-scaffold` and the `diagrams-fresh` check SHALL report a duplicate key in
  `index.yaml` with the `c4.index-duplicate-key` wording, and any other YAML error in it as before.

#### Scenario: Duplicate key in the config
- **WHEN** `living-architecture.yaml` sets `conventions:` on two lines and `la-config show` runs
- **THEN** it exits 1, printing a config error naming `living-architecture.yaml`, the key `'conventions'` and both lines

#### Scenario: Duplicate key in the local config
- **WHEN** `living-architecture.local.yaml` repeats a key and `la-config show` runs
- **THEN** it exits 1, printing a config error naming `living-architecture.local.yaml`, the key and both lines

#### Scenario: Duplicate key reported by la-doctor
- **WHEN** `living-architecture.yaml` repeats a key and `la-doctor` runs
- **THEN** its failure line names the file, the key and both lines, and it exits 1

#### Scenario: Duplicate key in the index under la-arch-check
- **WHEN** `architecture/index.yaml` sets `cross_cutting_specs:` on two lines and `la-arch-check` runs
- **THEN** it exits 2, printing `arch_check: architecture/index.yaml: ` followed by the duplicate-key message

#### Scenario: Other invalid YAML in the index under la-arch-check
- **WHEN** `architecture/index.yaml` is not valid YAML and `la-arch-check` runs
- **THEN** it exits 2, printing `arch_check: architecture/index.yaml: ` followed by the parser's wording

#### Scenario: Duplicate key in the index under la-arch-diagrams
- **WHEN** `architecture/index.yaml` repeats a key and `la-arch-diagrams` runs
- **THEN** it exits 1, printing `la-arch-diagrams: index.yaml is not valid YAML: ` followed by the duplicate-key
  message, and rewrites no doc

#### Scenario: Duplicate key in the index under la-arch-scaffold
- **WHEN** `architecture/index.yaml` repeats a key and `la-arch-scaffold` runs
- **THEN** it exits 2 with the duplicate-key message for `index.yaml` and writes nothing

### Requirement: A release that changes the released formats appends its own version
For a version V with a previous release (as in "A release that changes the tools raises the minor version"), the
previous release's formats SHALL be read from its `shared/config.yaml`: its released-formats list, else a list of its
single `format`, else an empty list when that release has no such file. A file that exists but declares neither in
the recognised one-line form, or a `git` failure other than the file's absence, SHALL be a problem naming the release.
HEAD's released formats SHALL equal the previous release's, or the previous release's followed by exactly V; any
other difference SHALL be a problem naming both lists and V. The reading of HEAD's list SHALL equal what the shared
YAML profile reads from the same file.

`scripts/release-check <tag>` SHALL fail on such a problem, and the Python test suite SHALL apply the same rule
whenever it applies the release rule to an untagged version.

#### Scenario: Formats unchanged
- **WHEN** HEAD's released formats equal those of `v0.6.0` and `scripts/release-check v0.7.0` runs on the tagged commit
- **THEN** the formats rule passes

#### Scenario: Own version appended
- **WHEN** `v0.6.0` released `[0.4.0]` and HEAD's released formats are `[0.4.0, 0.7.0]` for version `0.7.0`
- **THEN** the formats rule passes

#### Scenario: Wrong version appended
- **WHEN** `v0.6.0` released `[0.4.0]` and HEAD's released formats are `[0.4.0, 0.8.0]` for version `0.7.0`
- **THEN** `scripts/release-check v0.7.0` exits 1 naming both lists and `0.7.0`

#### Scenario: Several versions appended or an entry changed
- **WHEN** HEAD's released formats add two entries, or edit or drop an entry of the previous release's
- **THEN** `scripts/release-check` exits 1 naming both lists

#### Scenario: Previous release declares a single format
- **WHEN** the previous release's `shared/config.yaml` holds `format: 0.4.0` and no released-formats list
- **THEN** its formats are read as `[0.4.0]`

#### Scenario: Previous release has no config file
- **WHEN** the previous release has no `shared/config.yaml`
- **THEN** its formats are read as an empty list

#### Scenario: Unreadable previous formats fail closed
- **WHEN** the previous release's `shared/config.yaml` declares neither form recognisably, or `git` fails to read it for another reason
- **THEN** `scripts/release-check` exits 1 naming the previous release

#### Scenario: Bump PR checks the formats before tagging
- **WHEN** the repository's version has no tag yet and HEAD's released formats append a version other than it
- **THEN** the Python test suite fails
