## ADDED Requirements

### Requirement: Doctors keep la and trmv files out of a stealth repo
The shared contracts SHALL list each package's stealth path registry: la's is `living-architecture.yaml`,
`living-architecture.local.yaml`, `architecture/index.yaml` and every path under `openspec/` (only when the repo
tracks no path under `openspec/` at `HEAD`); trmv's is `trmv.yaml`, `living-architecture.yaml`, `.tsc-baseline.json`
and `.basedpyright/baseline.json`. In stealth mode, each doctor SHALL report, for each path of its package's
registry (`la-doctor` also trmv's), one finding naming the path when it is staged as an addition, or present,
untracked and not ignored by git, and exit 1. Git paths SHALL be read NUL-delimited. Outside stealth mode no such
check SHALL run.

#### Scenario: Untracked config in a stealth worktree
- **WHEN** a stealth repo has an untracked, unignored `trmv.yaml` in the working tree and `trmv-doctor` runs
- **THEN** it prints the finding naming `trmv.yaml` and exits 1

#### Scenario: Staged baseline
- **WHEN** a stealth repo has `.tsc-baseline.json` staged as an addition and `la-doctor` runs
- **THEN** it prints the finding naming `.tsc-baseline.json` and exits 1

#### Scenario: Ignored stray file
- **WHEN** a stealth repo has an untracked `.basedpyright/baseline.json` that `.git/info/exclude` ignores and `trmv-doctor` runs
- **THEN** it reports no registry finding

#### Scenario: Repo's own baseline
- **WHEN** a stealth repo tracks `.basedpyright/baseline.json` at `HEAD`, unchanged, and `trmv-doctor` runs
- **THEN** it reports no registry finding

#### Scenario: Untracked OpenSpec folder
- **WHEN** a stealth repo tracks nothing under `openspec/` and has an untracked `openspec/changes/x/proposal.md`, and `la-doctor` runs
- **THEN** it prints the finding naming `openspec/changes/x/proposal.md` and exits 1

#### Scenario: Not in stealth
- **WHEN** a repo with a committed `living-architecture.yaml` has an untracked `.tsc-baseline.json` and `la-doctor` runs
- **THEN** it reports no registry finding
