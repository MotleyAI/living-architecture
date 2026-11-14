## Context

See proposal.md (Why). Today a Python rename is rope's edits plus every reference basedpyright resolves plus the
keyed-class rewrites, computed over one snapshot (`rename_union.SymbolRename`); a TypeScript rename is the language
service's rename locations. `dr-compliance --attr` already finds untyped `x.NAME` receivers in both twins, and
`attr-blindspot` is printed as a kind but missing from the registry's `compliance_checks`, so `--select` rejects it.

Principles that apply (`architecture/system.arc42.md`; the `refactor` element has no arc42 of its own):
1. Twins — every item lands in both twins, pinned by paired conformance cases.
2. Shared contract — new options and the prose extensions in `cli.yaml`, templates in `findings.yaml`, the
   string-member call forms and `attr-blindspot` in `languages.yaml`.
3. Language-specific code only in `lang` and `refactor` — all new code is there.
4. No target-repo code runs — the dotted-path resolver and the stand-in scan are static.

Spec attachment: the existing `refactor` capability (metadata `specs` of `python.refactor`). No model or arc42
change: `refactor -> config` exists in both twins, so prose files come from `config.source_files` / `sourceFiles`.

## Goals / Non-Goals

**Goals:**
- A member rename is complete or loud: each gap the tool can enumerate is rewritten, refused with a per-site fix
  flag, or listed.
- One scan per twin backs both `dr-compliance --attr` and the rename's blind-spot refusal.
- One symbol set per rename (located hierarchy ∪ `--with` hierarchies); every rule runs once over it on one snapshot.

**Non-Goals:**
- `__all__` entries, `importlib` strings, entry points and config paths stay string-only leftovers.
- TypeScript object-literal "fakes" are not stand-ins (an untyped one that flows into a typed position becomes a
  `tsc` error after the rename, so the gate catches it).
- `--keep` on `move-symbol` / `move-module`.
- Dotted-path rewriting for module renames and moves.
- An assignability filter on stand-ins (decision 3).
- Changing how `explicit-any` finds first-party modules (decision 27).

## Decisions

Structural cause (design bias): the rename's reference set is "what the checker resolves", and everything outside
it is silent; its output cannot tell "nothing else references this" from "something may, unseen". The fix maps each
gap the tool can enumerate (untyped receivers, out-of-hierarchy declarations of OLD, string forms naming OLD,
textual mentions) to one outcome: rewrite, refuse naming the per-site flag, or list. Grounded in principles 1 and 2.

1. **TypeScript parity**: A) all six items in both twins, B) Python now, TS in a follow-up issue. Took A: the gaps
   belong to the rename contract; a probe showed the TS language service misses structural stand-ins and `spyOn`
   strings, and its `findInStrings`/`findInComments` is purely textual. (user)
2. **Untyped receivers**: A) a member rename refuses with per-site findings, `--allow-blindspots` overrides, B) report
   and proceed, C) skill step only. Took A: "compliant target" becomes machine-checked; one scan shared with
   `dr-compliance --attr`. (user)
3. **Stand-ins**: A) refuse until each is classified with `--with`/`--without`, every same-named class counted,
   B) report + `--with`, proceed, C) report only. Took A: flow-linked detection would have its own blind spots; one
   rename = one diff. (user)
4. **Dotted-path patch targets**: A) resolve statically and rewrite, B) receiver forms only. Took A, an extension
   beyond the issue's list: the same silent-miss class, and it covers function and class renames. (user)
5. **Bare words in declaring files (`--docs`)**: A) every whole word, B) code-marked only (backticks, Sphinx role,
   `{@link}`, a string starting with OLD and `:`/`(`/whitespace), the rest listed. Took B: high-precision rewrites,
   complete leftovers. (user)
6. **Prose files in `--docs`**: A) sources only, B) also git-listed `.md`/`.rst`/`.txt`, qualified mentions only,
   bare words listed. Took B, an extension beyond the issue. (user)
7. **`--keep` shape**: `PATH[:LINE]` (file, directory or line), line-literal, `rename` only; an unmatched keep exits
   2; kept lines are exempt from the blind-spot refusal. Covers both forms the issue offered in one flag. (default)
8. **`attr-blindspot` selection**: a registry check id parameterized by `--attr`; `--attr` without it selected, or
   it selected without `--attr`, exits 2; a test pins "every printed kind is selectable". The structural fix for
   item 6; the old `--select untyped-def --attr` workaround becomes an error. (default)
9. **Member rename** = a symbol declared in a class body (incl. `self.x`, fields, TS interface/type-literal members);
   only those get the blind-spot and stand-in refusals. (default)
