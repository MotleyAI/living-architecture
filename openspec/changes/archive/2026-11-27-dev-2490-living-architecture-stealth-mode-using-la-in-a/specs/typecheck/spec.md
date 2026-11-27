## MODIFIED Requirements

### Requirement: Baseline contract
In every language, `trmv-typecheck` SHALL exit 0 when no error lies outside the baseline, 1 when new errors exist
(listing them), and 2 on a usage, configuration or checker failure. The baseline SHALL shrink only on a run
without new errors. Besides shrinking, a check SHALL change a baseline only by realignment under `--realign-from`,
which changes path keys and positions and never the number of entries. `--write-baseline` SHALL write a baseline
for each applicable language that has none (an empty one for a clean language), SHALL skip with a notice each
language whose baseline file exists, and SHALL exit 0 when it wrote at least one baseline and 2 when every
applicable language already had one. In stealth mode `--write-baseline` SHALL instead exit 2 with a stealth refusal
naming the option, before any checker runs, and write nothing.

#### Scenario: New error and resolved error together
- **WHEN** a run fixes one baselined error and introduces a new one
- **THEN** it exits 1 and the baseline is unchanged

#### Scenario: Write refused when every baseline exists
- **WHEN** `trmv-typecheck --write-baseline` runs and every applicable language already has its baseline file
- **THEN** it exits 2 and no baseline changes

#### Scenario: Write for a newly added language
- **WHEN** a repo with a Python baseline adds TypeScript and runs `trmv-typecheck --write-baseline`
- **THEN** the TypeScript baseline is written, Python is skipped with a notice, and the exit code is 0

#### Scenario: Write refused in stealth
- **WHEN** `trmv-typecheck --write-baseline` runs in stealth mode
- **THEN** it exits 2 with the stealth refusal, no checker runs, and no file is written

## ADDED Requirements

### Requirement: Stealth baseline from the merge-base
In stealth mode, for each applicable language whose baseline file the repo does not track at `HEAD`, `trmv-typecheck`
SHALL use as that language's baseline the checker's errors at the merge base of the base ref and `HEAD`, in that
language's baseline format, and SHALL compare and report exactly as against a committed baseline that matched at the
merge base, realigned to the working tree (Python by the realignment rules of `--realign-from`; TypeScript keys are
independent of position). It SHALL never write or shrink a baseline file in the working tree. The base ref SHALL be
`--base BRANCH`, resolved by the shared base resolution (see the affected-tests capability), else the target of
`refs/remotes/origin/HEAD`; when neither resolves it SHALL exit 2 with a message naming `--base`.

The checker SHALL run at the merge base in a temporary linked worktree outside the repository's working trees, with
the configured command, after linking into it each of the language's environment directories (a language fact in the
trmv contract) that exists in the current working tree. Diagnostics SHALL be keyed by repo-relative paths. The
temporary worktree SHALL be removed and its registration pruned on every exit path. A checker failure at the merge
base SHALL exit 2 naming the merge-base commit. A language whose baseline file the repo tracks at `HEAD` SHALL behave
as outside stealth mode.

The result SHALL be cached under `<C>/trmv/typecheck/`, keyed by the merge-base commit, the language and a
fingerprint of the configured command, the trmv version and the current contents of the language's fingerprint files
(a language fact in the trmv contract). A run whose key matches a cached result SHALL NOT run the checker at the
merge base; a malformed cache entry SHALL be recomputed.

#### Scenario: Pre-existing error is not new
- **WHEN** a stealth repo without a tracked Python baseline has one type error at the merge base, the change moves it down three lines, and `trmv-typecheck --base main` runs
- **THEN** it exits 0

#### Scenario: Introduced error is new
- **WHEN** the change adds a type error that the merge base does not have and `trmv-typecheck --base main` runs in stealth mode
- **THEN** it exits 1 listing that error

#### Scenario: Nothing written to the tree
- **WHEN** `trmv-typecheck --base main` runs in stealth mode in a repo without tracked baselines
- **THEN** `git status --porcelain` is unchanged and `git worktree list` lists the same worktrees as before

#### Scenario: Cached merge-base result
- **WHEN** `trmv-typecheck --base main` runs twice in stealth mode with no change to the merge base, the configured command or the fingerprint files
- **THEN** the second run does not run the checker at the merge base and prints the same report

#### Scenario: Fingerprint change recomputes
- **WHEN** a fingerprint file of the language changes between two stealth runs
- **THEN** the second run runs the checker at the merge base again

#### Scenario: Tracked baseline in stealth
- **WHEN** a stealth repo tracks `.basedpyright/baseline.json` at `HEAD` and `trmv-typecheck` runs
- **THEN** it behaves exactly as outside stealth mode

#### Scenario: No base ref
- **WHEN** `trmv-typecheck` runs in stealth mode without `--base`, no baseline is tracked, and `refs/remotes/origin/HEAD` does not exist
- **THEN** it exits 2 with the message naming `--base`

#### Scenario: Same report from either twin
- **WHEN** `trmv-typecheck --base main` runs in stealth mode through each twin on a mixed repo
- **THEN** both runs produce byte-identical stdout, stderr and exit codes

### Requirement: Base option
`trmv-typecheck` SHALL accept `--base BRANCH`. Outside stealth mode, and for a language whose baseline the repo tracks
at `HEAD`, it SHALL have no effect. A twin running a language section through the other twin SHALL pass it on.

#### Scenario: Base ignored outside stealth
- **WHEN** `trmv-typecheck --base main` runs in a repo with a committed config and committed baselines
- **THEN** stdout, stderr and the exit code equal those of `trmv-typecheck`

### Requirement: Realignment needs a tracked baseline in stealth
In stealth mode, `--realign-from` SHALL exit 2 with a stealth refusal naming the option, before any checker runs, when
the repo tracks no Python baseline at `HEAD`.

#### Scenario: Realign refused without a tracked baseline
- **WHEN** `trmv-typecheck --realign-from HEAD` runs in stealth mode and the repo tracks no `.basedpyright/baseline.json`
- **THEN** it exits 2 with the stealth refusal and no checker runs
