Before writing code, read `architecture/system.arc42.md` (principles P2, P3, P4), `architecture/model.c4` and
design.md. Everything stays in `python.refactor`; no new import edge is allowed. Any arc42 or model edit needs
the user's OK on the exact wording.

Gotcha: `uv run --python 3.11 …` in `python/` replaces the project's `.venv` (default 3.14). To try another
Python, use `UV_PROJECT_ENVIRONMENT=$TMPDIR/venv-3.11 uv run --python 3.11 …`. If `.venv` was replaced, restore
it with `uv sync --python 3.14`.

## 1. Tests first (pr-tests)

- [x] 1.1 `python/tests/test_rope_patches.py`: the checked-in grammar corpus (design D9). It holds every repro
  from the spec, the tracker issue and design D8, plus the edge cases:
  - `lambda` with posonly, kw-only and defaults;
  - PEP 695 bounds and defaults (skip below 3.12);
  - nested f-strings, and `=`, `!r` and format specs;
  - triple-quoted and multi-piece concatenations;
  - a comment or backslash between pieces;
  - non-ASCII before and inside annotations, strings, f-strings and t-strings;
  - `rb`/`Rb`/`bR` prefixes;
  - class keywords and try/except/else/finally;
  - t-strings (skip below 3.14).

  Each case asserts the D1 invariant and `write_ast(tree) == source`. Verify: they fail before the patches.
- [x] 1.2 One subprocess canary per gap (design D2). Each asserts that unpatched rope still crashes on its
  repro or violates D1. Verify: each canary passes today.
- [x] 1.3 Test that `apply_rope_patches()` resets a primed `_Source._string_pattern` cache. Verify: it fails
  before the patch.