10. **Stand-in scope**: project source files only; the full hierarchy regardless of `--no-in-hierarchy`; a
    classification covers the class's hierarchy; `--with` joins the union and detection runs against it. TS
    stand-ins are classes, interfaces and type literals, not object literals. (default)
11. **Where the lists live**: string-member call forms in `languages.yaml` (`string_member_calls`, a language fact);
    prose extensions in `cli.yaml` under `dr-refactor` (a command parameter). Principle 2. (default)
12. **String forms count as blind spots** when their object is untyped, in both the refusal and `dr-compliance
    --attr` (one scan). (default)
13. **Release and SLayer pin are post-merge** tasks, following DEV-2291's decision 8. (default)
14. **Name the modified requirements**: TypeScript rename, compliance check sets, TypeScript compliance checks and
    Python `--attr` are MODIFIED in the delta. (codex)
15. **Resolved callee names; untyped callee = blind spot**: the forms are matched by the qualified name the checker
    resolves (typeshed's `patch.object`, pytest-mock's `patch.object`, pytest's `MonkeyPatch.setattr`/`delattr`);
    a call with the form's syntax and the literal OLD whose callee is unresolved (an unannotated `mocker` or
    `monkeypatch` fixture) is a blind spot. Tests use the real pytest and pytest-mock typings. (codex)
16. **TypeScript hierarchy clarified**: the declarations the language service's rename returns, merged interface
    declarations included; union, intersection and mapped types are not declarations. The assignability filter was
    rejected (decision 3 counts every same-named class); object literals stay out (Non-Goals). (codex; filter part
    rejected (codex))
17. **`PATH:LINE` classifies every stand-in member declared on that line**, so same-line declarations are
    well-defined without a column. (codex)
18. **`--docs` simple-name collisions**: a dotted prefix must be a suffix of the declaring module's path; a bare
    `Owner.OLD` is rewritten only when no other project class named `Owner` declares OLD, otherwise listed. (codex)
