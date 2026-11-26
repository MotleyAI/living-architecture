## MODIFIED Requirements

### Requirement: User-facing texts come from the shared findings registry
Every finding line, gate verdict and hint that a command prints SHALL be rendered from a template in a
shared findings registry, identified by a stable id. Each package has its own registry in its own contract; an
id SHALL be defined in at most one of them, and la SHALL render an id from its own registry, else from trmv's.
A `{name}` placeholder SHALL insert the value as text.
A `{name!r}` placeholder SHALL insert the canonical repr defined by the contract. That repr covers only
normalized values (string, integer, float, boolean, null, list, mapping). It SHALL match Python's `repr`
for those values, including quote selection and escapes, and it is pinned by shared test vectors. Every
registry template SHALL be exercised by at least one conformance case of its package's corpus.

#### Scenario: Registry coverage
- **WHEN** the test suite runs
- **THEN** it fails if any template id in either findings registry is not produced by at least one conformance golden of that package's corpus

#### Scenario: Ids unique across the packages
- **WHEN** the test suite runs and an id is defined in both the trmv and the la registry
- **THEN** it fails naming the id

#### Scenario: Repr of a string containing a quote
- **WHEN** a `!r` placeholder receives the string `it's`
- **THEN** it renders as `"it's"`, matching the shared repr vector

#### Scenario: Repr of a non-scalar YAML value
- **WHEN** `index.yaml` sets `legacy_arrows.baseline: [1, 2]`
- **THEN** the `baseline-ratchet` finding renders the value as `[1, 2]`, byte-identical to the frozen golden

### Requirement: Command surfaces come from the shared CLI manifest
The set of `la-*` and `trmv-*` commands, and each command's subcommands, options, types, choices, repeatability,
required options, mutually exclusive options and positionals, SHALL be defined by the shared CLI manifests: trmv's
manifest defines `trmv-refactor`, `trmv-compliance`, `trmv-mock-lint`, `trmv-typecheck`, `trmv-doctor` and `trmv-config`, and
la's manifest every `la-*` command, `la-typecheck` included. Each installed command SHALL build its parser from its
package's manifest. Parsing SHALL accept no abbreviated long options and SHALL honour
`--`. A usage error SHALL exit 2; giving more than one option of an `exclusive` group is a usage error. A command
declared `passthrough` SHALL hand its raw arguments to its handler. Options the manifest marks internal SHALL be
accepted but omitted from help. The manifest SHALL declare, for each language-specific command, the languages whose
twin implements it natively; a command declaring none is neutral. The manifest SHALL mark the commands exempt from
the format check (`la-arch-migrate`, `la-doctor`, `trmv-doctor` and the review shims); every other command SHALL run
the format check, and a format refusal SHALL exit 2 in every command. Each package's installed entry points SHALL be
exactly its manifest's command set, and every command a skill references SHALL be in a manifest: a trmv skill only in
trmv's.

#### Scenario: Entry points match the manifest
- **WHEN** either twin's test suite runs for either package
- **THEN** it fails if that package's installed commands (console scripts or `bin` entries) differ from its manifest's commands in either direction

#### Scenario: dr skill names an la command
- **WHEN** a SKILL.md of the trmv plugin mentions an `la-*` command
- **THEN** the skills test fails naming the skill and the command

#### Scenario: Abbreviated option rejected
- **WHEN** `la-check-conventions --bas main` runs through either twin
- **THEN** it exits 2 as a usage error

#### Scenario: Accepted invocation vector
- **WHEN** `la-check-conventions --file a.py --file b.py --exclude 'gen/*'` runs
- **THEN** both files are checked, `gen/*` is exempt, and the exit code and stdout equal the golden

#### Scenario: Exclusive options rejected together
- **WHEN** `trmv-refactor rename --file a.py --line 1 --symbol foo --new-name bar` runs through either twin
- **THEN** it exits 2 as a usage error

#### Scenario: Internal option hidden
- **WHEN** `la-doctor --help` runs
- **THEN** the help text does not mention `--twin`, and `la-doctor --twin` is still accepted

