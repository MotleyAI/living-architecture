## 1. Shared contract

- [x] 1.1 `shared/cli.yaml`: `native: [python, typescript]` on `dr-refactor`, `dr-compliance`, `dr-mock-lint`; drop the `--select` default; verify `scripts/sync-shared --check` passes after sync
- [x] 1.2 `shared/languages.yaml`: `compliance_checks`, `declaration_globs` (`**/*.d.ts`, `**/*.d.mts`, `**/*.d.cts`) and `excluded_dirs` (`node_modules`) per language; verify the snapshot drift tests pass
- [x] 1.3 `shared/findings.yaml`: TS refactor headers and errors (cross-language dest, unsupported extension, outside project, out-of-range position, not supported for TypeScript, cannot rename, not movable, conflicting edits, destination collision), compliance `tsconfig` / `explicit-any` / TS `untyped-def`, mock-lint `fn` / `module` / `cast`, skipped-file warning, `la-config` languages outside git; verify every new id is produced by a golden (registry-coverage test)
- [x] 1.4 `shared/vectors/diff.yaml` (no final newline, CRLF, created and deleted files, spaces and non-ASCII paths) and `shared/vectors/skill-leaks.yaml` (per-language tokens); verify both suites load them

## 2. Tests first (pr-tests stage)

- [x] 2.1 Conformance cases, inventoried by behaviour branch in `conformance/INVENTORY.md`: every scenario of the `refactor` spec (TS adapter cases for rename, move-symbol, move-module, locators, unsupported flags, library symbol, project references with differing options, collisions, compliance checks, mock-lint rules) and the routing branches (mixed blocks, directory expansion by repo languages, declaration skip, cross-language dest, PyPI twin forwarding `.ts`, cwd from a subdirectory, `LA_FORWARDED` refusal, twin unavailable, non-zero and signal relayed, exit max, unknown extension); verify they fail before implementation
- [x] 2.2 Neutral cases for `la-config get languages` / `lang.<language>.<key>` (every public key, an internal key refused, outside git) and `la-doctor` (TS repo without `node`/`npx`, Python repo unchanged); verify they fail before implementation
- [x] 2.3 Diff-vector tests in both suites (Python against difflib, Node against its formatter); verify the Node one fails before implementation
- [x] 2.4 Skills tests: leak list and `la-config get` key validity in `python/tests/test_skills.py` and new `node/test/skills.test.ts`; verify they fail on today's skills
- [x] 2.5 Unit tests for repo languages in both suites (stray script, typecheck `null` keeps the language, explicit entry forces it); verify they fail before implementation

## 3. Repo languages, la-config, la-doctor (both twins)

- [x] 3.1 Move the repo-languages definition into `config`; `la-typecheck` uses it minus `null` entries; verify every existing typecheck golden is unchanged
- [x] 3.2 `la-config get languages` and `lang.<language>.<key>` with the curated keys; verify the 2.2 cases pass through both twins
- [x] 3.3 `la-doctor` requires `node`/`npx` when TypeScript is a repo language; verify the 2.2 doctor cases pass

## 4. Routing (both twins' `refactor` nodes)

- [x] 4.1 Route `dr-refactor` by `--file`/`--module` language, forwarding wholesale with cwd preserved; verify the routing cases pass through both twins
- [x] 4.2 Split, expand and merge for `dr-compliance` / `dr-mock-lint`: captured other-twin output, registry-order blocks, exit max, all-or-nothing on failure; verify mixed cases are byte-identical from both invoking twins
- [x] 4.3 `--select` without a manifest default: absent = all checks per language, unknown id exit 2; verify every existing Python compliance golden is unchanged

## 5. TypeScript dr-refactor (npm `src/refactor`)

- [x] 5.1 Program loading: one LanguageService per project in the reference graph (reusing `lang/projects.ts`), owning project by preorder; verify the project-reference cases pass
- [x] 5.2 Locators: code-point line/col/offset, bounds, `--name`; verify the locator cases pass
- [x] 5.3 `rename` with merge and conflict detection, unsupported flags, cannot-rename mapping; verify the rename cases pass
- [x] 5.4 `move-symbol` via "Move to file" and `move-module` (file or directory); verify the move cases pass
- [x] 5.5 Compute-validate-write and the diff formatter; verify the diff vectors and collision cases pass and a dry-run writes nothing

