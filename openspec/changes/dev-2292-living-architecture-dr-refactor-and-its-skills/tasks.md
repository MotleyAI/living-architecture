## 0. Tests for the DEV-2289 merge (pr-tests stage, before any implementation)

- [x] 0.1 Failing tests (unit tests in `python/tests/test_rename_strings.py`; a conformance case only where the
      command-level output is new, listed in `conformance/INVENTORY.md`) for the scenarios the merge added to
      "Members named by string are renamed": "Target from tests into a src layout"; "Target through inheritance"
      (inherited, overridden, overridden with `--no-in-hierarchy`, diamond); "Ambiguous targets refuse" (a module
      in two source folders, conflicting bindings, a star import that `__all__` excludes, an import cycle, an
      unresolved base before the attribute), each a `refactor.unresolved-target` blind spot; and a target that
      resolves through a star import honouring `__all__`. Then a Codex review of these tests against the plan.
      Run this stage by naming `pr-tests` when invoking `/la:pr` (detection would pick `pr-implement`).

## 1. Shared contract

- [x] 1.1 `shared/cli.yaml`: add to `dr-refactor rename` the options `--allow-blindspots` (flag), `--with`,
      `--without`, `--keep` (strings, repeatable) and `--docs` (flag); add `prose_extensions: [.md, .rst, .txt]`
      under `dr-refactor`; name `attr-blindspot` in the `dr-compliance` help. Verify with the CLI vector tests in
      both twins.
- [x] 1.2 `shared/findings.yaml`: add `refactor.blindspots`, `refactor.unresolved-target`, `refactor.stand-in`,
      `refactor.not-stand-in`, `refactor.keep-unmatched`, `refactor.leftover`, `compliance.attr-required`,
      `compliance.attr-unselected`. Proposed texts (ids fixed; texts may tighten):
      `'{count} blind spot(s) of .{attr}: type or resolve them, or pass --allow-blindspots'`;
      `'{path}:{line}: unresolved-target: {target} names .{attr} but does not resolve'`;
      `'{path}:{line}: stand-in: {cls}.{attr} is outside the renamed hierarchy; pass --with {path}:{line} to rename
      it too or --without {path}:{line} to leave it'`; `'{site} is not a stand-in of this rename'`;
      `'--keep {site} matches nothing this rename touches'`; `'{path}:{line}: leftover: {where} mentions {old}'`;
      `'--select attr-blindspot needs --attr NAME'`; `'--attr needs attr-blindspot among the selected checks'`.
      Verify every new template is produced by at least one golden (task 8.3).
- [x] 1.3 `shared/languages.yaml`: add `attr-blindspot` to both `compliance_checks` (last; Python's list then
      reads `[untyped-def, unannotated-attr, explicit-any, mock, rope-walk, attr-blindspot]`, design decision 26);
      add `string_member_calls` per
      language (Python: the resolved qualified names of `getattr`, `setattr`, `hasattr`, `delattr`, pytest
      `MonkeyPatch.setattr`/`delattr`, typeshed `unittest.mock` `patch.object` and `patch`, pytest-mock
      `patch.object` and `patch`, each with its syntactic shape and member/target argument position; TypeScript:
      `vi.spyOn`, `jest.spyOn`, `Reflect.get/set/has/deleteProperty/defineProperty/getOwnPropertyDescriptor`,
      `Object.defineProperty/getOwnPropertyDescriptor`); update the header comment. Verify with the registry tests.
- [x] 1.4 Run `scripts/sync-shared`; verify `scripts/sync-shared --check` and the drift tests pass.

## 2. dr-compliance: selectable attr-blindspot, string forms (both twins)

- [x] 2.1 Python: `attr-blindspot` runs iff selected and `--attr` given; `compliance.attr-required` /
      `compliance.attr-unselected` exit 2; default output without `--attr` unchanged. Verify with unit tests and the
      "Selecting attr-blindspot", "attr-blindspot without --attr", "--attr outside the selection" scenarios.
- [x] 2.2 TypeScript: the same in `node/src/refactor/compliance.ts` and the CLI. Verify with Vitest.
- [x] 2.3 Unit test (both twins) pinning that every kind a `compliance.*` template prints, other than
      `parse-error`, is a registry check id.
