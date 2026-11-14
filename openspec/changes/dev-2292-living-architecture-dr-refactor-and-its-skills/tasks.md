## 0. Tests for the DEV-2289 merge (pr-tests stage, before any implementation)

- [ ] 0.1 Failing tests (unit tests in `python/tests/test_rename_strings.py`; a conformance case only where the
      command-level output is new, listed in `conformance/INVENTORY.md`) for the scenarios the merge added to
      "Members named by string are renamed": "Target from tests into a src layout"; "Target through inheritance"
      (inherited, overridden, overridden with `--no-in-hierarchy`, diamond); "Ambiguous targets refuse" (a module
      in two source folders, conflicting bindings, a star import that `__all__` excludes, an import cycle, an
      unresolved base before the attribute), each a `refactor.unresolved-target` blind spot; and a target that
      resolves through a star import honouring `__all__`. Then a Codex review of these tests against the plan.
      Run this stage by naming `pr-tests` when invoking `/la:pr` (detection would pick `pr-implement`).

## 1. Shared contract

- [ ] 1.1 `shared/cli.yaml`: add to `dr-refactor rename` the options `--allow-blindspots` (flag), `--with`,
      `--without`, `--keep` (strings, repeatable) and `--docs` (flag); add `prose_extensions: [.md, .rst, .txt]`
      under `dr-refactor`; name `attr-blindspot` in the `dr-compliance` help. Verify with the CLI vector tests in
      both twins.
- [ ] 1.2 `shared/findings.yaml`: add `refactor.blindspots`, `refactor.unresolved-target`, `refactor.stand-in`,
      `refactor.not-stand-in`, `refactor.keep-unmatched`, `refactor.leftover`, `compliance.attr-required`,
      `compliance.attr-unselected`. Proposed texts (ids fixed; texts may tighten):
      `'{count} untyped receiver(s) of .{attr}: type them, or pass --allow-blindspots'`;
      `'{path}:{line}: unresolved-target: {target} names .{attr} but does not resolve'`;
      `'{path}:{line}: stand-in: {cls}.{attr} is outside the renamed hierarchy; pass --with {path}:{line} to rename
      it too or --without {path}:{line} to leave it'`; `'{site} is not a stand-in of this rename'`;
      `'--keep {site} matches nothing this rename touches'`; `'{path}:{line}: leftover: {where} mentions {old}'`;
      `'--select attr-blindspot needs --attr NAME'`; `'--attr needs attr-blindspot among the selected checks'`.
      Verify every new template is produced by at least one golden (task 8.3).
- [ ] 1.3 `shared/languages.yaml`: add `attr-blindspot` to both `compliance_checks` (last; Python's list then
      reads `[untyped-def, unannotated-attr, explicit-any, mock, rope-walk, attr-blindspot]`, design decision 26);
      add `string_member_calls` per
      language (Python: the resolved qualified names of `getattr`, `setattr`, `hasattr`, `delattr`, pytest
      `MonkeyPatch.setattr`/`delattr`, typeshed `unittest.mock` `patch.object` and `patch`, pytest-mock
      `patch.object` and `patch`, each with its syntactic shape and member/target argument position; TypeScript:
      `vi.spyOn`, `jest.spyOn`, `Reflect.get/set/has/deleteProperty/defineProperty/getOwnPropertyDescriptor`,
      `Object.defineProperty/getOwnPropertyDescriptor`); update the header comment. Verify with the registry tests.
- [ ] 1.4 Run `scripts/sync-shared`; verify `scripts/sync-shared --check` and the drift tests pass.

## 2. dr-compliance: selectable attr-blindspot, string forms (both twins)

- [ ] 2.1 Python: `attr-blindspot` runs iff selected and `--attr` given; `compliance.attr-required` /
      `compliance.attr-unselected` exit 2; default output without `--attr` unchanged. Verify with unit tests and the
      "Selecting attr-blindspot", "attr-blindspot without --attr", "--attr outside the selection" scenarios.
- [ ] 2.2 TypeScript: the same in `node/src/refactor/compliance.ts` and the CLI. Verify with Vitest.
- [ ] 2.3 Unit test (both twins) pinning that every kind a `compliance.*` template prints, other than
      `parse-error`, is a registry check id.
