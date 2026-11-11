## Context

See proposal.md (Why). Facts the design rests on, measured during planning:

- Python checks run only in the PyPI twin; the npm twin forwards its Python section there (`la-typecheck
  --language python`) and relays it unchanged. So the patch is implemented once, in Python.
- The PyPI basedpyright starts Node through `nodejs_wheel` with the inherited environment, so `NODE_OPTIONS`
  reaches it through any wrapper (`uv run`, `poetry run`, a venv script). Its CLI entry `index.js` requires
  `dist/pyright.js`, a CommonJS webpack bundle.
- The bundle embeds basedpyright's own version as the module `"../pyright-internal/src/version.json"`
  (`module.exports = "1.40.2"` in the PyPI 1.40.2 wheel); the sibling `package.json` carries pyright's version
  (`1.1.414`), not basedpyright's. The table is keyed by the embedded basedpyright version.
- The condition occurs exactly once in the 1.40.2 (and 1.39.10) bundle. PyPI and npm 1.40.2 bundles differ
  byte-wise (sha256 `22326090…` vs `c4200771…`).
- A prototype preload that wraps `Module.prototype._compile` and rewrites the condition to `true &&` made the
  minimal repro report its error, also with `--threads 4` across 13 files (unpatched: 0 errors).
- DEV-2140: once patched, storyline's whole project gives identical results with 1, 4 and 32 threads.

Element principles that apply (`architecture/system.arc42.md`): 1 (twins: Python stays PyPI-only, the npm twin
relays it); 2 (the version table and every text come from `shared/`); 3 (language-specific code only in
`lang`: the preload and the basedpyright specifics live in `python.lang`); 4 (no target-repo code runs except the
configured command, and nothing in the target or its environment is modified). The spec stays on the existing
`typecheck` capability owned by `python.typecheck`; no model, view or arc42 edit is needed (the `typecheck ->
lang` arrow exists).

## Goals / Non-Goals

**Goals:**

- Every la repo's Python gate runs a patched basedpyright, through whatever command it configures.
- A run that is not patched can never look green: it exits 2.
- Removing the patch later is deleting the preload, its wiring and its texts.

**Non-Goals:**

- Switching storyline to la and deleting its wrapper (separate repo, after an la release).
- Patching `pyright-langserver.js` or the IDE.
- Detecting an upstream fix: when #11919 ships in basedpyright, the patch is removed (forward pointer in the
  code to microsoft/pyright#11919).
- Pinning `--threads` or the Node heap.
- Releasing or bumping versions: the version rule applies on the bump PR, enforced there by its test and
  `scripts/release-check`.
- A user-facing text for a malformed result file (see decision 13).

## Decisions

1. **Patch in memory through a `NODE_OPTIONS` preload** (user). Alternatives: patch the installed bundle files in
   place, as storyline does (mutates the target's environment, against principle 4; cannot locate the install
   behind an arbitrary wrapper; fails on read-only installs; a reinstall drops it silently), or ship a pinned,
   patched basedpyright in la (a ~40 MB Node wheel for every PyPI-twin user; version drift from the repo and IDE;
   la would have to resolve the repo's Python environment itself; `commands.typecheck.python` stops being a
   command). The preload leaves the target untouched, keeps the configured command the one way the checker runs,
   and is removed by deleting one file. Cost: the IDE's language server stays unpatched.
2. **Exact verified-version table plus the exactly-once check** (user). Alternatives: a pyright version range
   (admits versions nobody ran the repro on) or the exactly-once check alone (patches blindly; cannot tell an
   upstream fix from a refactor). The table is keyed by the bundle's embedded basedpyright version.
3. **The table starts with `1.40.2` only; this repo pins `basedpyright==1.40.2`** in the dev group and the
   `verify` extra, so la passes its own gate and anything la installs is verified (user). A version is added
   after running the minimal repro under the preload.
4. **Strict: no preload result means exit 2** (user). Alternative: run unpatched when the preload never fired
   (silently loses the determinism this change exists for). Consequence: every fake Python checker in the
   conformance corpus records a result.
