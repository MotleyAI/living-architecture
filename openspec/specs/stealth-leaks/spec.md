# stealth-leaks Specification

## Purpose
In stealth mode, keeps the text that leaves the machine (the pushed branch name, commit messages, the code the branch
adds as of `HEAD`, PR text and review-thread replies) free of tokens that show la or trmv was used.

## Requirements

### Requirement: The leak tokens are one shared list in two groups
The la contract SHALL list the leak tokens in two groups. Core tokens, which nothing can allow: `living-architecture`,
`type-rename-move`, `trmv`, `/la:`, `/trmv:`, `ALLOW(`, every command name in either package's CLI contract, and every
path of either package's stealth path registry. Waivable tokens: `arc42`, `LikeC4`, `OpenSpec`, `reset point`,
`decisions log`, `pr-plan`, `pr-tests`, `pr-implement` and `pr-review`. A token SHALL match case-insensitively where no
word character touches it on either side. `OpenSpec` SHALL be dropped when the repo tracks a path under `openspec/` at
`HEAD`, and every token in the stealth config's `leaks.allow` SHALL be dropped.

#### Scenario: Case and punctuation
- **WHEN** a scanned line reads `Ran **LA-DOCTOR**, then the `trmv-typecheck` gate`
- **THEN** both `la-doctor` and `trmv-typecheck` are reported

#### Scenario: Token inside a word
- **WHEN** a scanned line reads `retrmvx` or `xarc42y`
- **THEN** no token is reported

#### Scenario: Path token
- **WHEN** an added line reads `cat living-architecture.yaml`
- **THEN** `living-architecture.yaml` and `living-architecture` are reported

#### Scenario: OpenSpec repo
- **WHEN** the repo tracks `openspec/specs/a/spec.md` at `HEAD` and a commit message mentions OpenSpec
- **THEN** no token is reported for it

#### Scenario: Allowed token
- **WHEN** the stealth config sets `leaks: {allow: [arc42]}` and an added line mentions arc42
- **THEN** no token is reported for it

### Requirement: la-leak-check scans a branch or a text
`la-leak-check` SHALL take exactly one of `--base BRANCH` and `--text -`; neither or both SHALL be a usage error
(exit 2). With `--base`, it SHALL resolve the base ref by the shared base resolution and scan, in this order: the
current branch's short name (none when `HEAD` is detached); the full message of each commit reachable from `HEAD` and
not from the merge base, merge commits included, oldest first; then, in Unicode code-point order of path, each path
added, or renamed to, between the merge base and `HEAD`, and each added line of that diff. With `--text -`, it SHALL
scan each line of stdin. It SHALL print one line per hit on stdout, in scan order, as `branch: <token>`,
`<short sha>: <token>`, `<path>: <token>`, `<path>:<line>: <token>` or `stdin:<line>: <token>`, with tokens in the
order they occur, and SHALL exit 1 when it printed a hit, 0 otherwise, and 2 on a usage, config or git error. Without a
stealth config file it SHALL print a note on stderr, nothing on stdout, and exit 0, whatever the root config holds.

#### Scenario: Leaking branch name
- **WHEN** the current branch is `egor/dev-1-living-architecture-stealth` and `la-leak-check --base main` runs in stealth mode
- **THEN** it prints `branch: living-architecture` and exits 1

#### Scenario: Leaking commit message
- **WHEN** a commit since the merge base says `Implement pr-plan decision 3` and `la-leak-check --base main` runs in stealth mode
- **THEN** it prints that commit's short sha with `pr-plan` and exits 1

#### Scenario: Leaking merge commit
- **WHEN** the branch has a merge commit whose message names `la-doctor`
- **THEN** that commit's hit is printed

#### Scenario: Leaking added line and path
- **WHEN** the change adds `.tsc-baseline.json` and a line `# ALLOW(import-not-top): x` at line 4 of `src/a.py`
- **THEN** it prints `.tsc-baseline.json: .tsc-baseline.json` and `src/a.py:4: ALLOW(`, and exits 1

#### Scenario: Removed lines are not scanned
- **WHEN** the change only deletes a line that mentions `arc42`
- **THEN** it prints nothing and exits 0

#### Scenario: Clean change
- **WHEN** the branch name, commit messages and added lines hold no token
- **THEN** it prints nothing and exits 0

#### Scenario: Text from stdin
- **WHEN** `la-leak-check --text -` reads a PR body whose second line says `Spec: OpenSpec change` in a repo without OpenSpec
- **THEN** it prints `stdin:2: OpenSpec` and exits 1

#### Scenario: Both modes
- **WHEN** `la-leak-check --base main --text -` runs
- **THEN** it exits 2 with a usage error

#### Scenario: Not in stealth
- **WHEN** a repo with a committed `living-architecture.yaml` runs `la-leak-check --base main`
- **THEN** it prints a note on stderr, nothing on stdout, and exits 0

#### Scenario: Same output from either twin
- **WHEN** `la-leak-check --base main` runs through each twin on the same stealth repo
- **THEN** both runs produce byte-identical stdout, stderr and exit codes

### Requirement: Reply commands refuse leaking bodies in stealth
In stealth mode, `la-reply-to-pr-thread` and `la-reply-invalid-coderabbit` SHALL scan the reply body exactly as
`la-leak-check --text -` does before any network call, and on a hit SHALL print the hits on stderr, post nothing and
exit 1. When a stealth config file is present but the config cannot be read, they SHALL print the error, post nothing
and exit 2. Outside stealth mode their behaviour SHALL be unchanged.

#### Scenario: Broken stealth config refuses the reply
- **WHEN** a stealth config and a root config are both present and `la-reply-to-pr-thread <url>` runs
- **THEN** it prints the config error on stderr, never calls `gh`, and exits 2

#### Scenario: Leaking reply refused
- **WHEN** `la-reply-to-pr-thread <url>` runs in stealth mode with a body naming `la-typecheck`
- **THEN** it prints the hit on stderr, never calls `gh`, and exits 1

#### Scenario: Clean reply posted
- **WHEN** `la-reply-invalid-coderabbit` runs in stealth mode with a body holding no token
- **THEN** it posts the reply as outside stealth mode

#### Scenario: Not in stealth
- **WHEN** `la-reply-to-pr-thread <url>` runs in a repo with a committed config with a body naming `la-doctor`
- **THEN** it posts the reply as before
