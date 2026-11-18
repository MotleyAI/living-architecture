## Context

See proposal.md for why. The hot path is the per-file analysis `BindingCheck` builds (`python/src/living_architecture/refactor/bindings.py`):
`Snapshot.text` decodes the bytes (UTF-8 BOM stripped, then dr's coding-cookie rule `read_str_coding`, else UTF-8),
`SourceFile` parses them with `ast.parse` and converts byte columns to character offsets, `static_resolver.Module`
runs the `Binder` (scopes with `raw`, `bindings`, `globals`, `nonlocals`; bound names, loads, annotations, star
imports, `__all__`), and `bindings._Parsed` derives `sites`, binding `points` (name offset, run offset,
evaluated-first span), occurrences per name, `stars`, `all_names` and each class's loop spans.

Architecture: no model element, arrow or spec mapping changes. `system.arc42.md` principle 4 applies and holds: every
input file is parsed, never imported or executed. Principles 1 to 3 govern the twins, which this change does not touch.
`la-arch-check` stays green with `spike/` present.

## Goals / Non-Goals

**Goals:**

- A go/no-go number that compares the same work on both sides.
- Every parser difference class dr would meet, counted, with an example.
- Evidence that one abi3 wheel serves as module and console scripts, and what that costs at start-up.

**Non-Goals:**

- Any command implemented in Rust; any change to the twins, the contract, the corpus or CI.
- Building the macOS wheels or checking any target in CI (moved to DEV-2332, user decision).
- Porting anything beyond the per-file analysis (no `World`, no `_Judge`, no cross-file resolution).

## Decisions

Each entry gives the decision, the options weighed and who took it.

1. **Where the spike lives: `spike/` on this branch, pushed, no PR, nothing merged; the `/la:pr` flow ends after
   `pr-implement`, and this change is never archived.** Weighed: a PR merging only this change and a results document
   (contradicts "nothing merges", reviews throwaway code); merging the spike as the start of `rust/` (presumes the
   go and the crate layout this spike decides). (user) Amended after the decisions (user, 2026-11-18): step 3
   (DEV-2330) merges this branch into its own, keeps the reusable code (moved into `rust/dr-python` and its
   differential), deletes the rest of `spike/` and archives this change in its PR.
2. **Equivalence: a byte-equal canonical dump of everything `_Parsed` and its scopes hold, time-boxed to 14 hours of
   port plus differential.** Mismatches left when the box ends are reported by class, with count and example, each
   marked parser difference or unported form. Weighed: a reduced dump (lets unchecked parts do less work and inflate
   the speedup); no check (an unverifiable number). (user)
3. **Packaging targets: local builds only.** x86_64 glibc built and loaded; x86_64 musl built with `maturin --zig`
   and loaded in an Alpine container; aarch64 glibc and musl built, not loaded; macOS not built. The report states
   measurement 3 as incomplete on those points. Weighed: a temporary branch-only CI workflow; a `workflow_dispatch`
   workflow (needs a file on `main`). DEV-2328's measurement text was edited to match, with this approved wording:
   "Build the wheel locally for the four Linux targets, and load each one where this machine can run it. Building the
   two macOS targets and checking all six in CI move to DEV-2332 (user decision, 2026-11-17)." (user, approved wording)
4. **The 10× bar is read on single-threaded, end-to-end parse plus analysis, over the SLayer files whose dumps match
   on every CPython version that accepts them.** The report prominently gives the share of files and of Python time
   left out, and an all-files total as a secondary row. (codex)
5. **Binding equivalence on CPython 3.11, 3.12, 3.13 and 3.14.** The Python dump runs under each; Rust is compared
   with each version that accepts the file. Dumps that differ between CPython versions are listed apart, as an
   existing Python-twin hazard. (codex)
6. **Ingestion is identical raw-byte decoding on both sides.** Python uses `Snapshot.text`/`Snapshot.source`
   exactly; Rust reimplements that rule (BOM strip, `read_str_coding`'s regex on the first two lines, else UTF-8;
   undecodable → no analysis). The fidelity run also records files where dr's rule and `tokenize.detect_encoding`
   disagree, and compares both character and byte offsets. (codex)
7. **The dump holds the resolution-relevant state, not just the derived lists.** Per scope: kind, parent, `raw`,
   `bindings` (each binding by kind and offset), `globals`, `nonlocals`; per name used: `owner` and `resolving`;
   per occurrence: `may_precede` for each class scope binding the name, and `joined` per scope. Scopes are numbered
   in creation order. (codex)
8. **Timing protocol.** End-to-end parse plus analysis is the primary metric, with phase timers inside the same run
   and no JSON written while timing. Two lifetime regimes, identical on both sides: (a) every analysed state kept,
   as `World` keeps them; (b) one file at a time, dropped after analysis. Median and p95 of 5 runs, single-threaded,
   CPython 3.12 for Python; a rayon run as an extra row. Peak RSS by `/usr/bin/time -v`. Hardware, CPU governor and
   load are recorded. (codex, default for the run count)
9. **Baseline at this branch's HEAD**, the issue's single-method rename, cold (`LA_CACHE_DIR` empty, page cache not
   dropped since that needs sudo), 3 runs without profiler, median, phases and peak RSS. One cProfile run is
   diagnostic only and never compared with Rust numbers. rope is still installed for moves; the measured rename path
   no longer uses it. (codex, default)
10. **Corpus integrity.** The bench and report commands take the SLayer copy's path, compute a sorted manifest hash of
    its `.py` files and refuse when it differs from the one recorded on first extraction; they run the differential
    right before timing. File counts are computed, never hard-coded. (codex)
11. **SLayer snapshot: `git archive 452a2f57`** of `~/GitHub/SLayer/slayer` (the DEV-1607 branch commit DEV-2315
    used), `.venv` symlinked, own `LA_CACHE_DIR`, outside both repos. (default)
12. **Fidelity components from tokens.** CPython's AST merges implicitly concatenated literals into one `Constant`,
    so each literal part, each f-string literal part, replacement field and format spec comes from `tokenize`
    mapped onto its AST node. Covered by synthetic tests for prefixes, `{{`/`}}`, nested format specs and
    concatenated f-strings. (codex)
13. **Ruff target versions.** The exact parse-options call per CPython version is recorded in the report. A form the
    pinned parser cannot parse for a version (for example t-strings, if so) is a ruff rejection in the
    accept/reject table, never a skipped file. (codex)
14. **Synthetic inputs** in `spike/tests/data/` for forms the corpus may lack: `\r\n`, lone `\r`, latin-1 cookie,
    BOM, BOM plus cookie, invalid cookie, cookie not matching the bytes, form feed, non-ASCII and NFKC-folding
    identifiers, nested and triple-quoted f-strings, PEP 695 generics, `match`, walrus in comprehensions, string
    forward references, a 3.12-only file, a 3.14-only file (t-strings), a syntax error. (default, extension of the
    issue's list; codex)
15. **Start-up comparison.** The console script, the plain Rust binary and a Python console script each print the
    same line and do nothing else; 10 warm-up runs, then 50 timed; median and p95. (codex)
16. **PyO3 `abi3-py311`**, the package's `requires-python` floor. (default)
17. **Spike tests live in `spike/tests`, outside `python/tests` and outside CI**: `spike/` never lands as it is (decision 1), so CI has nothing
    to guard. (default)
18. **Ruff crates pinned `=0.0.22`; `Cargo.lock` committed.** (default, from the issue)

## Risks / Trade-offs

- [The 14-hour box ends with a sizeable unmatched share] → the bar is read on matching files only, and the excluded
  share is reported next to it, so the user decides with the gap in view.
- [Ruff 0.0.22's AST lacks a form (t-strings) or splits nodes differently] → counted as a parser difference class,
  never patched over in the dump.
- [Page cache not dropped (needs sudo)] → both sides read the same files first in an untimed warm-up pass, so both
  are timed warm; the baseline's "cold" means an empty `LA_CACHE_DIR` only.
- [Machine load skews timings] → median and p95 of repeated runs, load recorded.

## Migration Plan

None here. Step 3 (DEV-2330) merges this branch and moves the reusable code into `rust/` (decision 1).
