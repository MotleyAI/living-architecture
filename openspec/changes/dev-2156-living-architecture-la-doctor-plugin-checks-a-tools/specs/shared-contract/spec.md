## ADDED Requirements

### Requirement: la-doctor checks the tools fingerprint against the calling plugin
`la-doctor --plugin DIR` SHALL resolve DIR against the working directory and read the nearest
`.claude-plugin/plugin.json` file at or above it, skipping a missing entry or one that is not a regular file. When
none exists it SHALL report `doctor.plugin-not-found`; when an entry on the way cannot be inspected (any other
stat or read error) it SHALL report `doctor.plugin-unreadable`;
when the file is not valid UTF-8 JSON (no BOM, no `NaN`/`Infinity`) whose top level is an object with a string
`version` free of lone surrogates, it SHALL report `doctor.plugin-invalid`.

Otherwise it SHALL read the `TOOLS_FINGERPRINT` file beside that `plugin.json` and compare it with the tools
fingerprint the installed twin bundles; the two versions SHALL NOT be compared. A missing file (including a
dangling link) or a fingerprint different from the bundled one SHALL report `doctor.tools-mismatch`, naming the
installed tools' version, the plugin's version, and the invoking twin's own install command (its language's
`install` template at the plugin's version), so its cases are pinned to the invoking twin. A file that exists but
cannot be read SHALL report `doctor.plugin-unreadable` naming it. Content other than exactly 64 lowercase hex
digits optionally followed by one newline, compared byte-wise without trimming, SHALL report
`doctor.plugin-fingerprint-invalid`. An equal fingerprint SHALL be healthy. `la-doctor` SHALL NOT accept
`--expect`. Every skill that uses an `la-*` or `dr-*` command SHALL run
`la-doctor --plugin <this skill's base directory>` as its preflight.

#### Scenario: Fingerprint read from the enclosing plugin
- **WHEN** `la-doctor --plugin <plugin>/skills/pr` runs and `<plugin>/.claude-plugin/TOOLS_FINGERPRINT` holds the installed twin's fingerprint
- **THEN** it reports healthy and exits 0

#### Scenario: Versions differ but the tools are the same
- **WHEN** the nearest `plugin.json` declares `0.0.0` and the `TOOLS_FINGERPRINT` beside it holds the installed twin's fingerprint
- **THEN** it reports healthy and exits 0

#### Scenario: Tools differ
- **WHEN** the plugin's `TOOLS_FINGERPRINT` holds a well-formed fingerprint other than the installed twin's, with the plugin's version equal to or different from the installed one
- **THEN** it prints `installed la tools are <installed>, not the tools plugin <expected> was released with; reinstall them with: <install>` with `<install>` the invoking twin's install command at `<expected>`, and exits 1

#### Scenario: Plugin without a fingerprint
- **WHEN** the plugin has a valid `plugin.json` but no `TOOLS_FINGERPRINT` beside it
- **THEN** it prints the `doctor.tools-mismatch` problem and exits 1

#### Scenario: Malformed fingerprint
- **WHEN** the plugin's `TOOLS_FINGERPRINT` holds uppercase hex, 63 digits, a CRLF ending, a trailing space or two newlines
- **THEN** it prints the `doctor.plugin-fingerprint-invalid` problem naming the file and exits 1

#### Scenario: Unreadable fingerprint
- **WHEN** the plugin's `TOOLS_FINGERPRINT` is a directory
- **THEN** it prints the `doctor.plugin-unreadable` problem naming it and exits 1

#### Scenario: Invalid manifest is reported alone
- **WHEN** the nearest `plugin.json` is invalid and a valid `TOOLS_FINGERPRINT` sits beside it
- **THEN** it prints only the `doctor.plugin-invalid` problem among the plugin checks and exits 1

#### Scenario: No plugin manifest
- **WHEN** no `.claude-plugin/plugin.json` exists at or above DIR
- **THEN** it prints `no .claude-plugin/plugin.json at or above <DIR>` and exits 1

#### Scenario: Expect flag removed
- **WHEN** `la-doctor --expect 0.4.1` runs through either twin
- **THEN** it exits 2 as a usage error

### Requirement: Releases stamp and verify the tools fingerprint
The tools fingerprint SHALL be the sha256 over the git objects at HEAD of every file under `shared/`,
`conformance/`, `python/src/` and `node/src/` except the twins' own `TOOLS_FINGERPRINT` files, each contributing
its path, git mode and content, so it is independent of the checkout's line-ending, file-mode and symlink
settings. `plugin/.claude-plugin/TOOLS_FINGERPRINT`, `python/src/living_architecture/TOOLS_FINGERPRINT` and
`node/src/TOOLS_FINGERPRINT` SHALL hold the same well-formed fingerprint, and the built wheel and packed npm
package SHALL carry their twin's copy.

`scripts/release-bump <version>` SHALL set every package and plugin version (with lockfiles), every
`living-architecture` version pin in README.md and `docs/*.md`, and the fingerprint in all three files, and report
whether the tools changed since the previous fingerprint. It SHALL refuse, changing no file, when the version is
not `X.Y.Z` greater than the current one, a covered path has uncommitted changes or untracked non-ignored files,
the contract snapshots are stale, or a doc pin does not name the current version; a failure partway SHALL restore
every file it touched. `scripts/release-check` SHALL fail, naming each stale file, when any of the three does not
hold the checkout's fingerprint.

#### Scenario: Release without tool changes keeps the fingerprint
- **WHEN** `scripts/release-bump 0.4.2` runs on a clean tree whose covered files are unchanged since the 0.4.1 stamp
- **THEN** every version becomes 0.4.2, the three fingerprint files keep their value, and it reports that the tools are unchanged

#### Scenario: Release with tool changes restamps
- **WHEN** a file under `python/src/` was committed since the last stamp and `scripts/release-bump` runs
- **THEN** all three fingerprint files hold the new fingerprint and it reports that the tools changed

#### Scenario: Refusal changes nothing
- **WHEN** `scripts/release-bump` runs with `0.4.1-rc1`, a version not above the current one, a dirty covered file, stale snapshots or a stale doc pin
- **THEN** it exits 1 naming the problem and every file is byte-identical to before

#### Scenario: Failure partway restores every file
- **WHEN** a step of `scripts/release-bump` fails after earlier steps wrote files
- **THEN** it exits 1 and every file it touched is restored

#### Scenario: Fingerprint independent of checkout settings
- **WHEN** the fingerprint is computed in checkouts that differ in `core.autocrlf`, `core.filemode` or `core.symlinks`
- **THEN** it is the same

#### Scenario: Stale fingerprint blocks publishing
- **WHEN** a covered file changed after the last stamp and `scripts/release-check <tag>` runs
- **THEN** it exits 1 naming each stale fingerprint file

#### Scenario: Fingerprint copies drift
- **WHEN** the three `TOOLS_FINGERPRINT` files are not byte-identical or not well-formed
- **THEN** both twins' test suites fail

#### Scenario: Packaged twin carries the fingerprint
- **WHEN** the wheel or the packed npm package is installed outside the checkout and `la-doctor --plugin` runs against a plugin holding the source tree's fingerprint
- **THEN** it reports healthy

## REMOVED Requirements

### Requirement: la-doctor checks the tools against the calling plugin
**Reason**: It compared versions, so every release forced a tools reinstall, and `--expect` encoded the same rule.
**Migration**: Replaced by "la-doctor checks the tools fingerprint against the calling plugin": skills keep running
`la-doctor --plugin <this skill's base directory>`; a caller of `la-doctor --expect` drops the flag.
