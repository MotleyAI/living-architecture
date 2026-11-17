## 0. Setup

- [x] 0.1 Install Rust stable with rustup into `~/.cargo`; verify `cargo --version` and that `uvx maturin --version` and `uvx --from ziglang python -m ziglang version` run.
- [x] 0.2 Create the SLayer copy: `git archive 452a2f57` of `~/GitHub/SLayer/slayer` into a directory outside both repos, `.venv` symlinked; record the path and the sorted `.py` manifest hash in `spike/README.md`; verify the file count is computed, not hard-coded.
- [x] 0.3 Scaffold `spike/` (`README.md`, `rust/` workspace with `binding`, `fidelity`, `hello` crates, ruff crates pinned `=0.0.22`, `py/`, `tests/`); verify `cargo build --release` and `uv run --project python pytest spike/tests --collect-only` succeed.

## 1. Tests first (pr-tests)

- [x] 1.1 Synthetic inputs in `spike/tests/data/` per design decision 14; verify each file's intended accept/reject per CPython version with a test.
- [x] 1.2 Python canonical binding dump (`spike/py/binding_dump.py`) per design decision 7, reading through `Snapshot`; tests pin its output on a few synthetic files by hand.
- [x] 1.3 Binding differential test: Python dump on 3.11–3.14 vs the Rust `dump` binary, parametrized over the fixtures and the synthetic set, and over the SLayer copy given its path; fails until the Rust port exists.
- [x] 1.4 Fidelity harness tests: the CPython-side span and token dump (tokens mapped onto AST nodes, decision 12) and the comparer, on the synthetic set, including a planted offset difference the comparer must report.
- [x] 1.5 Packaging tests: the wheel builds, installs into a fresh venv, the module imports, both console scripts run and print the same as the module function.
- [x] 1.6 Codex review of the tests against this plan; findings resolved with the user.

## 2. Rust binding port (14-hour box, pr-implement)

- [ ] 2.1 Ingestion and `SourceFile` equivalent: raw bytes → dr's decoding rule → ruff parse → character offsets; verify on the encoding synthetic files.
- [ ] 2.2 `Binder` and `Scope` port (all scope kinds, globals/nonlocals, imports, stars, `__all__`, comprehensions, type parameters, `match`, walrus); verify with the differential.
- [ ] 2.3 `_Parsed` port (sites, points with evaluated-first spans, occurrences incl. annotation strings, class loop spans) and the dump queries (`owner`, `resolving`, `may_precede`, `joined`); verify with the differential on fixtures and synthetic files.
- [ ] 2.4 Differential on the SLayer copy under 3.11–3.14; classify each remaining mismatch (parser difference or unported form) with count and example. Stop porting at 14 hours.

## 3. Speedup measurement

- [ ] 3.1 Bench drivers on both sides per design decision 8 (both lifetime regimes, phase timers, no dump), refusing on a manifest-hash mismatch and running the differential first; verify they report the matching-file set.
- [ ] 3.2 Run the bench: 5 runs each, median and p95, peak RSS, single-threaded plus the rayon row; record hardware and load.
- [ ] 3.3 Baseline per design decision 9 (3 unprofiled runs + 1 diagnostic cProfile) at this branch's HEAD; record phases and peak RSS.

## 4. Parser fidelity measurement

- [ ] 4.1 Ruff-side span and token dump (`fidelity` crate) with the per-version parse options recorded; verify on the synthetic set.
- [ ] 4.2 Run the comparison over fixtures, SLayer and the synthetic set on 3.11–3.14; produce the class table (count, example, special form), the accept/reject table, the dr-rule vs `detect_encoding` disagreements, and CPython cross-version differences.

## 5. Packaging measurement

- [ ] 5.1 `hello` maturin project (abi3-py311, module + two console scripts) and the plain binary; verify the 1.5 tests pass.
- [ ] 5.2 Start-up timing per design decision 15.
- [ ] 5.3 Build x86_64 glibc and musl (load musl in Alpine via docker), aarch64 glibc and musl with `--zig` (not loaded); record outcomes; state macOS as not built.

## 6. Report and decisions

- [ ] 6.1 `spike/README.md` reproduces every number; post the measurements comment on DEV-2328.
- [ ] 6.2 Ask the user, one at a time with the numbers: go or no-go; how la uses dr as a library; reproduce or change goldens per parser difference class; the unit-test rule; the crate layout of `rust/`. Record the answers in the DEV-2328 comment.
- [ ] 6.3 Propose the edits to DEV-2327 and the later step issues that follow from the decisions; apply each after the user's OK.
- [ ] 6.4 Commit and push the branch; no PR. The flow ends here.