19. **Unresolved project patch targets refuse**: a target whose first segment names a project top-level package,
    with a segment OLD, that does not resolve joins the blind-spot refusal as `refactor.unresolved-target`
    (`--keep` / `--allow-blindspots` override); a target outside the project is listed as `leftover`. This reverses
    an earlier default that only listed them. Resolution is the shared static resolver of decision 27 (it replaced
    rope's static module lookup). (codex)
20. **Skill blind-spot command scans the repo**: `<paths>` → `<repo>` in the skill commands, matching the rename's
    project-wide scan. (codex; user, approved wording)
21. **`--keep` normalization**: real project-relative paths; a directory matches on whole path components; an edit
    matches by its line (edits replace one identifier, never span lines). Validating keeps against source
    locations instead of edits was rejected (codex): a keep lives for one invocation, so checker drift between runs
    cannot make it stale. (codex)
22. **One symbol set, one pass**: the located hierarchy and every `--with` hierarchy are resolved first; each rule
    runs once over the set on one snapshot; identical edits merge as today. (codex)
23. **Extra refusal and safety tests**: both refusals together under `--apply` write nothing; a same-line `--with`;
    lookalike callees; TS structural noise; doc name collisions; a file keep plus a line keep; several `--with`
    stand-ins sharing references; each conformance case through both invoking twins. (codex)
24. **Skill and language-doc wording**: applied verbatim from "Approved wording" below. (user, approved wording)

Merging DEV-2289 (Python `explicit-any` in the default check set, PR #41) into this branch before implementation:

25. **Merge it now, not after it lands**: its branch was merged into this one with the vendored `CONTRACT_HASH`
    conflicts resolved by `scripts/sync-shared`; `main` is merged again once DEV-2289 lands. (user)
26. **One combined check-set requirement**: the MODIFIED "Compliance check sets are per language" carries both
    changes — Python `[untyped-def, unannotated-attr, explicit-any, mock, rope-walk, attr-blindspot]`, "Python
    default unchanged" scoped to no `--attr` and no `Any`, DEV-2289's "Python default reports Any" scenario, and
    "Language-specific id" on `--select tsconfig` (DEV-2289's switch). Our archive follows DEV-2289's, so our full
    text is what the corpus keeps. Our contract pins of the Python list (`test_contract.py`,
    `test_compliance.py`'s `ALL_CHECKS`) are aligned in the merge commit. (user)
27. **One static resolver for `explicit-any` and dotted patch targets**: DEV-2289's scope/binding resolver moves
    out of `explicit_any.py` into a shared module of `python.refactor`, generalised with (a) an injected module
    finder — `explicit-any` keeps its import-root rule, the rename passes rope's source folders so `tests/` reaches
    `src/pkg` — and (b) values that name project definitions (a class or function with its location), so a target
    segment lands on a declaration. Weighed: a second resolver on rope's module lookup (two paths that must agree
    by hand on star imports, `__all__`, aliases and cycles). Also weighed and rejected: switching `explicit-any`
    to the project-wide finder (changes DEV-2289's approved behaviour, walks the tree on every default run, fixes
    only a rare false negative). (user)
28. **Module finder contract**: rope's source folders in order; zero files is unresolved, more than one distinct
    file is ambiguous and unresolved; directories without `__init__.py` below a folder are allowed. Tested with a
    `src/pkg` target patched from `tests/` and a module present in two folders. (codex)
29. **Declarations vs `Any` resolution**: the shared binding layer keeps DEV-2289's conservative "every binding
    agrees" rule (conflicting bindings are unresolved, so a project target refuses, loudly); class attributes use
    a separate lookup along the C3 method resolution order over statically resolved bases, unresolved when an
    unresolved base comes before the attribute. Tested: inherited, overridden (with and without
    `--no-in-hierarchy`), diamond, unresolved base. (codex)
30. **Extraction gate**: DEV-2289's `explicit-any` unit tests and conformance goldens pass unmodified after the
    extraction. Rejected (codex): a second regression matrix for `explicit-any` — its suite already covers mixed
    bindings, shadowing, relative imports, `__all__`, private names and cycles over the same code. (codex)
31. **Star-import targets**: two target tests, through a star import honouring `__all__` and through an import
    cycle (unresolved, refuses). Rejected (codex): repeating DEV-2289's full star-import matrix for targets, same
    reason as decision 30. (codex)
32. **Failure classification**: a target whose first segment names a project top-level package and that does not
    resolve to exactly one declaration (ambiguous folders, conflicting bindings, unresolved base, cycle) is
    `refactor.unresolved-target`; unit tests pin each class, the existing `refactor-rename-patch-target-unresolved`
    case pins the command. Rejected (codex): one conformance case per ambiguity class. (codex)
33. **Merge verification**: `scripts/sync-shared --check`; both twins' contract, snapshot and render tests;
    `compliance-help`, `compliance-select-other-language-check` and every DEV-2289 `explicit-any` case through both
    invoking twins (`scripts/conformance-cross`); the findings-coverage test; our failing set unchanged apart from
    the aligned pins. (codex)
34. **Archive order is a hard precondition**: this change archives only once `main` holds DEV-2289 archived (its
    change folder gone); then merge `main`, read `openspec/specs/refactor/spec.md`, validate strictly, archive, and
    check the archived requirement lists both `explicit-any` and `attr-blindspot`. Both ship in 0.9.0. (codex)

Review-round causes (2026-11-14). About 19 review findings were instances of five causes: syntax standing in for
what the checker knows, rules with a silent default, text primitives written twice, project files defined several
ways, and a probe leaking its coordinate space. Decisions 35–41 close each cause once.

35. **One outcome per examined site**: each rule returns, for every site it examines, one of rewrite, blind spot,
    leftover or unrelated, and the driver files it; no rule leaves a site naming OLD without one. Anything ambiguous
    in code is never rewritten: a member rename refuses on it, any other rename lists it; an ambiguous `--docs`
    mention is listed. Module renames share `--keep` and edit emission with symbol renames. Behaviour-preserving
    apart from decision 36. (user)
36. **Exact OLD literals listed by default**: A) a member rename lists every string literal whose whole value is OLD
    that no rule handled, even without `--docs`, B) keep "unchanged and unlisted" and record the limit in Risks.
    Took A: it closes string forms no rule anticipates (`operator.attrgetter`, `obj['saveModel']`, home-made
    `getattr` wrappers), and listing never blocks. (user)
37. **Membership from the checker**: the TypeScript stand-in index comes from each class, interface and type
    literal's property symbol for OLD and its declarations (parameter properties, quoted and constant computed names
    by construction); syntax only locates the name span. A spike first confirms the symbol route covers interfaces,
    type literals and merged declarations and keeps object literals out; if it does not, stop and ask. Python keeps
    its declaration walker, cross-checked by a test against stdlib `symtable` over every class-level binding form,
    directly and inside `if`/`try`/`with`/`for`/`while`/`match`; `self.x` attributes stay on the walker. Callees:
    resolution decides, syntax only for an unresolved callee. (user)