- [x] 2.4 Python scan: extend the `--attr` scan to the string-member forms (untyped object, or unresolved callee
      with the form's syntax and the literal NAME) as one reusable scan the rename also calls. Verify with the
      "String-member forms on untyped objects" scenario and a lookalike-callee negative test.
- [x] 2.5 TypeScript scan: the same for the TS forms with an `any` object. Verify with the "spyOn on an any
      object" scenario.

## 3. --keep (both twins)

- [x] 3.1 Python: parse and normalize `--keep PATH[:LINE]` (real project-relative paths, directory by whole
      components), drop matching edits after all rules ran, `refactor.keep-unmatched` exit 2. Verify with the
      `--keep` scenarios incl. `tests/compatible.py` vs `tests/compat`, and file + line keep together.
- [x] 3.2 TypeScript: the same. Verify with Vitest.

## 4. Blind-spot refusal (both twins)

- [x] 4.1 Python: classify member renames; run the shared scan over every project source file before printing;
      refuse with sorted `attr-blindspot` / `unresolved-target` lines + `refactor.blindspots`, exit 1, nothing on
      stdout, nothing written; `--allow-blindspots` proceeds; kept lines exempt; non-member renames skip the scan.
      Verify with the "Member renames refuse on untyped receivers" scenarios.
- [x] 4.2 TypeScript: the same with the TS scan. Verify with "TypeScript any receiver" and Vitest.

## 5. Stand-ins and --with / --without (both twins)

- [x] 5.1 Python: compute the full hierarchy (regardless of `--no-in-hierarchy`); find project classes outside it
      declaring OLD (def, property, class or `self.` attribute, field); classify by `PATH:LINE` (every stand-in on
      the line, plus its hierarchy); resolve the joined symbol set first, then run every rule once on one snapshot;
      `refactor.stand-in` refusal, `refactor.not-stand-in` exit 2. Verify with the stand-in scenarios.
- [x] 5.2 TypeScript: hierarchy = the language service's rename declarations (merged interfaces included);
      stand-ins = class / interface / type-literal members named OLD outside it, never object literals; `--with`
      adds that declaration's rename locations to the same edit set. Verify with "TypeScript structural class and
      object literal" and a noise case (several unrelated same-named members, each needing `--without`).

## 6. Members named by string (both twins)

- [x] 6.1 Python receiver forms: rewrite the member literal where the callee resolves to a listed form and the
      object's type (instance, class object, `type[...]`) looks OLD up onto a renamed declaration; quote style kept.
      Verify with "Receiver forms on instances and class objects", "Member of another class" and "Lookalike
      callee", using real pytest and pytest-mock typings.
- [x] 6.2 Shared static resolver (design decisions 27–29): move DEV-2289's scope/binding resolver out of
      `refactor/explicit_any.py` into a shared module of `living_architecture.refactor`, with an injected module
      finder (`explicit-any`: its import-root rule, unchanged; rename: rope's source folders in order, zero or
      several files → unresolved) and values naming project definitions (class/function with location). Gate:
      `tests/test_compliance_explicit_any.py` and every `compliance-explicit-any-*` golden pass unmodified.
- [x] 6.3 Python dotted targets on that resolver: longest project-module prefix, then module bindings ("every
      binding agrees"), then class attributes along the C3 MRO of statically resolved bases; no import or
      execution; rewrite each segment resolving to a renamed declaration (class renames too); a project target not
      resolving to exactly one declaration → `refactor.unresolved-target` blind spot; external target with a
      segment OLD → `leftover`. Verify with "Dotted patch targets", "Class rename segment", "Unresolved targets",
      "Target from tests into a src layout", "Target through inheritance" (incl. a diamond) and "Ambiguous targets
      refuse" (two folders, conflicting bindings, `__all__`-excluded star import, cycle, unresolved base), a target
      through a star import honouring `__all__`, plus a test that a `sitecustomize.py` marker is never written.
      The tests for the scenarios added by the DEV-2289 merge come from task 0.1.
- [x] 6.4 TypeScript forms: rewrite the member literal of the listed calls on a typed object or prototype. Verify
      with "TypeScript spyOn".

## 7. --docs (both twins)

- [x] 7.1 Python: tokenize comments and string literals (docstrings, f-string literal parts) of every project
      source; qualified mentions (prefix must be a suffix of the declaring module path; bare `Owner.OLD` only when
      unambiguous); code-marked bare mentions in declaring files; the rest as sorted `refactor.leftover` lines;
      prose files from `config.source_files` with the shared extensions, qualified only. Verify with the `--docs`
      scenarios.
- [x] 7.2 TypeScript: the same over comments (incl. JSDoc, `Owner#OLD`, `{@link …}`), string and template-literal
      text, and the same prose files via `sourceFiles`. Verify with "TypeScript JSDoc link" and Vitest.
- [x] 7.3 Both: a mention another rule rewrote is not listed; without `--docs` nothing is scanned or listed.
      Verify with "Without --docs" and "Comments and messages untouched by default".

## 8. Conformance corpus

- [x] 8.1 One adapter case per language (`refactor-rename-*` / `refactor-ts-rename-*`, the corpus's convention for
      `dr-refactor`) under `conformance/cases/` for: blind-spot refusal and
      `--allow-blindspots`; both refusals under `--apply` (tree unchanged); stand-in refusal, `--with`,
      `--without`, same-line classification, `not-stand-in`; string-member forms; `--keep` (line, file, directory,
      unmatched); `--docs` (qualified, code-marked, leftovers, prose, collision); paired cases for `dr-compliance
      --select attr-blindspot` and both usage errors. Python-only adapter cases for dotted targets.
- [x] 8.2 List every new case in `conformance/INVENTORY.md`.
- [x] 8.3 Verify every new findings template is produced by a golden and each case passes through both invoking
      twins (`scripts/conformance-cross`).

## 9. Skills and docs

- [x] 9.1 Apply design.md "Approved wording" verbatim to `plugin/skills/deterministic-refactor/SKILL.md`,
      `plugin/skills/make-refactor-target-compliant/SKILL.md`, `plugin/languages/python.md`,
      `plugin/languages/typescript.md`. Verify `npx -y @anthropic-ai/claude-code plugin validate plugin`.
- [x] 9.2 `docs/deterministic-refactoring.md`: append `attr-blindspot` to both rows of the `dr-compliance` table
      (the Python row already lists `explicit-any` from DEV-2289) and name the new
      `rename` options in the tools paragraph; `docs/commands.md` likewise if it lists `rename` options. Verify the
      docs build/link checks the repo runs.

## 10. Verification

- [x] 10.1 Local test scope green in both twins; `ruff`, `basedpyright`, `npm run lint && npm run typecheck`,
      `la-arch-check` and `la-typecheck` pass; no existing golden changed except where a scenario above says so.
- [x] 10.2 From this checkout, dry-run on SLayer's DEV-1607 branch: a storage method rename with untyped fixtures
      (expect the blind-spot refusal), `_ModelReadCache` (expect a stand-in), a
      `patch.object(SlayerQueryEngine, "save_model")` site, and `--docs` on a method with ``` ``get_model`` ```
      mentions; record the blind-spot scan's wall time here.
      Done on `86f9c538^` (SLayer venv of the DEV-1607 worktree): `StorageBackend.get_model` refuses with 206
      untyped receivers and 6 stand-ins (`_ModelReadCache`, `SlayerClient`, four test fakes), 33.6 s wall for the
      whole dry-run; `StorageBackend.save_model` with `--docs --allow-blindspots --without` the one stand-in
      rewrites the `monkeypatch.setattr` strings and ``` ``save_model`` ``` mentions, lists 109 leftovers, 41.4 s;
      no `patch.object(SlayerQueryEngine, "save_model")` exists on the branch, so the class-object form was checked
      on `patch.object(SlayerQueryEngine, "_side_stats", …)`, which is rewritten.

## 11. DEV-2289 merge (design decisions 25–34)

- [x] 11.1 Merge `origin/egor/dev-2289-living-architecture-python-dr-compliance-gets` into this branch; resolve the
      `CONTRACT_HASH` conflicts with `scripts/sync-shared`; align the Python check-list pins in
      `python/tests/test_contract.py` and `python/tests/test_compliance.py`.
- [x] 11.2 After implementation, merge verification (decision 33): `scripts/sync-shared --check`; both twins'
      contract, snapshot and render tests; `compliance-help`, `compliance-select-other-language-check` and every
      `compliance-explicit-any-*` case through both invoking twins (`scripts/conformance-cross`); the
      findings-coverage test.
- [ ] 11.3 Before archiving (hard precondition, decision 34): `main` holds DEV-2289 archived and
      `openspec/changes/dev-2289-living-architecture-python-dr-compliance-gets/` is gone; merge `main`; read
      `openspec/specs/refactor/spec.md`; `openspec validate dev-2292-living-architecture-dr-refactor-and-its-skills
      --strict`; after archiving, the "Compliance check sets are per language" requirement in the corpus lists both
      `explicit-any` and `attr-blindspot` for Python and keeps the "Python explicit-any compliance check"
      requirement.

## 13. Review-round causes (design decisions 35–41)

- [ ] 13.1 Outcomes (decision 35): Python `_string_member_edits`, `_target_edit`, `_blindspot_scan`,
      `_mention_edits`, `_keep` and TypeScript `scan`, `formCall`, `classify`, `docs`, `keep` return one outcome per
      examined site; module renames share `--keep` and edit emission. Verify with a unit test per rule asserting
      every branch yields an outcome, and every existing conformance case unmodified.
- [ ] 13.2 Exact OLD literals (decision 36), both twins: cases `refactor-rename-exact-literal` and
      `refactor-ts-rename-exact-literal` in `conformance/INVENTORY.md`, a function rename listing nothing. Verify
      with "Exact string literal listed without --docs".
- [ ] 13.3 TypeScript membership (decision 37): the spike, then the checker-based stand-in index. Verify with the
      parameter-property, quoted and merged/type-literal cases unmodified, plus a constant computed name.
      Spike done (2026-11-14, TypeScript in `node/node_modules`): `checker.getTypeAtLocation(owner).getProperty(OLD)`
      returns the declarations for classes (parameter properties, quoted and constant computed names, accessors),
      merged interfaces and type literals. Three things to handle: it also returns inherited declarations, so keep
      only those whose parent is the owner (a parameter property's parent chain ends at its class); static members
      are on the class symbol's `exports`, not the instance type; `#private` names are not reachable through
      `getProperty` and stay on the syntax path. Object literals also answer `getProperty`, so the owner kinds stay
      class, interface and type literal.
- [ ] 13.4 Python membership (decision 37): the `symtable` cross-check test and its fixes; a callee unit test for a
      form resolved under any spelling, a lookalike, and an unresolved callee with the form's syntax.
- [ ] 13.5 Shared vectors and one line index per twin (decision 38). Verify with the vectors in both twins, and
      stand-in and finding lines agreeing on a CR-only TypeScript file.
- [ ] 13.6 One file universe per twin (decision 39). Verify per twin: with a file outside the tsconfig `include` /
      rope's default set, the rename's blind-spot lines equal `dr-compliance --select attr-blindspot --attr OLD
      <project>` plus the unresolved and mixed targets.
- [ ] 13.7 Probe object (decision 40). Verify with calls in arbitrary order, a declaration before, between and after
      replaced literals, and a definition in another file.
- [ ] 13.8 Local gates, then one Codex pass with decision 41's brief; push once; reply to CodeRabbit r4575115899
      and r4575115901.
- [ ] 13.9 Python `excluded_dirs` (decision 42): `shared/languages.yaml`, `scripts/sync-shared`, both twins'
      registry pins; the rename's candidate files from the routing expansion. Verify with "Virtualenv skipped by
      both": cases `refactor-rename-venv-skipped` and `compliance-attr-venv-skipped` in `conformance/INVENTORY.md`.
- [ ] 13.10 `refactor.computed-stand-in` (decision 43): `shared/findings.yaml`
      (`'{path}:{line}: computed-stand-in: {cls}.{attr} is declared by a computed name; pass --without {path}:{line}
      and rename it by hand'`; after a hand rename the class no longer declares OLD, so the flag comes first), sync, the TypeScript twin. Verify with "Computed-name stand-in": case
      `refactor-ts-rename-computed-stand-in` (refusal, `--without`, `--with` exit 2) in `conformance/INVENTORY.md`.
- [ ] 13.11 Decisions 44–45, tests only unless one fails: a unit test and a `--docs` case row for a patch target
      resolving to a `--without` stand-in (unchanged, unlisted, with and without `--docs`); a Vitest case for a
      `--docs` qualifier spelled with the full project-relative path (`src.pkg.engine.Owner.OLD`, rewritten).

## 14. Post-merge (after the PR merges; not part of its diff)

- [ ] 14.1 Release 0.9.0: bump `python/pyproject.toml`, `node/package.json` and
      `plugin/.claude-plugin/plugin.json` together, run `scripts/release-check`, publish.
- [ ] 14.2 Pin 0.9.0 in SLayer; DEV-2292 stays open until the pin lands.
