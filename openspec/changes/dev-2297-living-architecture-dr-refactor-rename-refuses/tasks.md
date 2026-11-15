## 1. Tests (pr-tests)

- [x] 1.1 Conformance cases for the requirement "Renames keep every reference's binding", paired (`python/` and
      `node/` overlays) unless marked, new goldens written with `LA_UPDATE_GOLDENS=1`: issue capture; same-scope
      collision (`old` → `f`); outer reference shadowed; builtin shadowed (`len` / `parseInt`); direct importer binds
      the new name; re-export chain (TS) and star-import chain (Python adapter), two hops each; overload group renamed
      to a free name (exit 0); forward-reference string captured (Python adapter); kept site rebinding; kept site
      dangling (exit 0); kept declaration; no false conflict (attribute, call keyword, comment, unrelated local,
      nested binding not reading `old`; exit 0); `--docs` mention and `Literal` member beside a local of the new name
      (exit 0). TypeScript adapter: re-export boundary (exit 0); type vs value meanings (exit 0); interface renamed
      onto a class (declaration merging). Python adapter: class-body name vs method local, comprehension first
      iterable, comprehension walrus, `global`, `nonlocal` (each refused or allowed exactly as Python resolves).
      Verify: every refusing case fails before the fix (exit 0 today), every exit-0 case passes or fails as the
      golden says.
- [x] 1.2 Conformance cases for "Member renames refuse a name the member's namespace holds", paired unless marked:
      issue duplicate member; ancestor declares; descendant declares; library base (`dict.keys` /
      `Array<number>.map`); implicit root (`__repr__` / `toString`); renamed hierarchy is no conflict (override,
      interface plus implementation, diamond / interface extending two interfaces; exit 0). TypeScript adapter:
      instance → static name (exit 0). Python adapter: `self.next` in `__init__`; `classmethod` of the new name.
      Verify: refusing cases fail before the fix.
- [x] 1.3 Conformance cases for the modified rename-map requirement, paired: entries capturing each other's
      references (each alone clean); retarget beside a rename of its target (exit 0). The existing
      `refactor-map-swap` and `refactor-map-converging-names` goldens stay unchanged. Verify: the capture case fails
      before the fix.
- [x] 1.4 Conformance cases for the modified Python rename-references requirement (adapter): module onto an existing
      module, onto a package (`pkg/b/__init__.py`), onto an `__init__.py` binding; module rename capturing an
      importer's `b`; relative import `from . import a` → `from . import b` (exit 0); a namespace package destination;
      a kept import. Verify: the refusing cases fail before the fix.
- [x] 1.5 Align `python/tests/test_parameter_rename.py::test_type_parameter_of_the_new_name_is_a_conflict[nested]` to
      the relaxed rule (design decision 18): the rename exits 0 and renames `model_name` (approved in planning). The
      other parameter conflict tests stay unchanged. Verify: it fails before the fix.
- [x] 1.6 Unit tests, Python (`python/tests/`): the binding resolver against `symtable` over every binding form of
      the requirement (as `test_members_symtable.py` does for members), star-import binding (`__all__` literal list,
      tuple, absent, non-literal → module-level names), occurrence prefilter across all project sources, edit-origin
      filter (decision 22), finding-site order in original coordinates; `shared/languages.yaml` python `root_members`
      equals the union of `object`'s members in the pinned basedpyright's typeshed `builtins.pyi` over every version
      branch (drift test). Verify: they fail before the fix.
- [x] 1.7 Unit tests, TypeScript (`node/test/`): identity by declaration set across the overlay program (overloads,
      merged declarations, aliases), per-meaning resolution, the checks running after `--keep` and before the
      blind-spot refusal (a case with both a conflict and a blind spot reports the conflict), and the two existing
      `rename-map.test.ts` convergence tests unchanged. Verify: the new ones fail before the fix.
- [x] 1.8 `conformance/INVENTORY.md`: one row per new case group, in the refactor section. Verify: the inventory test
      passes.

## 2. Shared contract (pr-implement)

- [ ] 2.1 `shared/languages.yaml`: python `root_members` (sorted list), documented in the header comment; run
      `scripts/sync-shared`. Verify: drift tests and 1.6's typeshed test pass.

## 3. TypeScript twin (pr-implement)

- [ ] 3.1 A binding module under `node/src/refactor/`: the occurrence prefilter over every project source, the overlay
      program over the edited texts, per-meaning resolution, identity by declaration set (design decisions 9, 19–22),
      the kept-site rule, and the site order of decision 10.
- [ ] 3.2 The member-namespace check (decisions 3, 7, 24): the renamed set subtracted; instance and static sides;
      ancestors through heritage clauses and the apparent `Object` members; project descendants.
- [ ] 3.3 `rename.ts`: remove `checkNameConflict`, `checkConvergence`, `bindingScope`, `blockOf`, `blockScoped`;
      `runEntries` runs the per-entry then combined checks after `keep` and before `refusal` (decisions 11, 12);
      retarget entries expect their target (decision 13). Verify: 1.1–1.3 and 1.7 pass through the npm twin.

## 4. Python twin (pr-implement)

- [ ] 4.1 A binding module under `python/src/living_architecture/refactor/`: `symtable` over each edited source,
      import bindings as module-local declarations, star-import binding, forward-reference strings read in their
      scope, the occurrence prefilter, the kept-site rule, the site order of decision 10; a parse failure raises the
      `cannot-rename` refusal.
- [ ] 4.2 The member-namespace check: `member_declarations` for class bodies, `self` attributes in the class's
      methods, the MRO through rope (library bases), `root_members` from the shared contract, project descendants,
      the renamed set subtracted.
- [ ] 4.3 `rename_map.py` / `rename_union.py`: remove `check_convergence` and the `_variable_sites` parameter scan
      (and helpers only it used); `run_map` runs the per-entry then combined checks after `keep` and before
      `refusal`.
- [ ] 4.4 `rope_refactor.py` `_module_rename`: the destination check before rope computes changes, then the binding
      check over rope's edits on a virtual post-move snapshot (decision 23). Verify: 1.1–1.6 pass through the PyPI
      twin.

## 5. Finish (pr-implement)

- [ ] 5.1 Every new case through both twins (`scripts/conformance-cross`), the local test scope of `/la:pr`, lint and
      typecheck in both twins.
- [ ] 5.2 Enforcement bundle: `la-arch-check`, LikeC4 validation, `la-typecheck` against its baseline.
