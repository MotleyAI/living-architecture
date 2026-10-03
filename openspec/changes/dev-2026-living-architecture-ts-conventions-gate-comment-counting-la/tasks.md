## 1. Failing tests (pr-tests stage)

- [x] 1.1 Conventions routing and report cases (conformance, both twins): mixed `[python, typescript]` diff (one verdict, path order across languages, cross-language ratio groups, `.py and TS/JS` label), empty change set (`source` label), explicit unknown-extension warning for `--file` and for `la-count-comments` args, NUL-safe paths (space, non-ASCII, leading dash), deletion, rename across languages. Re-bless with a stated reason only `count-comments-help-is-a-path`, `count-comments-double-dash-is-a-path`, the empty-diff golden and any `--file` case with a non-source extension. Verify they fail now and every other existing golden is untouched.
- [x] 1.2 Facts-protocol cases: facts request for a non-owned language → 2 without spawning, malformed and schema-invalid documents → 2, identity mismatch → 2, relayed setup error, twin unreachable → 2 with the hint, a path list longer than one command line (stdin transport, order kept). Plus `shared/vectors` accept/reject documents for `conventions-facts.schema.json`. Verify they fail now.
- [x] 1.3 TS rule cases (`node/` overlays): every import-not-top bullet of the spec (import after code, `import type` late, `import x = require` late, directive prologue, top-level `require` ending the prologue, `require` in a function and in a top-level `if` block, `export … from` at the bottom, dynamic and type-position `import()`, `declare module` body); composite-assert (`expect`, `assert`, `assert.ok`, parenthesized, `||` not flagged, non-test file); raises-single-throw (each `toThrow*` matcher, `.rejects.*`, `assert.throws`/`assert.rejects`, `new` counted, one call clean, `.not.toThrow`); a waiver per rule incl. a multi-line construct; syntax error; each JS ScriptKind (`.js/.jsx/.mjs/.cjs`) and `.tsx/.mts/.cts`. Verify they fail now.
- [x] 1.4 TS line-set cases: text-ratio exactly at and just over the cap for each group, block comments starting or ending beside code, trailing comments and trailing JSDoc, BOM, CRLF and lone CR, no final newline, invalid UTF-8 → unreadable; `la-count-comments` files, `--range` (TS and mixed), JSDoc vs `/**/` vs `//`, shebang, syntax error still counting comments. Verify they fail now.
- [x] 1.5 `la-typecheck` cases with fake checkers in `.venv/bin` / `node_modules/.bin` (also on `PATH` to prove local-first): applicability (stray JS in a Python repo, explicit entry without markers, `null` off, no applicable language, not a git repo), checker missing → 2, string config → config error, mixed order/headers/exit max, same output from either twin. Python: passthrough clean/new/shrink, write with errors → 0, exit ≥ 2 → 2, a non-basedpyright command's failure mode. TS: unchanged, line shift, new error, count increase listing every occurrence, new + resolved (no shrink), shrink rewrite, write fresh / clean language (empty baseline) / skip existing / all exist → 2, path with spaces and parentheses, continuation lines, diagnostics on either stream, global diagnostic → 2, non-zero exit with nothing parsed → 2, malformed baseline → 2. Verify they fail now.
- [x] 1.6 Shared vectors `command-split.yaml` (quotes, escapes, empty words, unterminated quote → error) consumed by both suites; schema tests for `commands.typecheck` (defaults in `la-config show`, `null`, string rejected); a `twin-forwarding` case: `dr-mock-lint` still forwarded wholesale by the npm twin, conventions commands no longer forwarded. Re-bless the `la-config show` goldens with a stated reason. Verify they fail now.
- [x] 1.7 Unit tests in both twins for the neutral pieces (routing, waiver on carried line text, ratio, labels, applicability, exit combination) and the TS adapter (Vitest); one real-checker test per twin (basedpyright, tsc) in the integration set. Verify they fail now.
- [x] 1.8 Codex review of the tests against the plan (pr-tests Step 2). Verify that the findings are resolved with the user.

