## MODIFIED Requirements

### Requirement: la-arch-migrate converts the repo to the current format
`la-arch-migrate [--root DIR]` SHALL read the committed `living-architecture.yaml` as YAML only (its schema is not
checked) and:
- without a committed `living-architecture.yaml`, exit 2 with a message naming `/la:init`, writing nothing;
- when the file cannot be read, is not valid YAML or is not a mapping, exit 2, writing nothing;
- when `format` is invalid or newer than the current format, exit 2 with the format check's message, writing
  nothing;
- when `format` equals the current format, print that there is nothing to migrate, naming the format, change
  nothing and exit 0;
- when `format` is older than the current format and is not one of the released formats (the shared contract's
  list; see "Every command checks the declared format"), exit 2 naming the declared format as one no `la` release
  used, and the current format, writing nothing;
- when `format` is absent or is an older released format, convert the repo step by step, then stamp the current
  format.

There SHALL be one unversioned step, converting a repo that declares no format to the first released format: the
layout conversion (see "la-arch-migrate converts the legacy layout"), then the arc42 conversion (see "la-arch-migrate
converts the retired arc42 key format"). Every released format other than the current one SHALL have exactly one
step, converting to the next released format, and no step SHALL exist for any other source. A run SHALL apply every
step from the declared format (the unversioned step when there is none) up to the current format, in order, each
planned and verified against the repo as the earlier steps left it. No step SHALL write `living-architecture.yaml`.

Stamping SHALL be decided before any step writes. When `format` is absent, stamping SHALL insert one
`format: <current>` line, keeping every other byte of the file: after the leading comment lines, blank lines, `%`
directive lines and a `---` document marker, before the first other line, or at the end of a file that has no other
line (adding a missing final line break first); the inserted line SHALL use the file's line break (CRLF when the
file's first line break is CRLF, else LF). When `format` is present, stamping SHALL replace its value on the one line
that starts with the unquoted key `format` directly followed by a colon, when that colon is followed by spaces or
tabs, one single-line plain, single-quoted or double-quoted scalar and optionally whitespace and a comment: the
scalar, quotes included, becomes the bare current format and every other byte is kept. Any other form (no or several
such lines, a value on a later line, a block scalar, a quoted or spaced key) SHALL NOT be stamped. Before writing,
the stamped text SHALL be verified to parse to the original mapping with `format` set to the current format;
otherwise `la-arch-migrate` SHALL exit 2 with a message saying the format must be set by hand, writing nothing.

The run SHALL be all-or-nothing across every step's layout files, `architecture/index.yaml`, moved docs, deleted
files and directories, and the config: the config SHALL be replaced atomically as the last change. When a step
refuses, fails verification or hits a filesystem error, or replacing the config fails, after any change was made,
every created file SHALL be removed, every moved file moved back, and every deleted or replaced file and every
removed directory restored byte-for-byte with its mode, and the command SHALL exit 2 with that failure's message.
When restoring fails, the message SHALL name every path left changed.

On success it SHALL print the run's net effect, one path per line, each path at most once, and exit 0:
- first `wrote <path>` for each path the run wrote that exists at the end, in the order first written, with
  `living-architecture.yaml` last;
- then `moved <source> to <target>` for each moved file whose final path exists at the end, consecutive moves of one
  file composed into one move from its path before the run to its final path, in the order first moved; a file moved
  back to where it started is not reported as moved; a moved file whose contents a later step changed is also
  reported as written at its final path;
- then `deleted <path>` for each file or directory that existed before the run, does not exist at the end and is not
  the source of a reported move, in the order deleted;
- a path the run created and then removed is not reported.

For an unversioned repo this prints `architecture/model.c4`, `architecture/views.c4` and `architecture/index.yaml`
as written (each only when written), then `living-architecture.yaml`, then each moved doc, then each deleted path.

#### Scenario: No config file
- **WHEN** a repo has no committed `living-architecture.yaml` and `la-arch-migrate` runs
- **THEN** it exits 2 with a message naming `/la:init` and the repo is unchanged

#### Scenario: Already current
- **WHEN** the config declares the current format and `la-arch-migrate` runs
- **THEN** it prints that there is nothing to migrate, naming the current format, changes nothing and exits 0

#### Scenario: Newer format refused
- **WHEN** the config declares `format: 9.0.0` and `la-arch-migrate` runs
- **THEN** it exits 2 with the message naming `9.0.0` as the `la` version to upgrade to and the repo is unchanged

#### Scenario: Invalid format refused
- **WHEN** the config declares `format: 0.4` and `la-arch-migrate` runs
- **THEN** it exits 2 with the invalid-format message and the repo is unchanged

#### Scenario: Unknown older format refused
- **WHEN** the config declares `format: 0.3.0`, which is older than the current format and not a released format, and `la-arch-migrate` runs
- **THEN** it exits 2 naming `0.3.0` as a format no `la` release used, and the current format, and the repo is unchanged

#### Scenario: Unreleased format between released ones refused
- **WHEN** the released formats are `F1 < F3` and the config declares `F2` with `F1 < F2 < F3`
- **THEN** `la-arch-migrate` exits 2 naming `F2` and the repo is unchanged

#### Scenario: Released older format converts from its own step
- **WHEN** the released formats are `F1 < F2 < F3` and the config declares `F2`
- **THEN** `la-arch-migrate` applies only the step from `F2`, stamps `F3` and exits 0

#### Scenario: Unversioned repo applies every step
- **WHEN** the released formats are `F1 < F2` and the config declares no format
- **THEN** `la-arch-migrate` applies the unversioned step, then the step from `F1`, stamps `F2` and exits 0

#### Scenario: Every older released format has a step to the next one
- **WHEN** either twin's test suite inspects its steps against the released formats
- **THEN** there is exactly the unversioned step, targeting the first released format, and one step per released format other than the current, each targeting the next released format

#### Scenario: Malformed config refused
- **WHEN** the committed config is not valid YAML, or its top level is a scalar or a list, and `la-arch-migrate` runs
- **THEN** it exits 2 and every file is byte-identical to before

#### Scenario: Schema errors do not block stamping
- **WHEN** an unversioned config also sets a removed key such as `reviewers: {coderabbit: true}` and `la-arch-migrate` runs
- **THEN** it stamps the format, keeps the removed key and exits 0

#### Scenario: Stamp after leading comments
- **WHEN** an unversioned config opens with two comment lines and a blank line before `tracker: linear`
- **THEN** the stamped file holds those lines unchanged, then `format: <current>`, then `tracker: linear` and every following byte unchanged

#### Scenario: Stamp after a document marker
- **WHEN** an unversioned config opens with `%YAML 1.1` and `---` before its keys
- **THEN** `format: <current>` is inserted directly after the `---` line

#### Scenario: Stamp keeps CRLF line breaks
- **WHEN** an unversioned config uses CRLF line breaks
- **THEN** the inserted line ends with CRLF and every other byte is unchanged

#### Scenario: Stamp into an empty or comment-only file
- **WHEN** the unversioned config is empty, or holds only comments without a final line break
- **THEN** `format: <current>` is the file's last line and the prior content is unchanged apart from an added final line break

#### Scenario: Stamp replaces an existing value
- **WHEN** the config holds `format: '0.3.0'  # repo format` after another key
- **THEN** the stamped line is `format: <current>  # repo format` and every other byte is unchanged

#### Scenario: Unstampable config
- **WHEN** the unversioned config is a flow-style mapping `{tracker: linear}`
- **THEN** `la-arch-migrate` exits 2 saying the format must be set by hand and the repo is unchanged

#### Scenario: Unstampable existing value
- **WHEN** the config's `format` value sits on the line after the key, or the key is written `format :` or `'format':`
- **THEN** the stamp is refused and the config is unchanged

#### Scenario: Stamped repo passes the format check
- **WHEN** an unversioned repo is migrated and then `la-config show` runs
- **THEN** it exits 0 and prints the current format

#### Scenario: Write failure rolls back the config too
- **WHEN** writing, deleting or replacing the config fails part-way through `la-arch-migrate`
- **THEN** it exits 2 and every legacy file, the `architecture/model/` directory, any pre-existing `model.c4` and `views.c4`, `architecture/index.yaml`, every arc42 doc and `living-architecture.yaml` are byte-identical at their original locations

#### Scenario: A later step's failure rolls back the earlier steps
- **WHEN** a run applies two steps and the second refuses, fails verification or hits a filesystem error after the first created, moved, deleted and replaced files and removed a directory
- **THEN** `la-arch-migrate` exits 2 with the second step's failure message, and every path is back with its bytes and mode, and every directory exists again

#### Scenario: Failed rollback named
- **WHEN** a write fails and restoring one of the changed paths also fails
- **THEN** `la-arch-migrate` exits 2 and its message names that path as left changed

#### Scenario: One move reported once
- **WHEN** a run moves `a` to `b` and nothing else touches either
- **THEN** it prints `moved a to b` and neither `wrote b` nor `deleted a`

#### Scenario: Consecutive moves composed
- **WHEN** one step moves `a` to `b` and a later step moves `b` to `c`
- **THEN** it prints `moved a to c` and nothing about `b`

#### Scenario: Move back not reported
- **WHEN** one step moves `a` to `b` and a later step moves `b` back to `a`
- **THEN** it prints nothing about `a` or `b`

#### Scenario: Moved then deleted
- **WHEN** one step moves the pre-existing `a` to `b` and a later step deletes `b`
- **THEN** it prints `deleted a` and nothing about `b`

#### Scenario: Created then deleted not reported
- **WHEN** one step creates `x` and a later step deletes it
- **THEN** it prints nothing about `x`

#### Scenario: Written then deleted reported as deleted
- **WHEN** one step rewrites the pre-existing `x` and a later step deletes it
- **THEN** it prints `deleted x` and not `wrote x`