- [x] 1.4 Stdlib sweep and this-repo sweep (design D9) in the default suite. Verify: they fail before the patches.
- [x] 1.5 Localization unit tests (design D3), with one original rope visitor restored by monkeypatch:
  - the first-violation line after a crash (annotation gap: the annotation's line, not the drift line);
  - a silent gap (the string tail);
  - the top-level-statement fallback;
  - a clean module gives `None`.
- [x] 1.6 Guard tests through `run_refactor` / the real `Rename` path (design D4):
  - `refactor.rope-walk` text, path and line on stderr, exit 1, empty stdout;
  - the tree is unchanged with `--apply`;
  - a non-walker exception (also one raised in our own patch code) propagates.
- [x] 1.7 Dry-run writes nothing: the Python refactor test asserts no `.ropeproject` after a dry-run and after
  `--apply`. Every existing Python refactor conformance case lists `.ropeproject/history.json` in `expect.files`
  with a `files/.ropeproject/history.json` golden of `<MISSING>`. Verify: they fail before the fix.
- [x] 1.8 `python/tests/test_compliance.py` for `rope-walk`:
  - a clean file passes;
  - a gap file (monkeypatched) gets one finding at the D3 line;
  - parse-error precedence;
  - `rope-walk` runs by default and `--select rope-walk` selects it.
- [x] 1.9 `test_contract.py`:
  - `NEW_TEMPLATES` entries for both templates, with the exact design D7 wording;
  - both IDs in `UNPRODUCED_BY_DESIGN`, with the reason "no known input reaches a walker gap; pinned by the
    rope-walk unit tests".
- [x] 1.10 Conformance (hand-written goldens, `golden: manual`). List each in `conformance/INVENTORY.md`.
  - `compliance-rope-walk-clean` (adapter, Python): a fixture with every formerly failing construct that
    parses on 3.11; exit 0, empty stdout.
  - A neutral `dr-compliance --select rope-walk web/a.ts` case: exit 0, nothing printed, through both twins.
  - A Python `dr-refactor` rename on the annotated-parameter / f-string-concatenation fixture: its diff and
    exit 0.

## 2. Shared contract

- [x] 2.1 `shared/findings.yaml`: add `compliance.rope-walk` and `refactor.rope-walk` (design D7 wording).
- [x] 2.2 `shared/languages.yaml`: Python `compliance_checks: [untyped-def, unannotated-attr, mock, rope-walk]`.
- [x] 2.3 `shared/cli.yaml`: the dr-compliance help lists `rope-walk` among Python's checks. Re-bless the
  `compliance-help` golden with `LA_UPDATE_GOLDENS=1`; the commit message states the reason (a deliberate
  help change).
- [x] 2.4 Run `scripts/sync-shared`. Verify: `scripts/sync-shared --check` exits 0 and the drift tests pass.

## 3. Python implementation

- [x] 3.1 `refactor/rope_patches.py`: the invariant, character offsets and violations (design D1), and every
  walker patch (design D2), including the pattern cache reset. Fix the stale "rope <= 1.14" docstring; keep
  docstrings concise. Verify: 1.1–1.4 pass.
- [x] 3.2 `walk_gap_line` (design D3) and the `GlobalScope._calculate_scope_regions` guard raising
  `WalkerGap` (design D4), with narrow exception translation. Verify: 1.5 passes.
- [x] 3.3 `refactor/rope_refactor.py`: `Project(..., ropefolder=None)`; catch `WalkerGap` and print
  `refactor.rope-walk`, exit 1. Verify: 1.6, 1.7 and the existing refactor conformance goldens pass unchanged.
- [x] 3.4 `refactor/compliance.py`: the `rope-walk` check (design D5); update the module docstring's check
  list. Verify: 1.8 passes, and the existing compliance goldens are unchanged.

## 4. Docs, CI, versions

- [x] 4.1 `docs/deterministic-refactoring.md`: the Python row of the checks table lists `rope-walk`.
- [x] 4.2 `plugin/languages/python.md`, under "Compliance fixes", add exactly this line (user-approved):
  `` - `rope-walk` → rope cannot walk this construct, so `dr-refactor` refuses the file. It is a rope bug, not a source error: report it with the named line; rewriting the construct is only a stopgap. ``
- [x] 4.3 `.github/workflows/ci.yml`: add `"3.14"` to the Python matrix. Verify: the full Python suite passes
  locally on 3.11 and 3.14 (see the gotcha above).
- [x] 4.4 Bump to 0.3.3, mirroring commit 5d9752e:
  - `python/pyproject.toml` and `python/uv.lock`;
  - `node/package.json` and `node/package-lock.json`;
  - `plugin/.claude-plugin/plugin.json`;
  - the version mentions in `README.md`, `python/README.md`, `node/README.md` and `docs/commands.md`.

  Verify: `scripts/sync-shared --check`, and `la-doctor --contract-hash` agrees in both twins.

## 5. Full verification

- [x] 5.1 Python: `uv run pytest -q`, `uv run ruff check src tests` and `uv run basedpyright src tests` are
  green. npm: `npm run lint && npm run typecheck`, `npm test`, `npm run build && npm run conformance`.
  Repo-wide: `scripts/conformance-cross`, `la-arch-check`.
- [x] 5.2 Manual acceptance. Use the SLayer checkout at `/home/james/GitHub/SLayer/slayer`; it is read-only in
  the sandbox, and a dry-run must not need to write.
  - Walk every `git ls-files '*.py'` file: all 1,222 pass `dr-compliance --select rope-walk`.
  - `dr-refactor --project /home/james/GitHub/SLayer/slayer rename --file slayer/core/keys.py --line 326 --col 5 --new-name source`
    prints a diff, exits 0 and leaves no `.ropeproject`.

  Record the results in a Linear handoff comment on DEV-2130.

## 6. Upstream (pr-implement, only after the user's explicit go-ahead)

- [x] 6.1 File design D8's two issues with `gh issue create -R python-rope/rope`. Put each URL in its canaries'
  comments as a forward pointer ("drop this patch when <url> is fixed").

## 7. After merge (the user)

- [x] ~~7.1 Publish the 0.3.3 GitHub release (`publish.yml` runs the release check).~~ Post-merge, tracked on DEV-2130.
- [x] ~~7.2 SLayer bumps its pinned `living-architecture` to 0.3.3 under DEV-2119. DEV-2130 closes only on the
  user's call.~~ Post-merge, moved to DEV-2119.