5. **Threads, heap and checker options stay in the configured command** (user). Alternative: force `--threads 1`
   and a fixed heap, as storyline does (edits the command's arguments, breaks wrappers, slows every repo, and
   guards only against a hypothetical second order-dependent bug; DEV-2140 measured identical results across
   thread counts once patched).
6. **Placement** (default): the preload `.cjs` (package data) and the basedpyright specifics (the environment
   for the run, reading the result) in `python.lang` (`lang/typecheck.py`); `python.typecheck` wires them around
   the Python run. The table is a `python` fact in `shared/languages.yaml`, the texts are in `shared/findings.yaml`.
7. **The preload hard-codes no parameter** (default): la passes it the result-file path and the verified table
   through environment variables. The condition text and its replacement live in the preload (they are the
   patch, not a contract parameter).
8. **Nothing is printed when the patch applied** (default); the goldens of patched runs keep today's output.
9. **Conformance fakes record the preload's result; the real preload is covered by unit and integration tests**
   (default). The conformance runner needs no Node for Python cases.
10. **One writer, written atomically** (codex): every thread patches, only the main thread records the result,
    synchronously, via a temp file and rename, before any `process.exit`. The main thread compiles the bundle
    before any worker starts and all threads compile the same file, so they reach the same outcome; per-thread
    result files and a stress test were rejected as unnecessary.
11. **Fakes prove la set up the preload** (codex): before recording `patched`, each fake asserts `NODE_OPTIONS`
    holds `--require` with la's preload path, the result-file and table variables are set, and, in one case with
    a preset `NODE_OPTIONS`, that the earlier value comes first. Every conformance case that runs a Python fake
    checker is updated, including `typecheck-mixed-*` and `twin-typecheck-*` (codex).
12. **Wheel-content test** (codex): a test builds the wheel and asserts the preload is inside and locatable from
    the installed package. The new `languages.yaml` fact is documented in its header comment, and
    `scripts/sync-shared --check` is part of verification (codex).
13. Rejected (codex): a `typecheck.patch-result-invalid` text. The result file is la's own, written atomically by
    one writer; a malformed one is an la bug, not a user condition.
14. Rejected (codex): binding results to bundle paths and rejecting several bundles in one run. The preload
    ignores non-basedpyright Node processes, and a wrapper that strips `NODE_OPTIONS` is the tested not-applied
    case.
15. Rejected (codex): treating the version bump as in scope. See Non-Goals.
16. Rejected (codex, then user): a sha256 per verified bundle. PyPI and npm builds differ, so each version
    would need one hash per distribution and any other build would be refused; the exactly-once check already
    catches the realistic failure (a bundle patched or edited in place).
17. Approved wording (user, approved wording):
    - `typecheck.patch-not-applied`: "la-typecheck: python: {command} loaded no basedpyright, so the pyright#11919 patch was not applied; run basedpyright under Node and keep NODE_OPTIONS"
    - `typecheck.patch-unverified`: "la-typecheck: python: the pyright#11919 patch is verified for basedpyright {verified}, but {version} is installed; pin a verified version"
    - `typecheck.patch-mismatch`: "la-typecheck: python: basedpyright {version} has the pyright#11919 line {count} times, not once; reinstall basedpyright"

## Risks / Trade-offs

- [The IDE's language server stays unpatched, so the editor can show fewer errors than the gate in this loop
  pattern] → accepted; the gate is the authority.
- [Repos must pin a verified basedpyright and wait for an la release to upgrade] → accepted (decision 2); the
  unverified text says what to do.
- [A future Node or basedpyright moves the bundle to ESM, bypassing `Module.prototype._compile`] → the preload
  never fires, so the run exits 2 with the not-applied text instead of passing unpatched.
- [Storyline's dev venvs hold bundles already patched in place] → the mismatch text tells them to reinstall.
- [A preload path with spaces breaks `NODE_OPTIONS` parsing] → la quotes the path; a unit test covers it.

## Migration Plan

Repos pin `basedpyright` to a verified version (today `1.40.2`) before taking the la release carrying this.
Rollback is the previous la release.
