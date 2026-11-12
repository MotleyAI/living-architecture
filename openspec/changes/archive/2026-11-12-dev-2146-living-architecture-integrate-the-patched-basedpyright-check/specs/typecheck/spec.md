## ADDED Requirements

### Requirement: Python checker is patched
For Python, in check and write mode, `la-typecheck` SHALL run the configured command with a preload added to the
end of the command's `NODE_OPTIONS`, keeping any existing value. When Node compiles basedpyright's CLI bundle, the
preload SHALL remove the condition `!isGetTypeFromCodeFlowPending(referenceKeyWithSymbolId) &&` (microsoft/pyright#11919)
from the compiled source, in the main thread and in every worker thread, and SHALL modify no file. It SHALL patch
only when the bundle's embedded basedpyright version is in the shared contract's verified-version table and the
condition occurs exactly once in the bundle. The run SHALL exit 2 with the shared `typecheck.patch-unverified`
text for an unlisted version, with `typecheck.patch-mismatch` when the condition does not occur exactly once,
and with `typecheck.patch-not-applied` when the command loaded no basedpyright bundle under the preload; the
command's own output SHALL still be relayed. A patched run SHALL print nothing beyond the checker's output. The
verified-version table SHALL initially hold exactly `1.40.2`.

#### Scenario: Dropped diagnostic is reported
- **WHEN** a repo with basedpyright 1.40.2 checks a file whose loop body is `assert k in d, k` followed by a
  type error on `d`
- **THEN** the type error is reported and the exit code is 1

#### Scenario: Worker threads are patched
- **WHEN** the configured command passes `--threads 4` and thirteen files each hold that pattern
- **THEN** all thirteen errors are reported

#### Scenario: Wrapper command
- **WHEN** the configured command starts basedpyright through a wrapper such as `uv run basedpyright`
- **THEN** the patch applies and the run behaves as a direct one

#### Scenario: Existing NODE_OPTIONS kept
- **WHEN** `NODE_OPTIONS` is already set when `la-typecheck` starts
- **THEN** the checker sees the existing value followed by the preload

#### Scenario: Installed checker untouched
- **WHEN** a patched run finishes
- **THEN** every file of the installed basedpyright is byte-identical to before the run

#### Scenario: Unverified version
- **WHEN** the installed basedpyright is 1.39.10
- **THEN** the run exits 2 and stderr names 1.39.10 and the verified versions

#### Scenario: Bundle already patched in place
- **WHEN** the installed 1.40.2 bundle no longer contains the condition
- **THEN** the run exits 2 and stderr reports the condition was found 0 times

#### Scenario: Command does not run basedpyright under Node
- **WHEN** the configured command never loads basedpyright's bundle with the preload, for example because it
  clears `NODE_OPTIONS`
- **THEN** the run exits 2 with the not-applied text after relaying the command's output

#### Scenario: Write mode refused on a patch failure
- **WHEN** `la-typecheck --write-baseline` runs with an unverified basedpyright and no Python baseline
- **THEN** the run exits 2 and no baseline is written

#### Scenario: Patch failure through the npm twin
- **WHEN** a patch failure occurs while `la-typecheck` runs through the npm twin on a mixed repo
- **THEN** stdout, stderr and the exit code are byte-identical to the run through the PyPI twin

## MODIFIED Requirements

### Requirement: Python baselines are basedpyright's own
For Python, `la-typecheck` SHALL run the command as configured, apart from the patch preload in its
environment. When the patch applied, it SHALL pass basedpyright's output and its exit codes 0 and 1 through
unchanged and map any higher exit code to 2. In write mode it SHALL append `--writebaseline` and exit 0 after a
successful, patched write. The Python baseline file SHALL be `.basedpyright/baseline.json`.

#### Scenario: Shrink passed through
- **WHEN** a patched Python run fixes a baselined error and adds none
- **THEN** basedpyright's baseline-update message prints and the exit code is 0

#### Scenario: Initial write exits 0
- **WHEN** `la-typecheck --write-baseline` runs on a Python repo with errors and no baseline, and the patch
  applies
- **THEN** the baseline is written and the exit code is 0
