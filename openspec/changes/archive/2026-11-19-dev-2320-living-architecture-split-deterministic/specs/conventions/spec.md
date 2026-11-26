## MODIFIED Requirements

### Requirement: Files are routed to a language by extension
Each file's language SHALL be the shared languages-registry entry whose source extensions contain the file's
extension. A diff-derived file list SHALL include every changed file with a known extension, after the globs of the
top-level `exempt` key and of `--exclude`, and SHALL silently ignore other files. An explicitly given path
(`--file`, `la-count-comments` arguments) whose extension is unknown SHALL be skipped with one stderr warning naming
it, and SHALL NOT affect the exit code. Changed files SHALL be listed with NUL-delimited git output, so that paths
containing spaces, non-ASCII characters or a leading dash are checked under their real names; deleted files SHALL
be excluded and a renamed file SHALL be checked under its new path.

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

#### Scenario: Exempt paths come from the top-level key
- **WHEN** the config sets `exempt: ['gen/*']` and the diff changes `gen/a.py` and `src/b.py`
- **THEN** only `src/b.py` is checked
