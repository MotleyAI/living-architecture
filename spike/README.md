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
  - `binding` also has bin `binding-bench`, the Rust bench driver.
- `py/`: the CPython side: `binding_dump.py` (the oracle), `fidelity_dump.py`, `fidelity_compare.py`, `corpus.py`;
  the bench driver `bench.py`; the measurement runners `bench_run.py`, `baseline_run.py`, `fidelity_run.py`,
  `packaging_run.py`.
- `results/`: the JSON reports the runners wrote for the numbers below.
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

## Results (2026-11-17)

Reproduce each with `source ~/.cargo/env`, then from `spike/py`:

```bash
uv run --project ../../python python bench_run.py --slayer ~/dr-spike/slayer-452a2f57 --out ../results/bench.json
uv run --project ../../python python baseline_run.py --slayer ~/dr-spike/slayer-452a2f57 --out ../results/baseline.json
uv run --project ../../python python fidelity_run.py --slayer ~/dr-spike/slayer-452a2f57 --out ../results/fidelity.json
uv run --project ../../python python packaging_run.py --out ../results/packaging.json
```

Machine: Intel i9-14900KF (32 threads, P and E cores), `powersave` governor, kernel 7.0.0-43, shared with other
work: load average 5 to 15 during the runs (each report records it before and after). The runners ran one at a
time.

### 1. Port and binding equivalence

The port (`rust/binding`, about 1,500 lines with its dump) covers `Snapshot.text`'s decoding rule, `SourceFile`'s offsets,
`static_resolver.Binder`/`Module`/`Scope` and `bindings._Parsed` with its queries. Its canonical dump is byte-equal
to `py/binding_dump.py`'s on **every file CPython accepts, on 3.11, 3.12, 3.13 and 3.14**: 25 synthetic files, 1,421
conformance files, 1,619 SLayer files; 0 mismatches, so no file is left out of the speedup and no mismatch class
exists. It took well under the 14-hour box. ruff's spans are mapped onto CPython's where they differ (section 4)
inside the port: a decorated definition's start, an `elif`'s statement end, a parameter's name. Ingestion
implements the UTF-8, UTF-8-SIG, Latin-1 and ASCII codecs; another codec Python knows reports
`unsupported-encoding` (none occurs in the corpora).

CPython's own dumps do not differ between 3.11 and 3.14 on any file of the three corpora (binding and fidelity).

### 2. Speedup (`results/bench.json`)

Single-threaded, end to end per file: read and decode, parse, analyse (`_Parsed`). Python on CPython 3.12, Rust
with `--python-version 3.12`. All 1,619 SLayer files (the matching set is all of them). Median (p95) of 5 runs;
peak RSS by `/usr/bin/time -v`.

| Regime | Python | Rust | Speedup | Python peak | Rust peak |
| -- | -- | -- | -- | -- | -- |
| keep every analysed state (as `World`) | 11.10 s (12.55) | 0.416 s (0.519) | **26.7×** | 448 MB | 205 MB |
| one file at a time | 9.65 s (10.65) | 0.402 s (0.446) | **24.0×** | 160 MB | 12 MB |
| keep, rayon on 32 threads | | 0.123 s (0.126) | 90× | | 231 MB |
| one at a time, rayon on 32 threads | | 0.042 s (0.049) | 231× | | 75 MB |

Phases (keep, median): decode 0.088 s vs 0.022 s; parse (`ast.parse` vs ruff) 2.66 s vs 0.208 s, 12.8×; analysis
8.39 s vs 0.177 s, **47×**. An earlier full run under lower load gave 25.5× and 22.8×. The kept Rust state is
about 190 MB for 1,619 files against Python's 290 MB: the per-scope hash maps are not compacted yet.

### 3. Baseline (`results/baseline.json`)

`dr-refactor --timings rename --file slayer/storage/base.py --symbol StorageBackend.validate_for_save --new-name
validate_before_save --allow-blindspots`, dry run, this branch's HEAD `e0554e69`, `LA_CACHE_DIR` empty per run, 3
runs. Median: load 0.16 s, resolve 0.02 s, references 2.05 s, rules 5.13 s, **conflicts 6.65 s**, baseline 1.26 s,
**total 19.05 s**, peak RSS 1.28 GB. The one cProfile run (diagnostic, 48 s profiled) puts 20.0 s of its 23.9 s
`conflicts` in `_Parsed.__init__`, 1,162 calls from `BindingCheck._star_importers`: the work section 2 times.