#### Scenario: Skill references only real commands
- **WHEN** a SKILL.md mentions an `la-*` or `trmv-*` command absent from the manifest
- **THEN** the skills test fails naming the command

#### Scenario: Every non-exempt command runs the format check
- **WHEN** either twin's test suite runs each manifest command not marked exempt in a repo whose config declares no `format`
- **THEN** each exits 2 with the missing-format message, and no exempt command is refused by it (`la-doctor` reports
  the missing format as one of its problems instead)

### Requirement: Vendored contract snapshots match the shared source
The shared contract SHALL be split per package: `shared/trmv/` and `shared/la/`. Each twin of each package SHALL
load its own contract only from its own vendored snapshot of its package's directory, and la SHALL load trmv's
contract only through the trmv library it runs with. Each snapshot SHALL be byte-identical to its source directory,
with file modes preserved, and SHALL carry that directory's contract hash. `trmv-doctor --contract-hash` SHALL print
trmv's hash and `la-doctor --contract-hash` la's. Both twins of a package SHALL carry equal hashes; the trmv and la
hashes are independent.

#### Scenario: Stale snapshot detected
- **WHEN** a file under `shared/trmv/` or `shared/la/` changes and a twin's snapshot of that directory is not re-synced
- **THEN** that twin's test suite fails and names the sync command

#### Scenario: Built artifact carries the contract
- **WHEN** a package's wheel is built and installed into a clean environment outside the checkout (la's with trmv's)
- **THEN** every command loads its contract, a review shim runs its bundled script, and the package's doctor reports the same contract hash as the source tree

#### Scenario: Packed npm package carries the contract
- **WHEN** a package's `npm pack` output is installed into a clean prefix outside the checkout (la's with trmv's)
- **THEN** every command loads its contract, a review shim runs its bundled script, and the package's doctor `--contract-hash` prints the same hash as its PyPI twin

