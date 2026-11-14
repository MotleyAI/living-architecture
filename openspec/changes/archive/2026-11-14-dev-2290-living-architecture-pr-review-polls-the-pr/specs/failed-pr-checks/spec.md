## ADDED Requirements

### Requirement: --check keeps one check
`la-fetch-failed-pr-checks --check X` SHALL keep only the failed checks whose Details URL or name equals `X`
exactly, and SHALL make log attempts only for those. When none matches, its output SHALL be that of a PR with no
failed checks. A `--check` without a value SHALL be a usage error (exit 2).

#### Scenario: Match by Details URL among same-named checks
- **WHEN** two failed checks are both named `tests`, with Details URLs `https://github.com/o/r/actions/runs/1/job/2` and `https://github.com/o/r/actions/runs/3/job/4`, and the command runs with `--check https://github.com/o/r/actions/runs/3/job/4`
- **THEN** the output lists only the check with job 4, and no log attempt is made for job 2

#### Scenario: Match by name
- **WHEN** a failed StatusContext `ext-ci` has no Details URL and the command runs with `--check ext-ci`
- **THEN** the output lists exactly that check

#### Scenario: No match
- **WHEN** a check failed and the command runs with `--check other`
- **THEN** the Markdown says `_No failed checks._` and the JSON's `failed_checks` is empty

#### Scenario: Missing value
- **WHEN** the command runs as `la-fetch-failed-pr-checks 7 --check`
- **THEN** it exits 2
