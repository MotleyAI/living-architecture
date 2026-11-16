## ADDED Requirements

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

#### Scenario: Index under a regular file under la-arch-diagrams
- **WHEN** `architecture` is a regular file and `la-arch-diagrams` runs
- **THEN** it exits 1 printing exactly `la-arch-diagrams: architecture/index.yaml: not a directory` in both twins

#### Scenario: Untraversable architecture directory under la-arch-diagrams
- **WHEN** `architecture/` cannot be searched for lack of permission and `la-arch-diagrams` runs
- **THEN** it exits 1 printing exactly `la-arch-diagrams: architecture/index.yaml: permission denied` in both twins

#### Scenario: Untraversable architecture directory under la-arch-migrate
- **WHEN** `architecture/` cannot be searched for lack of permission and `la-arch-migrate` runs
- **THEN** it exits 2 printing `la-arch-migrate: architecture/index.yaml: permission denied`, and every file, the
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
- **WHEN** `living-architecture.yaml` cannot be read for lack of permission and `dr-refactor` runs
- **THEN** it behaves exactly as it does for a config that is not valid YAML, in both twins, and never crashes

#### Scenario: TypeScript refactor with an unreadable index
- **WHEN** `architecture/index.yaml` cannot be read for lack of permission and a TypeScript refactor command runs
- **THEN** it exits 2 printing `architecture/index.yaml: permission denied` and writes nothing

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

#### Scenario: OS error text is the same in both twins
- **WHEN** `la-arch-check` cannot read `architecture/index.yaml`, or `la-arch-diagrams` cannot read a mapped arc42 doc, through either twin
- **THEN** both twins print byte-identical stderr and exit with the same code

## MODIFIED Requirements

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
- **THEN** it exits 2, printing exactly `arch_check: architecture/index.yaml: invalid YAML` in both twins

#### Scenario: Duplicate key in the index under la-arch-diagrams
- **WHEN** `architecture/index.yaml` repeats a key and `la-arch-diagrams` runs
- **THEN** it exits 1, printing `la-arch-diagrams: index.yaml is not valid YAML: ` followed by the duplicate-key
  message, and rewrites no doc

#### Scenario: Duplicate key in the index under la-arch-scaffold
- **WHEN** `architecture/index.yaml` repeats a key and `la-arch-scaffold` runs
- **THEN** it exits 2 with the duplicate-key message for `index.yaml` and writes nothing

## REMOVED Requirements

### Requirement: Observable outputs reproduce the conformance goldens
**Reason**: It excluded runtime-supplied error detail (OS errors, YAML library messages) from byte comparison and
pinned that each twin prints its runtime's own wording; OS and YAML errors now render from the shared registry.
**Migration**: Replaced by "Observable outputs reproduce the conformance goldens byte for byte", identical except
that only `--help` text and parser error wording stay excluded from byte comparison.