### Requirement: Configuration parameters are defined only by the shared schemas
Every key, type, constraint and default of `trmv.yaml` SHALL be defined only by trmv's shared JSON
Schema, and of `living-architecture.yaml` only by la's, which SHALL take each trmv key (`format`, `exempt`,
`commands.test`, `commands.typecheck`, `refactor`) by a reference to trmv's definition and stay closed to unknown
keys. The keys `living-architecture.local.yaml` may set SHALL be defined only by the shared local schema (which
references the main schema's definitions of those keys), and every config file name SHALL come only from the shared
contracts.
Filling defaults SHALL follow such references exactly as inline definitions. Every key and type of `architecture/index.yaml` SHALL be defined
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
- **WHEN** the config sets `exempt: []`, `conventions: {rules: []}` and `reviewers: {codex: false}`
- **THEN** the resolved configuration keeps the empty lists and `false` rather than substituting defaults

#### Scenario: Referenced dr keys are filled
- **WHEN** `living-architecture.yaml` sets only `commands: {test: pytest}` and `la-config show` runs
- **THEN** `exempt` is `[]`, `commands.lint` is null and `commands.typecheck` carries both language defaults, byte-identical in both twins

#### Scenario: Explicit null kept through a reference
- **WHEN** the config sets `commands: {typecheck: {python: null}}`
- **THEN** the resolved `commands.typecheck.python` is null and `commands.typecheck.typescript` carries its default

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

### Requirement: Doctor checks each repo language's executables
`trmv-doctor` and `la-doctor` SHALL each report a missing executable for `node` and for `npx` when TypeScript is a
repo language. Outside a git repository they SHALL skip the language-dependent checks. A repo without TypeScript
SHALL get today's output.

#### Scenario: TypeScript repo without node
- **WHEN** `la-doctor` runs in a TypeScript repo with no `node` on PATH
- **THEN** it reports `node` missing and exits 1

#### Scenario: Python repo unchanged
- **WHEN** `la-doctor` runs in a Python-only repo with no `node` on PATH
- **THEN** its output equals today's golden

### Requirement: Skills are language-neutral
A SKILL.md of either plugin SHALL contain no language-only token from the shared skill-leak list; language idioms
SHALL live only in `plugin/trmv/languages/<language>.md`. Every `la-config get <key>` or `trmv-config get <key>` a
SKILL.md names SHALL be a valid key of that command (with `<language>` standing for any registered language), and a
trmv skill SHALL name only `trmv-config`. Both twins' suites SHALL enforce these rules.

#### Scenario: Leaked token
- **WHEN** a SKILL.md mentions `basedpyright`
- **THEN** the skills test fails in both suites naming the skill and the token

#### Scenario: Unknown config key
- **WHEN** a SKILL.md says `la-config get lang.<language>.runner`
- **THEN** the skills test fails naming the key

### Requirement: la-doctor checks the tools' minor series against the calling plugin
`la-doctor --plugin DIR` and `trmv-doctor --plugin DIR` SHALL each resolve DIR against the working directory and read the nearest
`.claude-plugin/plugin.json` file at or above it, skipping a missing entry or one that is not a regular file. When
none exists it SHALL report `doctor.plugin-not-found`; when an entry on the way cannot be inspected (any other
stat or read error) it SHALL report `doctor.plugin-unreadable`. When the file is not valid UTF-8 JSON (no BOM, no
`NaN`/`Infinity`) whose top level is an object with a string `version` that is free of lone surrogates and consists
of ASCII digits, a dot, ASCII digits, a dot and at least one more character, it SHALL report
`doctor.plugin-invalid`.

Otherwise it SHALL compare the plugin version's major and minor with the installed tools' as integers (leading
zeros insignificant, any number of digits), ignoring whatever follows. Equal SHALL be healthy. Different SHALL
report `doctor.version-mismatch`, naming the doctor's package (`la` or `trmv`), the installed version, the plugin's
version, the plugin's `<major>.<minor>` as written, and the invoking twin's own install command for that package
(its language's `install` template at the plugin's version), so its cases are pinned to the invoking twin. Neither
doctor SHALL accept `--expect`. Every skill of the la plugin that uses an `la-*` or `trmv-*` command SHALL run
`la-doctor --plugin <this skill's base directory>` as its preflight, and every skill of the trmv plugin that uses a
`trmv-*` command SHALL run `trmv-doctor --plugin <this skill's base directory>`.

#### Scenario: Version read from the enclosing plugin
- **WHEN** `la-doctor --plugin <plugin>/skills/pr` runs and `<plugin>/.claude-plugin/plugin.json` declares the installed version
- **THEN** it reports healthy and exits 0

#### Scenario: Same series, other patch
- **WHEN** the plugin version has the installed major and minor and a different rest (`.999`, `.0-rc1`, or the same numbers with leading zeros)
- **THEN** it reports healthy and exits 0

#### Scenario: Different series
- **WHEN** the plugin version's major or minor differs from the installed tools', e.g. `0.0.0`
- **THEN** it prints `installed la tools are <installed>, but plugin 0.0.0 needs 0.0.x; reinstall them with: <install>` with `<install>` the invoking twin's install command at `0.0.0`, and exits 1

#### Scenario: Different series under dr-doctor
- **WHEN** `trmv-doctor --plugin DIR` runs and the trmv plugin's version is `0.0.0`
- **THEN** it prints `installed trmv tools are <installed>, but plugin 0.0.0 needs 0.0.x; reinstall them with: <install>` with `<install>` the trmv install command at `0.0.0`, and exits 1

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
The tool inputs SHALL be every file under `shared/`, `conformance/`, each package's `src/` under `python/` and
`node/`, `node/scripts/` and each npm package's `scripts/`, every `tsconfig*.json` under `node/`, and every
`pyproject.toml`, `package.json` and lockfile under `python/` and `node/`, compared with the packages' own version,
la's pin on trmv and la's plugin dependency on trmv substituted. Both packages and both plugins SHALL share one version,
so the rule applies to it once. For a version V, the previous
release SHALL be the highest `vX.Y.Z` tag reachable from HEAD whose version is below V; tags of any other form
SHALL be ignored. When the tool inputs differ between the previous release and HEAD, V's major or minor SHALL be
greater than the previous release's.

`scripts/release-check <tag>` SHALL fail, naming the previous release and the changed inputs, when the tag's
version breaks this rule; it SHALL also fail when HEAD is not the tag's commit, when the repository is shallow, or
when no previous release is reachable. The Python test suite SHALL apply the rule to the repository's current
version whenever no tag for that version exists, skipping without reachable release tags except on GitHub Actions,
where it SHALL fail instead.

#### Scenario: Tool change released as a minor
- **WHEN** a file under `python/trmv/src/` changed since `v0.4.1` and `scripts/release-check v0.5.0` runs on the tagged commit
- **THEN** the rule passes

#### Scenario: Tool change released as a patch
- **WHEN** a file under `node/trmv/src/` or a dependency in `node/trmv/package.json` changed since `v0.4.1` and `scripts/release-check v0.4.2` runs on the tagged commit
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

#### Scenario: Versions out of lockstep
- **WHEN** the trmv and la package versions, their `plugin.json` versions, la's pin on trmv or la's plugin dependency on trmv disagree on the major and minor
- **THEN** `scripts/release-check` and the Python test suite fail naming the disagreeing files

#### Scenario: Snapshot hashes checked per package
- **WHEN** `python/trmv`'s and `node/trmv`'s snapshot hashes equal `shared/trmv`'s and the la snapshots' equal `shared/la`'s
- **THEN** the hash check passes although the trmv and la hashes differ, and it fails naming the snapshot when any one of the four is stale

### Requirement: A release that changes the released formats appends its own version
For a version V with a previous release (as in "A release that changes the tools raises the minor version"), the
previous release's formats of each config file SHALL be read from its trmv contract's `shared/trmv/config.yaml` per-file
series when that file exists; otherwise from its `shared/config.yaml`, whose released-formats list, else a list of
its single `format`, else an empty list when that release has no such file, are the formats of
`living-architecture.yaml`, and `trmv.yaml` then has an empty list. A file that exists but declares
none of these in the recognised form, or a `git` failure other than the file's absence, SHALL be a problem naming
the release. For each config file, HEAD's released formats SHALL equal the previous release's, or the previous
release's followed by exactly V; any other difference SHALL be a problem naming the file, both lists and V. The
reading of HEAD's lists SHALL equal what the shared YAML profile reads from the same file.

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

#### Scenario: Split release read against the single-file layout
- **WHEN** `v0.13.0` has `shared/config.yaml` with `formats: [0.4.0]` and HEAD's `shared/trmv/config.yaml` gives `living-architecture.yaml` `[0.4.0, 0.14.0]` and `trmv.yaml` `[0.14.0]` for version `0.14.0`
- **THEN** the formats rule passes

### Requirement: OS and YAML errors render from the shared registry
Every OS error a command reports SHALL render, in both twins, from the `os.*` templates of the shared findings
registry: `os.error` (`{path}: {reason}`), or the reason alone where the surrounding finding already names the file.
The reason SHALL be chosen by the error's symbolic code: `ENOENT` gives `os.not-found`, `EACCES`
`os.permission-denied`, `EISDIR` `os.is-a-directory`, `ENOTDIR` `os.not-a-directory`, and any other code
`os.other` carrying the symbolic name (`unknown` when the error has none). The path SHALL be the file the command was
reading, written relative to the repo root with `/` separators when it lies lexically under the root, else absolute.
No runtime error message and no errno number SHALL reach output.

Any YAML error other than a duplicate key, in any file the tools read with the shared YAML profile, and any such file
that is not valid UTF-8, SHALL render as invalid YAML from the registry, without the parser's wording. A duplicate key
keeps the `yaml.duplicate-key` wording.

For `living-architecture.yaml`, `living-architecture.local.yaml` and `architecture/index.yaml`, only a path that does
not exist SHALL count as absent (a path that exists but is not a regular file stays absent, as before). Any other
error while checking or reading the file SHALL be reported from the templates, never treated as absence and never a
crash:
- a config file SHALL be a config error, as for invalid YAML in it, through every command that loads the config;
- `la-arch-check` SHALL report it as a setup error and exit 2;
- `la-arch-diagrams`, `la-arch-migrate`, `la-arch-scaffold`, the TypeScript refactor commands and `la-doctor` SHALL
  report it as they report an unusable `index.yaml`, changing nothing.

The conventions gate's `[unreadable]` finding SHALL carry the reason alone, and `conventions.not-utf8` for a file
that is not valid UTF-8, in both twins.

#### Scenario: Index missing under la-arch-check
- **WHEN** `architecture/index.yaml` does not exist and `la-arch-check` runs, through either twin
- **THEN** it exits 2 printing exactly `arch_check: architecture/index.yaml: no such file or directory`

#### Scenario: Index permission denied under la-arch-check
- **WHEN** `architecture/index.yaml` cannot be read for lack of permission and `la-arch-check` runs
- **THEN** it exits 2 printing exactly `arch_check: architecture/index.yaml: permission denied` in both twins

#### Scenario: Index is a directory under la-arch-check
- **WHEN** `architecture/index.yaml` is a directory and `la-arch-check` runs
- **THEN** it exits 2 printing exactly `arch_check: architecture/index.yaml: is a directory` in both twins

#### Scenario: Index under a regular file under la-arch-check
- **WHEN** `architecture` is a regular file and `la-arch-check` runs
- **THEN** it exits 2 printing exactly `arch_check: architecture/index.yaml: not a directory` in both twins

#### Scenario: Other OS error carries the symbolic code
- **WHEN** `architecture/index.yaml` is a symlink to itself and `la-arch-check` runs
- **THEN** it exits 2 printing exactly `arch_check: architecture/index.yaml: OS error ELOOP` in both twins

#### Scenario: Doc missing under la-arch-diagrams
- **WHEN** `index.yaml` maps `architecture/gone.arc42.md`, which does not exist, and `la-arch-diagrams` runs
- **THEN** it exits 1 printing exactly `la-arch-diagrams: architecture/gone.arc42.md: no such file or directory`

#### Scenario: Doc permission denied under la-arch-diagrams
- **WHEN** a mapped arc42 doc cannot be read for lack of permission and `la-arch-diagrams` runs
- **THEN** it exits 1 printing exactly `la-arch-diagrams: ` followed by the doc's repo-relative path and
  `: permission denied`, in both twins, and rewrites no doc

#### Scenario: Doc is a directory under la-arch-diagrams
- **WHEN** a mapped arc42 doc is a directory and `la-arch-diagrams` runs
- **THEN** it exits 1 printing exactly `la-arch-diagrams: ` followed by the doc's repo-relative path and
  `: is a directory`, in both twins

#### Scenario: Doc under a regular file under la-arch-diagrams
- **WHEN** a mapped arc42 doc's path runs through a regular file and `la-arch-diagrams` runs
- **THEN** it exits 1 printing exactly `la-arch-diagrams: ` followed by the doc's repo-relative path and
  `: not a directory`, in both twins

#### Scenario: Untraversable architecture directory under la-arch-diagrams
- **WHEN** `architecture/` cannot be searched for lack of permission and `la-arch-diagrams` runs
- **THEN** it exits 1 printing exactly `la-arch-diagrams: architecture: permission denied` in both twins

#### Scenario: Untraversable architecture directory under la-arch-migrate
- **WHEN** `architecture/` cannot be searched for lack of permission and `la-arch-migrate` runs
- **THEN** it exits 2 printing `la-arch-migrate: architecture: permission denied`, and every file, the
  config's `format` included, is byte-identical to before

#### Scenario: Unreadable config
- **WHEN** `living-architecture.yaml` cannot be read for lack of permission and `la-config show` runs
- **THEN** it exits 1 printing exactly `la-config: living-architecture.yaml: permission denied` in both twins

#### Scenario: Config not valid UTF-8
- **WHEN** `living-architecture.yaml` is not valid UTF-8 and `la-config show` runs
- **THEN** it exits 1 printing exactly `la-config: living-architecture.yaml: invalid YAML` in both twins

#### Scenario: Config not valid YAML
- **WHEN** `living-architecture.yaml` is not valid YAML (a refused tag or an impossible date included) and
  `la-config show` runs
- **THEN** it exits 1 printing exactly `la-config: living-architecture.yaml: invalid YAML` in both twins

#### Scenario: dr-refactor with an unreadable config
- **WHEN** `living-architecture.yaml` cannot be read for lack of permission and `trmv-refactor` runs
- **THEN** it behaves exactly as it does for a config that is not valid YAML, in both twins, and never crashes

#### Scenario: TypeScript refactor with an unreadable index
- **WHEN** `architecture/index.yaml` cannot be read for lack of permission and `trmv-refactor` runs on TypeScript source
- **THEN** it exits 1 printing `architecture/index.yaml: permission denied` and writes nothing, as for an index that
  is not valid YAML

#### Scenario: Unreadable file in the conventions gate
- **WHEN** a changed source file is a directory and `la-check-conventions` runs, for Python and for TypeScript
- **THEN** the finding reads `<path>:1: [unreadable] is a directory`

#### Scenario: Non-UTF-8 file in the conventions gate
- **WHEN** a changed Python source file is not valid UTF-8 and `la-check-conventions` runs
- **THEN** the finding reads `<path>:1: [unreadable] not valid UTF-8`, as for TypeScript

#### Scenario: No errno number reaches output
- **WHEN** any conformance case pins an OS error
- **THEN** its golden contains no `[Errno` text and no numeric error code

### Requirement: Observable outputs reproduce the conformance goldens byte for byte
The conformance corpus SHALL be split per package, `conformance/trmv/` and `conformance/la/`, each with its own cases
and inventory; a case's tree SHALL decide its package (its manifest, format series, version, contract hash and entry
points), and a case SHALL invoke only its own package's commands. One runner SHALL run both trees, with the commands
of both packages but none of the host's runners on `PATH`. Fixtures SHALL be shared by both trees.
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
`--help` text and parser error wording SHALL be excluded from byte comparison.

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