- [ ] 2.4 Python scan: extend the `--attr` scan to the string-member forms (untyped object, or unresolved callee
      with the form's syntax and the literal NAME) as one reusable scan the rename also calls. Verify with the
      "String-member forms on untyped objects" scenario and a lookalike-callee negative test.
- [ ] 2.5 TypeScript scan: the same for the TS forms with an `any` object. Verify with the "spyOn on an any
      object" scenario.

## 3. --keep (both twins)

- [ ] 3.1 Python: parse and normalize `--keep PATH[:LINE]` (real project-relative paths, directory by whole
      components), drop matching edits after all rules ran, `refactor.keep-unmatched` exit 2. Verify with the
      `--keep` scenarios incl. `tests/compatible.py` vs `tests/compat`, and file + line keep together.
- [ ] 3.2 TypeScript: the same. Verify with Vitest.

## 4. Blind-spot refusal (both twins)

- [ ] 4.1 Python: classify member renames; run the shared scan over every project source file before printing;
      refuse with sorted `attr-blindspot` / `unresolved-target` lines + `refactor.blindspots`, exit 1, nothing on
      stdout, nothing written; `--allow-blindspots` proceeds; kept lines exempt; non-member renames skip the scan.
      Verify with the "Member renames refuse on untyped receivers" scenarios.
- [ ] 4.2 TypeScript: the same with the TS scan. Verify with "TypeScript any receiver" and Vitest.

## 5. Stand-ins and --with / --without (both twins)

- [ ] 5.1 Python: compute the full hierarchy (regardless of `--no-in-hierarchy`); find project classes outside it
      declaring OLD (def, property, class or `self.` attribute, field); classify by `PATH:LINE` (every stand-in on
      the line, plus its hierarchy); resolve the joined symbol set first, then run every rule once on one snapshot;
      `refactor.stand-in` refusal, `refactor.not-stand-in` exit 2. Verify with the stand-in scenarios.
- [ ] 5.2 TypeScript: hierarchy = the language service's rename declarations (merged interfaces included);
      stand-ins = class / interface / type-literal members named OLD outside it, never object literals; `--with`
      adds that declaration's rename locations to the same edit set. Verify with "TypeScript structural class and
      object literal" and a noise case (several unrelated same-named members, each needing `--without`).

## 6. Members named by string (both twins)

- [ ] 6.1 Python receiver forms: rewrite the member literal where the callee resolves to a listed form and the
      object's type (instance, class object, `type[...]`) looks OLD up onto a renamed declaration; quote style kept.
      Verify with "Receiver forms on instances and class objects", "Member of another class" and "Lookalike
      callee", using real pytest and pytest-mock typings.
- [ ] 6.2 Shared static resolver (design decisions 27–29): move DEV-2289's scope/binding resolver out of
      `refactor/explicit_any.py` into a shared module of `living_architecture.refactor`, with an injected module
      finder (`explicit-any`: its import-root rule, unchanged; rename: rope's source folders in order, zero or
      several files → unresolved) and values naming project definitions (class/function with location). Gate:
      `tests/test_compliance_explicit_any.py` and every `compliance-explicit-any-*` golden pass unmodified.
- [ ] 6.3 Python dotted targets on that resolver: longest project-module prefix, then module bindings ("every
      binding agrees"), then class attributes along the C3 MRO of statically resolved bases; no import or
      execution; rewrite each segment resolving to a renamed declaration (class renames too); a project target not
      resolving to exactly one declaration → `refactor.unresolved-target` blind spot; external target with a
      segment OLD → `leftover`. Verify with "Dotted patch targets", "Class rename segment", "Unresolved targets",
      "Target from tests into a src layout", "Target through inheritance" (incl. a diamond) and "Ambiguous targets
      refuse" (two folders, conflicting bindings, `__all__`-excluded star import, cycle, unresolved base), a target
      through a star import honouring `__all__`, plus a test that a `sitecustomize.py` marker is never written.
      The tests for the scenarios added by the DEV-2289 merge come from task 0.1.
- [ ] 6.4 TypeScript forms: rewrite the member literal of the listed calls on a typed object or prototype. Verify
      with "TypeScript spyOn".

## 7. --docs (both twins)

- [ ] 7.1 Python: tokenize comments and string literals (docstrings, f-string literal parts) of every project
      source; qualified mentions (prefix must be a suffix of the declaring module path; bare `Owner.OLD` only when
      unambiguous); code-marked bare mentions in declaring files; the rest as sorted `refactor.leftover` lines;
      prose files from `config.source_files` with the shared extensions, qualified only. Verify with the `--docs`
      scenarios.
- [ ] 7.2 TypeScript: the same over comments (incl. JSDoc, `Owner#OLD`, `{@link …}`), string and template-literal
      text, and the same prose files via `sourceFiles`. Verify with "TypeScript JSDoc link" and Vitest.
- [ ] 7.3 Both: a mention another rule rewrote is not listed; without `--docs` nothing is scanned or listed.
      Verify with "Without --docs" and "Comments and messages untouched by default".

## 8. Conformance corpus

- [ ] 8.1 One adapter case per language (`refactor-rename-*` / `refactor-ts-rename-*`, the corpus's convention for
      `dr-refactor`) under `conformance/cases/` for: blind-spot refusal and
      `--allow-blindspots`; both refusals under `--apply` (tree unchanged); stand-in refusal, `--with`,
      `--without`, same-line classification, `not-stand-in`; string-member forms; `--keep` (line, file, directory,
      unmatched); `--docs` (qualified, code-marked, leftovers, prose, collision); paired cases for `dr-compliance
      --select attr-blindspot` and both usage errors. Python-only adapter cases for dotted targets.
- [ ] 8.2 List every new case in `conformance/INVENTORY.md`.
- [ ] 8.3 Verify every new findings template is produced by a golden and each case passes through both invoking
      twins (`scripts/conformance-cross`).

## 9. Skills and docs

- [ ] 9.1 Apply design.md "Approved wording" verbatim to `plugin/skills/deterministic-refactor/SKILL.md`,
      `plugin/skills/make-refactor-target-compliant/SKILL.md`, `plugin/languages/python.md`,
      `plugin/languages/typescript.md`. Verify `npx -y @anthropic-ai/claude-code plugin validate plugin`.
- [ ] 9.2 `docs/deterministic-refactoring.md`: append `attr-blindspot` to both rows of the `dr-compliance` table
      (the Python row already lists `explicit-any` from DEV-2289) and name the new
      `rename` options in the tools paragraph; `docs/commands.md` likewise if it lists `rename` options. Verify the
      docs build/link checks the repo runs.

## 10. Verification

- [ ] 10.1 Local test scope green in both twins; `ruff`, `basedpyright`, `npm run lint && npm run typecheck`,
      `la-arch-check` and `la-typecheck` pass; no existing golden changed except where a scenario above says so.
- [ ] 10.2 From this checkout, dry-run on SLayer's DEV-1607 branch: a storage method rename with untyped fixtures
      (expect the blind-spot refusal), `_ModelReadCache` (expect a stand-in), a
      `patch.object(SlayerQueryEngine, "save_model")` site, and `--docs` on a method with ``` ``get_model`` ```
      mentions; record the blind-spot scan's wall time here.

## 11. DEV-2289 merge (design decisions 25–34)

- [x] 11.1 Merge `origin/egor/dev-2289-living-architecture-python-dr-compliance-gets` into this branch; resolve the
      `CONTRACT_HASH` conflicts with `scripts/sync-shared`; align the Python check-list pins in
      `python/tests/test_contract.py` and `python/tests/test_compliance.py`.
- [ ] 11.2 After implementation, merge verification (decision 33): `scripts/sync-shared --check`; both twins'
      contract, snapshot and render tests; `compliance-help`, `compliance-select-other-language-check` and every
      `compliance-explicit-any-*` case through both invoking twins (`scripts/conformance-cross`); the
      findings-coverage test.
- [ ] 11.3 Before archiving (hard precondition, decision 34): `main` holds DEV-2289 archived and
      `openspec/changes/dev-2289-living-architecture-python-dr-compliance-gets/` is gone; merge `main`; read
      `openspec/specs/refactor/spec.md`; `openspec validate dev-2292-living-architecture-dr-refactor-and-its-skills
      --strict`; after archiving, the "Compliance check sets are per language" requirement in the corpus lists both
      `explicit-any` and `attr-blindspot` for Python and keeps the "Python explicit-any compliance check"
      requirement.

## 12. Post-merge (after the PR merges; not part of its diff)

- [ ] 12.1 Release 0.9.0: bump `python/pyproject.toml`, `node/package.json` and
      `plugin/.claude-plugin/plugin.json` together, run `scripts/release-check`, publish.
- [ ] 12.2 Pin 0.9.0 in SLayer; DEV-2292 stays open until the pin lands.
