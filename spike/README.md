# Rust dr spike (DEV-2328)

Throwaway: lives on this branch only and never merges. The plan is
`openspec/changes/dev-2328-living-architecture-rust-dr-step-1-spike/`.

## Setup

- Rust stable via rustup in `~/.cargo` (`cargo 1.100.0` when set up). `maturin` and zig run through `uvx`:
  `uvx maturin --version` printed `maturin 1.16.0`, `uvx --from ziglang python -m ziglang version` printed `0.17.1`.
- SLayer copy: `git archive 452a2f57` of `~/GitHub/SLayer/slayer`, extracted to `~/dr-spike/slayer-452a2f57`, with
  `.venv` symlinked to the checkout's. Its own `LA_CACHE_DIR` is `~/dr-spike/la-cache`.
- SLayer manifest hash (`corpus.manifest_hash`, sorted `.py` paths and contents, symlinked `.venv` not followed):
  `c73df99dedee2e7b86d3d693d86bc7e6e351ba5e4cd0e3e9cbdcf36cb6e7ea40`, recorded in `slayer-manifest.sha256`; the
  count is `len(corpus.py_files(root))` (1619 at extraction).

## Layout

- `rust/`: Cargo workspace; ruff crates pinned `=0.0.22`, `Cargo.lock` committed.
  - `binding`: the port of dr's per-file binding analysis; bin `binding-dump`.
  - `fidelity`: ruff's spans and tokens; bin `fidelity-dump`.
  - `hello`: the PyO3 abi3 packaging probe.
- `py/`: the CPython side: `binding_dump.py` (the oracle), `fidelity_dump.py`, `fidelity_compare.py`, `corpus.py`.
- `tests/`: pytest, outside `python/tests` and outside CI; `tests/data/` holds the synthetic inputs.

## Contracts the Rust side meets (pinned by `tests/`)

- `binding-dump --python-version 3.X --root DIR [REL ...]` (RELs from stdin when none): one `REL<TAB>JSON` line per
  file, the JSON byte-equal to `py/binding_dump.py`'s under CPython 3.X (`canonical`: sorted keys, no spaces, raw
  UTF-8).
- `fidelity-dump --python-version 3.X --root DIR [REL ...]`: the same line format and schema as
  `py/fidelity_dump.py` (`status`; `tokens`, `nodes`, `strings` entries with `kind`, `chars`, `bytes`, and `node` for
  strings). `fidelity-dump --describe-options --python-version 3.X` prints the ruff parse options used for 3.X.
- `hello`: a maturin project building one `cp311-abi3` wheel with module `dr_hello` (`greeting()`) and console
  scripts `dr-hello` and `dr-hello-two`, each printing `greeting()`'s line.

## Running the tests

```bash
uv run --project python pytest spike/tests
uv run --project python pytest spike/tests --slayer=$HOME/dr-spike/slayer-452a2f57   # adds the SLayer copy
```

Pass `--slayer=PATH` with `=`: as a separate argument, pytest loads the copy's own `conftest.py`. The Python side
runs under each of CPython 3.11 to 3.14 through `uv run --isolated --no-project --with-editable python`.