38. **One primitive per twin, pinned by shared vectors**: new `shared/vectors/` files, run by both twins, for line
    of offset, mention boundaries, qualifier segments and site matching, with per-language expectations where line
    conventions differ (Python `\n`, `\r\n`, `\r`; TypeScript adds U+2028/U+2029). Each twin keeps one line index
    and routes every line computation through it. (user)
39. **One file universe per twin**: one function per twin returns a language's source files under the project; the
    rename (blind spots, stand-ins, string forms, `--docs`) and `dr-compliance` directory expansion both use it. If
    rope's file set and the routing expansion differ in a way the spec does not settle, stop and ask. (user)
40. **Probe encapsulated**: the probe is one object owning the rewritten text and its offset map, and returns only
    original-file spans. (user)
41. **Review rules for the remaining rounds**: a finding that is an instance of causes 1–5 gets a vector or case and
    a fix inside the shared mechanism; one that opens a new cause stops for a decision; an edge case outside the
    spec gets a reply citing the rule, no code. The pre-push Codex brief adds: a site naming OLD that ends with no
    edit and no printed line; an input where the twins differ; a line number or project file list computed by its
    own means. (user)
42. **Python file universe = the routing expansion**: Python's `excluded_dirs` takes rope's default ignored
    directory names (`.venv`, `venv`, `.tox`, `.git`, `.hg`, `.svn`, `_svn`, `.mypy_cache`, `.pytest_cache`,
    `.ropeproject`), and the rename's candidate files come from the routing expansion of the project root, so the
    rename and `dr-compliance` scan one set. Rejected: `dr-compliance` on rope's file set (ties a neutral command to
    rope's configuration); the rename over virtualenvs (refuses on third-party code). (user)
43. **Computed-name stand-ins**: the checker index includes members declared by a constant computed name; they are
    stand-ins, `--without` classifies them, and `--with` exits 2 with `refactor.computed-stand-in`, because the
    language service cannot rename them (a use-site rename returns nothing; one at `[KEY]` renames the constant).
    Rejected: leaving them out (a silent miss). (user)

## Risks / Trade-offs

- [Common member names (`run`, `name`, `type`) produce many stand-ins] → one `--without PATH:LINE` per class
  settles each; listing everything is what keeps the check sound.
- [The blind-spot scan hovers every `.OLD` access in the project] → it reuses the language server the rename already
  starts; the SLayer timing task records the cost.
- [`--docs` message-prefix rule rewrites prose that starts with OLD + whitespace in a declaring file] → limited to
  declaring files; the diff shows each rewrite.
- [pytest / pytest-mock typings change their qualified names] → the names live in `languages.yaml`, pinned by tests
  using the real packages.
- [Exact-OLD string listing on common names (`name`, `type`) produces long leftover lists] → member renames and
  whole-value matches only; listing never blocks.

## Migration Plan

`dr-compliance --select <ids without attr-blindspot> --attr NAME` now exits 2: use `--select attr-blindspot --attr
NAME`. The skills change in the same PR. Archive only after DEV-2289 is archived on `main` (decision 34). Release
0.9.0 after merge (tool inputs change, so the minor version moves; it carries DEV-2289 too), then pin it in SLayer.

## Approved wording

### plugin/skills/deterministic-refactor/SKILL.md — replaces `## Procedure` and `## Commands`

```markdown
## Procedure

1. Locate the symbol with the editor/LSP (not grep) → file, line, col.
2. **Check the verifier**: run `la-typecheck`. It runs the project's type
   checker in the project env (the one the tests use) against its committed
   baseline, and it must pass before you start. If it prints "nothing to
   check", STOP and tell the user: with no type check there is no guarantee,
   so offer to set one up (`commands.typecheck` and
   `la-typecheck --write-baseline`) first.
3. **Type the receivers** (member renames): `dr-compliance --select attr-blindspot --attr OLD <repo>`
   lists each receiver of `OLD` the checker cannot type. Type them
   (`la:make-refactor-target-compliant`) until it reports nothing; `dr-refactor`
   refuses a member rename while any remain.
4. **Dry-run** (default):
   `dr-refactor --project <repo> rename --file F --line L --col C --new-name N --docs`.
   Method renames rename the hierarchy by default. Re-run until it is the rename you want:
   - `stand-in`: a class outside the hierarchy declares `OLD`. `--with PATH:LINE` renames it too
     (a duck-typed implementation: a cache, a fake, a `cast()` target); `--without PATH:LINE` leaves it
     (an unrelated class).
   - `attr-blindspot` on a receiver that cannot be typed (a third-party `Any`): `--allow-blindspots`,
     and tell the user which.
   - a site that must keep the old name (a back-compat test or shim): `--keep PATH:LINE`, or
     `--keep PATH` for a whole file.
   Show the diff.
5. **Apply**: `--apply` is a GLOBAL flag and goes before the subcommand
   (`dr-refactor --project <repo> --apply rename ...`); trailing it errors.
6. **GATE — done only when ALL pass:**
   - `la-typecheck` passes: **no new errors** vs the baseline;
   - `dr-mock-lint <tests>` passes;
   - the full non-integration test suite (`la-config get commands.test`) passes;
   - by hand, only these: each `leftover` line the apply printed, each receiver
     `--allow-blindspots` let through, and the string-only references the language doc lists.
7. Review the diff. The user commits — never commit or `git add -A`.

## Commands

`dr-refactor` subcommands: `rename` / `move-symbol` / `move-module`. Dry-run is
default; `--apply` writes; `--project` defaults to cwd. Locator: `--line [--col]`
(1-based), `--offset N` (0-based), or `--name` (first declaration, else first
use). `rename` also takes `--with` / `--without PATH:LINE`, `--keep PATH[:LINE]`,
`--allow-blindspots` and `--docs` (comments, docstrings, strings and prose files:
qualified mentions everywhere, code-marked ones in the declaring files, the rest
listed as `leftover`). Move destinations must already exist, and a `move-symbol`
destination is a file of the same language. Run the repo's formatter afterwards.
```

