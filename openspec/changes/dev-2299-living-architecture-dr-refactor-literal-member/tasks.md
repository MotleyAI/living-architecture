## 0. Order and notes

- [ ] 0.1 Build the timings first (sections 2.1–2.3 before 2.4–2.6), per DEV-2299, so the speed-up is measured with
      them. Verify: commit order.
- [ ] 0.2 Docs and skill wording (task 2.8) is shown to the user verbatim and applied only after their OK.

## 1. Tests (pr-tests)

- [x] 1.1 `shared/`: `refactor.timing: 'timing: {phase} {seconds}s'` in `findings.yaml`; in `cli.yaml` the top-level
      `dr-refactor` option `{name: --timings, type: flag, help: ...}` and the ordered `timing_phases` list (design
      `--timings`), with a header comment like `literal_value_forbidden`'s; `scripts/sync-shared`. Verify:
      `scripts/sync-shared --check` and the drift tests pass.
- [x] 1.2 Python unit tests for the timer (new module in `refactor`): exclusive nesting (a nested phase's time is
      subtracted from its parent), repeated runs summed, list order, phases that never ran omitted, `total` last,
      flooring from injected nanoseconds (1.239 s → `1.23`, 0.004 s → `0.00`, negative → `0.00`). Verify: fail before
      the module exists.
- [x] 1.3 The same timer tests in the npm twin (Vitest), from the same injected integers. Verify: fail before the
      module exists.
- [x] 1.4 Python unit tests for the reverse closure in `lang/edges.py`: absolute, relative (`from . import x`, `from
      .. import`), `from pkg import *` reaching every direct submodule, imports under `TYPE_CHECKING`, inside
      functions and classes, conditional; a chain that reaches the target only through `x.pyi` and through
      `pkg/__init__.pyi`; a `<name>-stubs` directory; a namespace package; a project `__builtins__.pyi` reached from
      every file; a file that does not parse read lexically; a file that does not reach the target is excluded; parsed
      trees passed in are not re-read. Plus a test that `dependency_edges` output for `.py`-only inputs is unchanged.
      Verify: fail before the change.
- [x] 1.5 Python probe spy tests (`tests/test_literal_rename.py` style, real language server): a module that reaches
      nothing and holds no equal string is never opened nor pulled; `before` is pulled only for files a round shows a
      severity-1/2 diagnostic, after the round reverted; cases for a pre-existing error on the same span with the same
      code and with a different code, an error away from the literal, reveal-only results, a diagnostic in a different
      file; an equal string in a file outside the closure is still typed-round probed and classified as today. Verify:
      fail before the change (except the classification ones, which pin today's output).
- [x] 1.6 Conformance `refactor-literal-import-routes` (adapter, Python, `golden: manual`): one file per route of the
      spec scenario "Every import route carries the type" passing `"edit_model"` to a `DriftKind` parameter (all
      rewritten), plus a file outside the member's reach holding `s: str = "edit_model"` (leftover), exit 0; and
      `refactor-literal-import-routes-blindspot` on the same fixture plus `DEFAULT: Final = "edit_model"` passed from
      a file without the string through a re-export chain (blind spot, exit 1 refusal). Hand-written goldens. Verify:
      passes today (pins current output) and stays green after 2.6.
- [x] 1.7 Conformance `--timings` cases, each normalizing `\d+\.\d\ds` to `<S>s`: `refactor-timings-python` (adapter,
      a Python rename), `refactor-timings-typescript` (adapter, a TS rename), `refactor-timings-literal` (Python
      `Literal` rename: `literal-scan`, `literal-probe`), `refactor-timings-refusal` (a member rename refusing on a blind
      spot, exit 1, timing lines after the refusal), `refactor-timings-forwarded` (`twin: typescript`, a Python input:
      only the Python twin's lines), `refactor-timings-map-error` (a mixed-language map: only `total`, exit 2),
      `refactor-timings-missing-twin` (the other twin unavailable: only `total`), `refactor-timings-baseline-failed`
      (the configured checker fails: `baseline` timed, exit as today). `golden: manual`; list each in
      `conformance/INVENTORY.md` and the `refactor.timing` template as produced. Verify: fail before 2.2/2.3.
- [x] 1.8 Codex review of the tests against this plan (`reviewers.codex`). Verify: findings resolved with the user.

## 2. Implementation (pr-implement)

- [x] 2.1 Python timer module in `refactor` and the contract accessor for `timing_phases`; npm timer module in
      `refactor` and its accessor. Verify: 1.2 and 1.3 pass.
- [x] 2.2 Python `dr-refactor`: parse `--timings`, open the scope after parsing and print in a top-level `finally`
      around routing, forwarding, native work and error translation; wrap the phases per design (`load`, `resolve`,
      `references`, `rules`, `blindspot-scan`, `literal-scan`, `literal-probe`, `baseline`, `write`) in
      `rename_map.py`, `rope_refactor.py`, `rename_union.py`, `literal_rename.py`, `baseline_align.py` call sites and
      the writer. A forwarded run prints nothing of its own. Verify: the Python `--timings` cases of 1.7 pass.
- [x] 2.3 npm `dr-refactor`: the same in `refactor/index.ts` (scope around `runRefactor`), `typescript.ts`,
      `rename.ts`, `session.ts`, `baseline.ts`; the first build of each program inside `load`. Verify: the TS
      `--timings` cases of 1.7 pass; `npm run build && npm run conformance` on them.
- [ ] 2.4 `lang/edges.py`: extension-aware resolution (`.pyi`, both initializers, relative into stubs, `-stubs`
      directories), star-import submodules, `__builtins__.pyi`, and the reverse-closure function taking parsed trees.
      Verify: 1.4 passes; the `la-affected-tests` corpus is unchanged.
- [ ] 2.5 `LiteralRename.prepare`: candidates = closure ∪ equal-string files, the closure built from the scan's trees
      over every `.py`/`.pyi` outside `excluded_dirs`, only `.py` files as candidates. Verify: 1.5's candidate tests
      pass.
- [ ] 2.6 `LiteralRename.rules`: lazy cached `before` per design; typed round over every equal-string file, verify
      over every candidate. Verify: 1.5 and 1.6 pass, every `refactor-literal-*` case unchanged.
- [ ] 2.7 Acceptance: every existing `refactor-literal-*` and `refactor-map-literal-*` case through
      `scripts/conformance-cross` byte-for-byte without `--timings`; then the local test scope per `/la:pr`,
      `uv run ruff check src tests`, `uv run basedpyright src tests`, `npm run lint && npm run typecheck`,
      `la-arch-check`. Verify: all green.
- [ ] 2.8 Mention `--timings` in `docs/deterministic-refactoring.md` and `plugin/skills/deterministic-refactor/SKILL.md`
      (wording approved by the user first, per 0.2). Verify: the plugin validates
      (`npx -y @anthropic-ai/claude-code plugin validate plugin`).

## 3. Verification on SLayer (dry run only)

- [ ] 3.1 Reinstall the la tools editable from this checkout; in SLayer's DEV-1607 worktree run
      `dr-refactor --timings rename --file slayer/live_schema/schema_drift.py --line 112 --col 24 --new-name
      edit_model_x` (dry run). Compare stdout and stderr (timing lines aside) with the same run on `main`'s tools:
      identical. Nothing is written to the SLayer checkout.
- [ ] 3.2 Record on DEV-2299 as a Linear comment: the phase lines, the total, and the baseline (89 s on this machine
      before the change; 110.47 s in DEV-2295 task 12.2).