## 6. TypeScript dr-compliance and dr-mock-lint

- [x] 6.1 `tsconfig`, `explicit-any`, checker-based `untyped-def`, `--attr`; verify the compliance cases pass
- [x] 6.2 Mock lint `fn`, `module` (typed forms, unresolved import), `cast` in test globs, checker-resolved receivers; verify the mock-lint cases pass

## 7. Architecture model (each edit needs the user's explicit OK first)

- [x] 7.1 Add `typescript.refactor` (`src/refactor`) and arrows `cli → refactor`, `refactor → contract`, `refactor → lang`, `refactor → config`, `refactor → twin`; add `python.refactor → config`, `python.refactor → twin`; verify `la-arch-check` is green
- [x] 7.2 Regenerate the `system.arc42.md` diagrams with `la-arch-diagrams`; verify `diagrams-fresh` passes

## 8. Skills and docs (show the exact skill wording to the user before each skill edit)

- [x] 8.1 Write `plugin/languages/python.md` and `plugin/languages/typescript.md` (test, mock, override, type-only import, env, formatter, string-only references, suppression and baseline idioms); verify `npx -y @anthropic-ai/claude-code plugin validate plugin` passes
- [x] 8.2 Rewrite every skill with a language idiom to use `la-config get languages` / `lang.<language>.<key>` and the language docs; the refactor gate becomes `la-typecheck` + `dr-mock-lint` + `commands.test`; verify the 2.4 skills tests pass
- [x] 8.3 `arch-init` and `living-architecture` skills: language-neutral wording; the CI snippet in `uvx` and `npx` forms (`actions/setup-node` pinned by SHA); verify the leak test passes
- [x] 8.4 README: two twins, install per ecosystem, prerequisites per language, TS `index.yaml` shape and multi-language form, CI snippets, Deterministic refactoring for both languages; AGENTS.md: forwarding paragraph rewritten; verify `scripts/sync-shared --check` passes (vendored README)

## 9. Node-only acceptance

- [x] 9.1 In-repo TS fixture repo (several nodes, an import cycle, tests with Vitest, one violation per TS compliance and mock rule) and `scripts/acceptance-node-only`: PATH trap for `python`, `python3`, `uv`, `uvx`; packed twin installed into an isolated prefix with resolved bin paths asserted; `la-doctor`, `la-config get languages`, `la-arch-scaffold`, then `la-arch-check` green, `la-typecheck --write-baseline` then `la-typecheck`, `npx likec4 validate`, `la-check-conventions --base`, `la-count-comments`, the compliance and mock findings then their fixes, dry-run and `--apply` of all three refactors, then `la-typecheck` and Vitest green; verify the trap log is empty and the script exits 0 locally under docker
- [ ] 9.2 CI job running it in a `node:22-slim` container; verify the job is green on the PR

## 10. Release

- [x] 10.1 Version 0.3.0 in `python/pyproject.toml`, `node/package.json` (no longer `private`), `plugin/.claude-plugin/plugin.json`, and README; verify the version tests pass
- [x] 10.2 Full suites: `uv run pytest -q`, ruff, basedpyright in `python/`; `npm run lint && npm run typecheck && npm test && npm run build && npm run conformance` in `node/`; `scripts/conformance-cross`; `la-arch-check`; verify all green

## 11. Manual acceptance on worktree-term (pr-review stage, before merge)

- [ ] 11.1 Once worktree-term has its daemon skeleton: install this branch's twins (`uv tool install -e python`, `npm install -g ./node` after build) and point `~/.claude/skills/la` at this branch's `plugin/`; run `/la:arch-init` on worktree-term until `la-arch-check`, `likec4 validate` and `la-typecheck` are green; fix every gap found in this PR
- [ ] 11.2 Take worktree-term's next change through all four `/la:pr` stages with Vitest as `commands.test`; fix every gap found in this PR; merge this PR only after it passes
