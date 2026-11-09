## ADDED Requirements

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

## REMOVED Requirements

### Requirement: la-doctor checks the tools against the calling plugin
**Reason**: It compared exact versions, so every release forced a tools reinstall, and `--expect` encoded the same
rule.
**Migration**: Replaced by "la-doctor checks the tools' minor series against the calling plugin": skills keep
running `la-doctor --plugin <this skill's base directory>`; a caller of `la-doctor --expect` drops the flag.
