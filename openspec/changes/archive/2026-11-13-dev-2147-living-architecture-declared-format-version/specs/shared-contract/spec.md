## ADDED Requirements

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