## 2. Shared contract

- [x] 2.1 `languages.yaml`: `typescript` gains `markers: [tsconfig.json]`, `files_label: TS/JS`, `comment_prefix: '//'`, `suppression: '// @ts-expect-error — <reason>'`, `local_bin: node_modules/.bin`, `baseline_file: .tsc-baseline.json`; `python` gains `local_bin: .venv/bin`, `baseline_file: .basedpyright/baseline.json`; `type_checker` removed. `conventions.yaml`: `typescript` descriptions for every rule. Verify the registry tests.
- [x] 2.2 `cli.yaml`: `la-typecheck` (`--write-baseline`, internal `--language`), internal `--language`/`--emit facts` on `la-check-conventions` (also serving comment counts), both conventions commands neutral, `la-count-comments` help says doc lines. `schema/living-architecture.schema.json`: `commands.typecheck` map with defaults and the basedpyright-compatibility note. New `schema/conventions-facts.schema.json`, `vectors/command-split.yaml`. `findings.yaml`: TS rule templates, unknown-extension warnings, typecheck header/new-error/count/shrink/write/skip/refusal/not-found/no-languages/not-git templates. Run `scripts/sync-shared`. Verify the drift tests and the manifest/entry-point tests (new `la-typecheck` script and bin).

## 3. PyPI twin

- [x] 3.1 `lang`: conventions facts for Python (existing analysis plus the flagged line text and comment/doc counts); the basedpyright adapter (write flag, exit mapping). Verify the Python unit tests.
- [x] 3.2 `conventions`: NUL-safe diff, routing, facts requests through `twin` (stdin paths), waivers on carried line text, cross-language ratio and labels, unknown-extension warnings, the facts server for `--language python --emit facts`; `la-count-comments` routing and `--range` with raw base bytes. Verify every Python-invoked conventions case from 1.1–1.4.
- [x] 3.3 New `typecheck` node and its `cli` wiring. Verify every Python-invoked case from 1.5–1.6.

## 4. npm twin

- [x] 4.1 `lang`: TS conventions detectors, line sets, decoding, syntax errors, facts; tsc adapter (grammar, both streams, multiset baseline JSON, shrink, write). Verify the Vitest adapter tests.
- [x] 4.2 New `conventions` node (port of the neutral gate and comment counter) and `typecheck` node; `cli` dispatch and bins. Verify every case from 1.1–1.6 through the npm twin and `scripts/conformance-cross`.

## 5. This repo's architecture (every edit presented for the user's per-edit approval)

- [x] 5.1 Present and write `architecture/model/la.c4` per design D9. Verify `npx likec4 validate architecture` and `la-arch-check` from both twins.
- [x] 5.2 Present and write `system.arc42.md` principle 4 as the approved wording (design D7); run `la-arch-diagrams`. Verify `la-arch-check` exits 0 from both twins.

## 6. Docs

- [x] 6.1 `AGENTS.md` (la-typecheck, conventions facts), `README.md` (TS conventions, `la-typecheck`, `commands.typecheck`, BREAKING routing note, `conventions.exempt` advice), `conformance/INVENTORY.md`. Verify `test_skills`, `plugin validate plugin`, and every new findings id covered by a golden.

## 7. Final gates

- [x] 7.1 `python/`: full non-integration suite, `ruff check src tests`, `basedpyright src tests`. `node/`: lint, typecheck, Vitest, conformance. `scripts/conformance-cross`. Verify all green.
- [x] 7.2 `la-check-conventions --base main` clear from both twins; `la-typecheck` on this repo (with `commands.typecheck` set for its layout); `openspec validate dev-2026-living-architecture-ts-conventions-gate-comment-counting-la --strict`; `la-arch-check` exits 0 from both twins.
- [ ] 7.3 (pr-review, at archive time) Map `conventions` on `python.conventions` and `typecheck` on `python.typecheck` in model metadata (exact edit presented for approval). Verify `la-arch-check` exits 0 after `openspec archive`.
