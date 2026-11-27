## ADDED Requirements

### Requirement: Stealth waivers come from a ledger
In stealth mode, `la-check-conventions` SHALL NOT treat a waiver comment as a waiver. It SHALL read the ledger
`<C>/living-architecture/waivers.yaml` with the shared YAML profile: a list of entries, each a mapping with exactly the
string keys `path`, `rule`, `line` and `reason`, as the shared contract's schema defines. `rule` SHALL be a waivable
rule. A violation SHALL be waived iff an entry's `path` equals its repo-relative POSIX path, its `rule` equals the
violation's rule, and its `line` equals the text of the violation's line with any trailing carriage return removed and
leading and trailing whitespace trimmed; an entry SHALL waive every violation it matches. A missing ledger SHALL mean
no waivers. A ledger that is not valid YAML or fails the schema SHALL exit 2 with a message naming the file. In stealth
mode the RED verdict SHALL name the ledger in place of the inline waiver example. Outside stealth mode the ledger
SHALL NOT be read.

#### Scenario: Ledger waives a flagged line
- **WHEN** a stealth repo's change adds `import os` inside a function in `src/a.py` and the ledger has `{path: src/a.py, rule: import-not-top, line: import os, reason: optional dependency}`
- **THEN** `la-check-conventions --base main` reports no violation for it and exits 0

#### Scenario: Inline waiver ignored in stealth
- **WHEN** the same late import carries `# ALLOW(import-not-top): optional dependency` and the ledger is empty
- **THEN** `la-check-conventions --base main` reports the violation and exits 1

#### Scenario: Indentation and line endings do not matter
- **WHEN** the flagged line is `        import os` with a CRLF ending and the entry's `line` is `import os`
- **THEN** the violation is waived

#### Scenario: Entry on another line text
- **WHEN** the entry's `line` is `import sys` and the flagged line is `import os`
- **THEN** the violation is reported

#### Scenario: Malformed ledger
- **WHEN** the ledger has an entry without `reason` and `la-check-conventions --base main` runs in stealth mode
- **THEN** it exits 2 with the message naming the ledger

#### Scenario: Unwaivable rule in the ledger
- **WHEN** a ledger entry names `text-ratio`
- **THEN** `la-check-conventions --base main` exits 2 with the message naming the ledger

#### Scenario: Verdict names the ledger
- **WHEN** a stealth run reports a waivable violation
- **THEN** the RED verdict names `<C>/living-architecture/waivers.yaml` and shows no inline waiver example

#### Scenario: Ledger ignored outside stealth
- **WHEN** a repo with a committed config has a ledger file in `<C>/living-architecture/` and an `ALLOW` comment on a flagged line
- **THEN** the comment waives the violation and the ledger is not read
