# CI profile (2026-11-16)

Runs: `main` @ `bc103e73` (run 43844086245) and this branch with DEV-2301 merged (run 43862183837, with
`--durations` and JUnit output). Local runs: a 32-core machine, pinned with `taskset` to 4 CPUs and `-n 4`.

## Where the time goes

### Heavy steps (wall-clock)

| Job | `main` | with DEV-2301 |
| -- | -- | -- |
| `test (3.11)` pytest | 666 s | 976 s |
| `test (3.12)` pytest | 667 s | 770 s |
| `test (3.13)` pytest | 614 s | 909 s |
| `test (3.14)` pytest | 445 s | 1,261 s |
| `cross-twin (typescript)` | 621 s | 991 s |
| `cross-twin (python)` | 564 s | 758 s |

Every other step is under 1 min (`node`'s `npm test` 46–63 s). `test (3.14)` with DEV-2301 is uniformly about 1.6×
slower than 3.12 in every test file, so it ran on a slower runner: runner speed varies that much between jobs.

### CPU count explains the CI-versus-local gap

| | summed test time | wall-clock |
| -- | -- | -- |
| CI `test (3.12)`, 4 vCPUs | 2,604 s | 770 s |
| local, pinned to 4 CPUs | 2,608 s | 762 s |
| `main`, local, pinned to 4 CPUs | 1,083 s | 334 s |

The "about 100 s locally" in the issue is the same suite on 32 cores.

### Top costs (`test (3.12)`, with DEV-2301, summed test time 2,604 s)

| Area | Summed | Note |
| -- | -- | -- |
| conformance cases (4,178 runs) | 1,076 s | refactor 638 s (0.53 s/run, 0.23 s on `main`), arch 168 s, config 57 s, shim 56 s |
| `test_keyed_rename` (39 tests) | 614 s | 15.7 s/test; 1.7 s on `main` |
| `test_parameter_rename` | 114 s | |
| `test_compliance_attr` | 100 s | 4.8 s/test; 0.6 s on `main` |
| everything else | ~700 s | no file above 75 s |

`cross-twin`: python leg 2,237 s summed (refactor 1,157 s, arch 408 s), typescript leg 2,772 s (refactor 1,525 s,
arch 609 s). The slowest single cases are the pydantic field and key renames (13–23 s each).

### Inside a run

- **The export pass's transitive follow (DEV-2301).** A CPU profile of basedpyright during one 22 s keyed-rename test:
  18 s in `DefinitionProvider` reached from `Exporter.follow` → `getSourceFilesFromStub` /
  `_isStubThatShouldBeMappedToImplementation` (stub-to-source mapping, uncached), following field annotations and
  bases into pydantic and typeshed. Stopping the follow at third-party and typeshed files: the 1,552 affected tests
  pass and their summed time falls from 1,493 s to 761 s (`test_keyed_rename` 609 → 114 s).
- **Per refactor run**: about +0.3 s median against `main`, consistent with the language-server start every rename now
  pays.
- **Case set-up** (fixture copy, `git init`, commits): 8 ms per case. Negligible.
- **Process start-up**: `python -c pass` 13 ms; Python-twin `la-config get tracker` about 280 ms, of which about
  185 ms is importing `living_architecture.cli` (refactor 61 ms, affected 85 ms, rope 32 ms, jsonschema 24 ms,
  `importlib.metadata` 16 ms); the commands it needs (`config`, `contract`) take about 45 ms. npm-twin `la-config`
  about 160 ms; `typescript` is no longer loaded at start-up.

### Duplicated work

- The twin-native conformance cases run in all four `test` jobs (1,076–1,336 s summed each), and `cross-twin
  (python)` runs every case through the PyPI twin on Python 3.13: the `test (3.13)` run is a pure duplicate; the
  others add only version coverage.
- The two `cross-twin` legs run the same cases through different invoking twins: not duplicated (twin rule).

## Options (effort vs impact)

Savings are wall-clock on the affected jobs, estimated from summed test time on a 4-vCPU runner (~3.4× parallel).

| # | Change | Effort | Saving | Slowest job after this row and those above |
| -- | -- | -- | -- | -- |
| A | Export follow stops at third-party and typeshed files | S | about −3.5 to −4.5 min per `test` job, −1.5 min per `cross-twin` leg | ~15 min |
| D1 | Drop native conformance from `test (3.13)` | XS | −4 to −5 min on that job | ~15 min |
| B | Shard: `test` ×2, `cross-twin` ×3 | S–M | about −45% per `test` job, −60% per `cross-twin` leg | ~6.5 min |
| C | One entry module per Python-twin command | M | about −1.5 to −3.5 min per Python-heavy job unsharded | ~5.5–6 min |
| D2 | Drop native conformance from 3.11, 3.12, 3.14 too (coverage cut) | XS | −4 to −5 min summed per job | ~5 min |
| E | Avoid the per-run language-server start in refactor runs | L, uncertain | about −1.5 min per job unsharded | ~4.5–5 min |

Chosen: A, B, C, D1, D2. Not E.

## DEV-2038 cross-check

| DEV-2038 item | Status |
| -- | -- |
| 1. Parallel conformance (`pytest-xdist`, `-n auto`) | landed (`addopts = "-n auto"`); keep |
| 2. Split `cross-twin` per invoking twin | landed; extended here by sharding (B) |
| 3. Lazy `typescript` import in the npm twin | landed (`la-config`, `la-doctor --twin` no longer open it); C is the Python-twin counterpart |
| 4. Skip our own twin in discovery | landed in both twins (`_discover_dir` / `discoverDir`) |
| 5. Remove duplicated runs: `node` job conformance | landed |
| 5. Conformance on one Python version | done here (D2, approved coverage cut) |
| 5. Skip pairs each twin's suite runs in `cross-twin` | drop: with D2 the `test` jobs no longer run conformance, so nothing is duplicated |
| 6. Build once per job; npm/uv caches | `node` job no longer builds for conformance; `setup-node` caches npm; setup steps total < 30 s per job: drop |
| Acceptance "slowest job ≤ 5 min" | replaced by the user's choice from the curve above |

## After

Filled from this PR's CI run (task 5.1): run 43889989137 on `e23534f9`. Wall is the heavy step; "Before" is the
with-DEV-2301 run above. "After" summed is the committed `pytest-split` duration file, recorded on CI with this
change's code (the run itself prints no per-test times).

| Job kind | Before: wall / summed | After: wall (slowest shard) / summed |
| -- | -- | -- |
| `test` | 770 s (3.12; 614–1,261 s over versions) / 2,604 s | 121 s (3.12; 115–194 s over versions) / 1,291 s |
| `cross-twin (python)` | 758 s / 2,237 s | 220 s / 1,321 s |
| `cross-twin (typescript)` | 991 s / 2,772 s | 203 s / 2,250 s |

The first sharded run (`1e5ba22d`, run 43880287484) left the slowest `cross-twin` shard at 421 s: xdist's default
`load` scheduler handed one worker a contiguous block of 218 expensive refactor cases and never rebalances.
`--dist worksteal` in `addopts` brings it to the figures above.