### 4. Parser fidelity (`results/fidelity.json`)

Every file of the three corpora, on each CPython version against ruff with that target version
(`ParseOptions::from(Mode::Module).with_target_version(...)`; a `ParseError` or an `UnsupportedSyntaxError` counts
as a rejection).

**Accept/reject:** identical on every file and version (SLayer 1,619 ok; conformance 1,395 ok, 19 syntax errors, 7
undecodable; synthetic per version as `tests/test_synthetic.py` pins). ruff 0.0.22 parses t-strings, PEP 695 and
PEP 696 and rejects them for the versions CPython rejects them.

**Strings, comments, f-string parts, encodings:** no difference. Every string literal part, f-string literal run,
replacement field and format spec, every comment and string token, has the same character and byte span, including
in the files with `\r\n`, a lone `\r`, a BOM, a coding cookie, form feeds and non-ASCII identifiers.

**Node classes** (count per CPython version; the same on all four):

| Class | SLayer | conformance | synthetic | Example |
| -- | -- | -- | -- | -- |
| decorated `def`/`async def`/`class` start: CPython at the keyword, ruff at the first `@` | 5,226 | 44 | 1 | `slayer/api/server.py`, 13021 vs 12985 |
| a generator that is a call's sole argument: CPython's span includes the call's parentheses, ruff's does not | 3,150 | 1 | 1 | `setup_metricflow.py`, 4185–4238 vs 4186–4237 |
| `*args`/`**kw` parameter start: ruff includes the stars | 1,386 | 17 | 2 | `setup_metricflow.py`, 10145 vs 10144 |
| `elif` end: CPython's nested `If` ends with the whole chain, ruff's clause with its own body | 251 | 0 | 0 | `scripts/doc_examples.py`, 10991 vs 10839 |

(The comparer pairs 6 of SLayer's generators by a shared end with the enclosing generator, so they show as
"GeneratorExp start"; they are the second class.)

**Tokens of rejected files only:** on files both parsers reject, CPython's tokenizer fails (`TokenError`) where
ruff's lexer does not, and CPython 3.11 to 3.13 tokenize a t-string, and 3.11 a PEP 701 f-string, the old way.
dr analyses no rejected file.

**dr's decoding rule vs `tokenize.detect_encoding`:** they differ only on the synthetic files written for it (BOM
plus Latin-1 cookie, a cookie on the second line, a cookie dr misses) and on 3 conformance fixtures that are binary
(both fail). None in SLayer.

### 5. Packaging (`results/packaging.json`)

One maturin project (`rust/hello`, PyO3 0.30.1, `abi3-py311`) builds one `cp311-abi3` wheel holding the module
`dr_hello` and the console scripts `dr-hello` and `dr-hello-two`; installed into fresh CPython 3.11 and 3.14 venvs,
the module imports and both scripts print `greeting()`'s line (`tests/test_packaging.py`).

| Target | Wheel | Loaded |
| -- | -- | -- |
| x86_64 glibc | `cp311-abi3-manylinux_2_34_x86_64` (native build, host glibc), 1.4 MB | natively, CPython 3.11, 3.12, 3.14 |
| x86_64 musl | `cp311-abi3-musllinux_1_2_x86_64` (`--zig`), 1.4 MB | `python:3.12-alpine` in docker: import and both scripts |
| aarch64 glibc | `cp311-abi3-manylinux2014_aarch64` (`--zig`), 1.4 MB | not loaded: this machine cannot run it |
| aarch64 musl | `cp311-abi3-musllinux_1_2_aarch64` (`--zig`), 1.4 MB | not loaded: this machine cannot run it |
| macOS x86_64, arm64 | not built | moved to DEV-2332 |

Measurement 3 is incomplete on the two aarch64 loads, the macOS builds and CI, as decided. A release build for
x86_64 glibc needs `--zig` or a manylinux container for a lower glibc tag than the host's 2.34.

Start-up, CPython 3.12, 10 warm-up then 50 timed runs, median (p95): console script backed by the abi3 module 8.9
ms (12.3); plain Rust binary 0.57 ms (0.70); pure-Python console script 10.1 ms (18.6). A console script costs the
interpreter's start-up, about 8 ms per command, against seconds of work per refactor.

The workspace builds the PyO3 crate with `extension-module` on by default: without it, a plain `cargo build` links
`libpython3.x`, which a system Python without the shared library cannot satisfy.