#### Scenario: Case invoking another package's command
- **WHEN** a case under `conformance/trmv/` invokes an `la-*` command, or a case under `conformance/la/` a `trmv-*` command
- **THEN** the corpus self-test fails naming the case

#### Scenario: OS error text is the same in both twins
- **WHEN** `la-arch-check` cannot read `architecture/index.yaml`, or `la-arch-diagrams` cannot read a mapped arc42 doc, through either twin
- **THEN** both twins print byte-identical stderr and exit with the same code

## ADDED Requirements

### Requirement: release-check verifies the trmv plugin tag
la's plugin dependency on trmv resolves against the plugin tag `trmv--v<version>`. `scripts/release-check <tag>`
SHALL fail, naming the plugin tag, unless that tag exists for the tag's version and points at the same commit as
`<tag>`.

#### Scenario: Plugin tag at the release commit
- **WHEN** `trmv--v0.14.0` and `v0.14.0` point at the same commit and `scripts/release-check v0.14.0` runs on it
- **THEN** the plugin tag check passes

#### Scenario: Plugin tag missing
- **WHEN** no `trmv--v0.14.0` tag exists and `scripts/release-check v0.14.0` runs on the tagged commit
- **THEN** it exits 1 naming `trmv--v0.14.0`

#### Scenario: Plugin tag at another commit
- **WHEN** `trmv--v0.14.0` points at a commit other than `v0.14.0`'s and `scripts/release-check v0.14.0` runs on the tagged commit
- **THEN** it exits 1 naming `trmv--v0.14.0` and both commits