### plugin/skills/make-refactor-target-compliant/SKILL.md — replaces steps 2, 4, 5 and the closing paragraph

```markdown
2. **Enumerate blind spots:**
   - `dr-compliance --select attr-blindspot --attr NAME <repo>` → `x.NAME`,
     `getattr(x, "NAME")` and the like where `x` is untyped. Each names the
     receiver to type.
   - A `dr-refactor` dry-run of the rename lists the stand-ins: classes outside
     the hierarchy that declare NAME. Make a real implementation a subclass or
     a `Protocol` implementation now, or classify it at the rename (`--with` /
     `--without`, see `la:deterministic-refactor`).
```

(step 3 unchanged)

```markdown
4. **Re-check until the blast radius is typed:**
   - `dr-compliance --select attr-blindspot --attr NAME <repo>` reports nothing;
   - `la-typecheck` shows no new errors over the touched files.
5. **Then run `la:deterministic-refactor`.** Every real reference is now
   type-visible; what is left is a string the rename lists as a `leftover`
   or the language doc names.

The guarantee still comes from the type checker after the rename; this
skill's job is to shrink the checker's untyped surface over the blast radius
to zero.
```

### plugin/languages/python.md — `## Refactoring`: replaces the paragraph after "It refuses a new name the function already uses." through the end of the leftovers list

```markdown
A rename also rewrites a member named by string on an object the checker types: `getattr`, `setattr`, `hasattr`,
`delattr`, `monkeypatch.setattr` / `delattr` and `patch.object` (also `mocker.patch.object`), and each segment of a
`patch`, `mocker.patch` or `monkeypatch.setattr` / `delattr` target that resolves statically to a renamed
declaration. A member rename refuses while a receiver of the old name is `Unknown` or `Any` (`--allow-blindspots`
overrides) or a class outside the hierarchy declares the old name (`--with` / `--without`).

What a rename leaves unrenamed:
- receivers `--allow-blindspots` let through; `dr-compliance --attr` misses only a subscript or call receiver typed
  `Model | Any` whose `Model.NAME` is itself `Any`;
- string-only references: `importlib`, `__all__`, entry points, config paths, and a `patch` target that does not
  resolve into the project (listed as a `leftover`);
- mentions in comments, docstrings, messages and prose files: all of them without `--docs`; with it, the ones it
  lists as `leftover`;
```

(the parameter-rename and field-rename bullets stay as they are)

### plugin/languages/typescript.md — `## Refactoring`: replaces the first paragraph's parenthetical and the string-only paragraph

First paragraph: `(overrides and implementations included; strings and comments untouched)` becomes

```markdown
(overrides and implementations included, plus the member string of `vi.spyOn` / `jest.spyOn`, `Reflect.*` and
`Object.defineProperty` / `getOwnPropertyDescriptor` on a typed object; comments and other strings only with
`--docs`)
```

and after it:

```markdown
A member rename refuses while a receiver of the old name is `any` (`--allow-blindspots` overrides) or a class,
interface or type literal outside the hierarchy declares the old name (`--with` / `--without`).

String-only references no static tool sees: dynamic `import()` of a computed path, `require()` of a computed
path, `vi.mock('path')` / `jest.mock('path')` strings, property access by a computed key (`obj[name]`), an
object literal outside any declared type holding the old key, JSON and config files, and package `exports` maps.
```
