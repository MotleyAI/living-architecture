## Why

The umbrella DEV-2327 proposes moving the Python `deterministic-refactor` to Rust because dr's own pure-Python AST work
dominates large renames (about 17 of 20.4 s for one rename on SLayer). Before any of it is built, this spike answers
whether the port is worth it and on which design: it measures the speedup on the real hot path, how far ruff's parser
differs from CPython on what dr reads, and whether one PyO3 abi3 wheel can serve both as a library and as the `dr-*`
commands.

## What Changes

- A `spike/` directory on this branch, with no PR of its own (step 3 merges the branch and keeps the reusable
  code; design decision 1): a Cargo workspace porting the per-file
  binding analysis (`SourceFile` + `static_resolver.Module` + `bindings._Parsed`) onto `ruff_python_parser`, a
  ruff-side span and token dump, a PyO3 hello-world wheel, and the Python drivers, differentials and report builders.
- Three measurements (speedup, parser fidelity, packaging) and their report, posted as a comment on DEV-2328.
- The decisions DEV-2328 ends with, asked of the user with the numbers, and DEV-2327 plus the later step issues edited
  to match them.
- Nothing under `python/`, `node/`, `shared/`, `conformance/`, `plugin/`, `architecture/` or `.github/` changes. No
  command's behaviour changes, so this change has no spec delta (`skip_specs: true`).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None.

## Impact

- New, unmerged: `spike/` (Rust workspace, Python scripts, pytest differentials outside `python/tests` and outside
  CI).
- Developer machine: a Rust stable toolchain under `~/.cargo` (rustup); `maturin` and `ziglang` run through `uvx`.
- Tracker: a measurements comment on DEV-2328; edits to DEV-2327 and its step issues after the user's decisions.
