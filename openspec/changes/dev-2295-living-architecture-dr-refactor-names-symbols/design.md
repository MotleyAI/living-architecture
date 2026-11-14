## Context

See proposal.md (Why). This change builds on DEV-2292's rename pipeline, which is on `main` and archived: one
symbol set per rename, blind-spot and stand-in refusals, string members, `--keep`, `--docs`, and its shared
mechanisms: one outcome per examined site (`refactor/outcomes`), one line index and one file universe per twin,
the probe object, and `shared/vectors/refactor-text.yaml`. `origin/main` is merged into this branch (tasks section
0) before implementation continues; decisions 38–46 fit this change to those mechanisms.

Today a Python rename is `rename_union.SymbolRename` (rope + basedpyright references + keyed rewrites over one
`Snapshot`); a TypeScript rename is the language service's rename locations; both are located by `--offset`,
`--line`/`--col` or `--name`. `la-typecheck` runs `commands.typecheck.<language>` against `.basedpyright/baseline.json`
(entries `{code, range{startColumn, endColumn, lineCount}}` per file, matched by basedpyright's LCS diff against
position-sorted diagnostics) or `.tsc-baseline.json` (`(file, code, message) → count`). la's own basedpyright
language server runs isolated from the project environment.

Principles that apply (`architecture/system.arc42.md`; the `refactor` element has no arc42 of its own):
1. Twins — every item lands in both twins, pinned by conformance cases run through both invoking twins.
2. Shared contract — options, the `exclusive` key, templates and the rename-map schema live in `shared/`.
3. Language-specific code only in `lang` and `refactor` — all new code is there, plus `cli` for the manifest key.
4. No target-repo code runs — except the configured `commands.typecheck.python`, which the Python baseline aligner
   runs; the `Literal` probe and the TypeScript aligner use la's own language servers, in memory.

Spec attachment: `refactor` (metadata `specs` of `python.refactor`), `twin-forwarding` (`python.twin`) and the
cross-cutting `shared-contract`. Model edit (decision 8): `python { refactor -> typecheck; refactor -> changes }`,
`typescript { refactor -> changes }`, diagrams regenerated.

## Goals / Non-Goals

**Goals:**
- A symbol is addressed by a path that does not go stale; a map of entries is one dry-run, one apply, one gate.
- No refactor resurfaces a baselined error.
- `rename` and `retarget` are one-entry maps: one code path.

**Non-Goals:**
- Cross-module retarget (an alias imported from another module): refused with `refactor.retarget-scope`.
- Mixed-language rename maps.
- Change-signature codemods (splitting or merging classes or fields, constructor respelling).
- Comparing failing tests against a base ref.
- Renaming compound names (listed only).
- TypeScript `Literal` probing beyond the language service's rename (an `as const` local passed into the union
  becomes a tsc error the gate reports).
- `dr-mock-lint --base` with arbitrary refs (tags, SHAs).
- Guarding the apply against concurrent modification beyond the re-check before writing.

## Decisions

Structural cause (design bias): (1) a refactor is addressed by position and run one symbol at a time, so positions
go stale and every symbol needs its own gate; fix: stable symbol paths and a map as the unit of work, with `rename`
and `retarget` as one-entry maps. (2) A refactor's write set stops at the sources while the baseline is keyed by
position or message; fix: every refactor yields a position map and one aligner per language maps each baselined
diagnostic through it, for every subcommand. Grounded in principles 1 and 2.

1. **Locator syntax**: A) `--file F --symbol Q` (in-file path, both twins), B) `--symbol pkg.mod.Class.method`
   (dotted import path, a second TS grammar, module resolution), C) `--symbol F::Q`. Took A: one grammar, no
   module-resolution ambiguity, routing by `--file` unchanged. (user)
2. **Sequencing with DEV-2292**: A) tests now, implement after DEV-2292's implementation is merged in, B) implement
   both here, C) wait before tests. Took A: separate PRs, as the tracker's "blocked by" says. (user)
3. **TypeScript baseline diagnostics**: A) bundled language services before/after in memory, B) configured tsc
   before and after writing. Took A: in-process, works in dry-run, degrades to today's behaviour on a TypeScript
   version mismatch. Python is fixed to the configured checker because la's server is isolated from the project
   environment. (user)
4. **Baseline in dry-run**: A) dry-run computes and prints it, B) apply only, C) opt-in flag. Took A: `--apply`
   writes exactly what the dry-run printed. (user)
5. **Baseline scope**: A) every refactor through one position map, B) renames + move-module, C) renames only. Took
   A, an extension beyond the issue: one aligner closes the bug class. (user)
6. **Python `Literal` rename**: A) checker probe in la's language server, B) syntactic contexts + hover. Took A:
   identity from the checker, one rule, loud on what it cannot fix. (user)
7. **Retarget scope**: A) same scope + retarget map entries, B) cross-module with import re-pointing, C) same
   scope, command only. Took A: covers every DEV-2294 twin shape; map entries (an extension beyond the issue) turn
   SLayer's 43 twins into one dry-run and one gate. (user)
8. **Model edit**: add `python { refactor -> typecheck; refactor -> changes }` and `typescript { refactor ->
   changes }`, regenerate diagrams. Weighed: moving the helpers into `lang` / `config`, a structural refactor that
   belongs in its own la:arch-cleanup change. (user, approved edit)
9. **Skill and language-doc wording**: applied verbatim from "Approved wording" below. (user, approved wording)
10. **`--name` removed**, replaced by `--symbol`: its "first declaration, else first use" guess is the failure the
    issue reports; an import binding counts as a declaration, so renaming from an importing file keeps working. The
    conformance cases using `--name` migrate. **BREAKING**. (default)
11. **One locator**: `--offset`, `--line` and `--symbol` are mutually exclusive through a new manifest key
    `exclusive` (shared-contract), replacing today's silent precedence. (default)
12. **Locator failures exit 2** listing candidates, as the issue states; out-of-range `--line` / `--offset` keep
    exit 1. (default)
13. **Map format**: a YAML list validated by `shared/schema/rename-map.schema.json`; entry files relative to
    `--project` (the map describes the project, independent of the working directory); map-level options apply to
    every entry. (default)
14. **Map conflicts**: identical edits merge, differing edits to one span refuse; name-conflict checks run against
    the code before the map, so swaps and chains in one scope refuse. (default)
15. **Mixed-language maps refused** (exit 2): one twin computes one snapshot. (default)
16. **Retarget refuses an overridden alias** (calls would bypass the override) and removes an import it would
    duplicate (a duplicate TS import specifier is an error). (default)
17. **Baseline checker failure refuses** the refactor (exit 1, nothing written). (default)
18. **`Literal` new value**: no quote, backslash or line break; the identifier rule does not apply. (default)
19. **`Literal` locator**: `Q['value']` on any declaration whose annotation or alias body holds the literal type,
    plus a line/col on the string itself. (default)
20. **Compound-name rule**: words split at `_` and CamelCase, case-insensitive, the last word may take `s`/`es`;
    a new `refactor.compound` template. (default)
21. **`--attr` repeatable as an ADDED requirement**, so its text does not depend on DEV-2292's MODIFIED wording of
    "Python --attr reports Unknown and Any receivers". (default)
22. **`dr-mock-lint` becomes a parsed command**, fixing `--help` structurally; `--base BRANCH` follows
    `la-affected-tests`'s `origin/BRANCH` convention, through `changes`; base paths mapped through git rename
    detection. (default)
23. **Archive order**: this change archives after DEV-2292's and DEV-2289's. (default)
24. **Python checker scope**: the configured command runs over the affected files only; a Python key has no message,
    so an unedited file's entries cannot shift. Probed: `basedpyright -p . file.py --outputjson` works. Tests cover a
    `-p` command and one with positional paths. Rejected (codex): running the whole project. (codex)
25. **Python matching is basedpyright's own**: probed, a run without `--writebaseline` prunes the baseline file it is
    given to exactly the entries it matched, in order. The aligner runs on a temporary copy, then pairs that pruned
    list 1:1 with the baselined diagnostics (the empty-baseline run's minus the copy run's, by position). Tests:
    identical-shaped entries, a stale entry, a diagnostic inserted earlier, multiline ranges. (codex)
26. **TypeScript diagnostics are pre-emit diagnostics** (`ts.getPreEmitDiagnostics`: syntactic, semantic, options,
    declaration) from every project holding the file, over every file the baseline lists; a parity test runs real
    tsc on an unedited consumer whose message changes. Rejected (codex): running tsc (decision 3). (codex)
27. **Ambiguous TypeScript attribution**: a key whose instances split while only some are baselined is left
    unchanged with a `refactor.baseline-ambiguous` warning; no refusal. (codex)
28. **Rollback on write failure**: each file written through a same-directory temporary file and a rename; a failed
    write restores the files already written. Rejected (codex): guarding concurrent modification beyond today's
    re-check. (codex)
29. **Retarget validation**: new-name collision checks do not apply; a bare-name reference where the target's name
    is bound to something else refuses (`refactor.retarget-shadowed`). Tests: shadowing, import aliases, accessors,
    TS merged declarations. (codex)
30. **`Literal` probe refinements**: positive identity (the operand's hover type contains the sentinel); a
    diagnostic counts only when its range is the literal or a display holding it as an element or key; a
    verification pass with every candidate set to the sentinel turns any remaining new diagnostic into a blind spot
    (no false refusal at `assert_never`). Rejected (codex): replacing the probe with syntactic contexts (decision
    6). (codex)
31. **Duplicate map entries**: resolved symbols are canonicalised first; one symbol with one intent merges, with
    different intents exits 2 (`refactor.map-duplicate`); a retarget whose target another entry renames writes the
    target's new name. (codex)
32. **Locator grouping by checker symbol**: declarations group only when the checker resolves them to one symbol,
    else `refactor.symbol-ambiguous`; one test per construct (overloads, accessors, `self.x` in several methods,
    conditional definitions, TS merging, namespace reopening). (codex)
33. **Range transform**: a start or end at or inside a replaced span maps to the replacement's start or end; an
    unmappable range warns with `refactor.baseline-ambiguous`. (codex)
34. **TypeScript `Literal` contexts pinned**: the bundled TypeScript 6.0.3 was probed (declaration, typed variable,
    argument, `===`, `case`, typed array element renamed; another union's string, a `string` variable and an `as
    const` local not). Rejected (codex): a further prototype. Tests pin each context plus aliases and imported types.
    (codex)
35. **`--base` errors**: fetch failure falls back to the ref as it stands; only an unresolvable `origin/BRANCH`
    exits 2. Rejected (codex): arbitrary refs, for consistency with `la-affected-tests` and `la-check-conventions`.
    (codex)
36. **Structured finding comparison**: `--base` compares findings by path, template id and parameters other than
    the line, not by printed text. (codex)
37. **Conformance coverage**: paired or neutral cases for shared surfaces (help, `--attr`, map errors, locator
    failures, `--base`), adapter cases for language-only semantics, every case run through both invoking twins.
    (codex)

38. **Merging `origin/main`**: commit the working tree, then merge (no stash, no rebase). Files git merges cleanly
    stay as merged (`shared/findings.yaml`, `shared/cli.yaml`, `compliance.ts`, `test_contract.py` hold both
    sides). Every conflicted file takes `main`'s side (DEV-2292's fixtures, goldens, tests and archived change,
    with `main`'s fixture names); this change's edits to those files are then redone on top (`--name` → `--symbol`, the `dr-mock-lint` and overlay
    changes in `mocks.ts` / `workspace.ts`); generated files are regenerated, never hand-merged (`CONTRACT_HASH` by
    `scripts/sync-shared`; `conformance/INVENTORY.md` is the union of both sides' rows). Files only this change
    owns keep their `Acme` names. Weighed: keeping this branch's `Acme` spelling in DEV-2292's files (re-blesses
    goldens `main` already reviewed, for no behaviour). (default)
39. **New rules return outcomes**: the `Literal` probe, retarget, the compound-name scan and the map engine use
    DEV-2292's outcome model: each returns one outcome per examined site and the one driver files them. In a map,
    "a declaration the rename leaves unchanged" is judged against the whole map's symbol set. Weighed: none; a
    rule with its own reporting path is the shape DEV-2292's decision 35 removed. (default)
40. **Equal strings of a `Literal` rename are always listed**: A) every other string literal whose whole value is
    OLD is a `leftover` with or without `--docs`, except one the checker types by another literal type, which is
    unrelated and unlisted; B) list them only with `--docs`, as the issue's item 6 says. Took A, a change to the
    issue's item 6: one rule with DEV-2292's exact-OLD listing (its decisions 35, 36 and 44), and a stale
    `choices=[...]` is never silent. (user) Unlisted means one criterion in both twins: the position accepts no
    other string (a sentinel is rejected there, by a diagnostic absent before); a position typed `Other | str`, or
    one that already had an error, is listed, since listing never blocks. (codex)
41. **New twin primitives are pinned by shared vectors**: symbol-path parsing, the compound-name word split and
    match (decision 20) and the range transform (decision 33) get `shared/vectors/` files run by both twins; every
    line number this change prints or reads (candidates, `--keep`, `--with`, findings) goes through each twin's one
    line index. Weighed: per-twin unit tests only (two implementations that agree by hand). (default)
42. **One file universe**: the map engine's scans, the `Literal` probe, the compound-name scan and retarget read
    project sources only through each twin's file-universe function, so they see the files `dr-compliance` and
    the blind-spot scan see. (default)
    Tests added for decisions 39, 42 and 44 (codex): a map whose other entry renames the declaration a patch target
    resolves to; a `Literal`, compound-name and retarget run with a file in an excluded directory and (TypeScript)
    one outside every program; a map `--with` / `--without` on a computed-name stand-in.
43. **One probe object**: the Python `Literal` probe extends DEV-2292's probe object (it owns the rewritten text
    and its offset map and returns original-file spans); the sentinel rounds, including the one that tests each
    remaining equal string for another literal type (decision 40), are rounds of that object. Weighed: a second
    sentinel/offset mechanism beside it. (default)
44. **A member declared by a computed name is not a path candidate**: a symbol path names a declaration by its name
    span, and such a member has none, so `--symbol Owner.OLD` on it is `refactor.symbol-unresolved`; it stays a
    stand-in handled by `--without`, and `--with` on it exits 2 with `refactor.computed-stand-in` in a map as in a
    single rename. (default)
45. **`--name` migration covers `main`'s cases and tests**: every conformance case and test `main` added with
    `--name` migrates to `--symbol` with its golden unchanged (30 cases at the merge). (default)
46. **Repeatable `--attr` covers every access form**: with several names, each of DEV-2292's access forms
    (attribute access, the string-member forms, TypeScript element access on an `any` receiver) is reported per
    name in the one scan. (default)
47. **`python.md` wording for decision 40**: "strings equal to a renamed `Literal` member that the checker does not
    type by it (`str` variables, `argparse` `choices`; each listed as a `leftover`)," (user, approved wording)

## Mechanisms

- **Position map**: each refactor yields per-file edit lists, file renames (move-module) and moved spans
  (move-symbol: the moved statement's span to its place in the destination, through a character diff of the moved
  text when the move rewrote it). Ranges map through it by decision 33.
- **Python aligner**: affected files = files the refactor edits, moves or deletes that have entries. Two runs of the
  configured command through `living_architecture.typecheck`'s runner (patch preload included), each appending
  `--outputjson --baselinefile <temp>` and the affected files: one with a copy of the baseline, one with an empty
  baseline. Decision 25 pairs entries with diagnostics; mapped entries are rewritten or moved, the rest kept.
- **TypeScript aligner**: decisions 26 and 27; keys rendered through tsc's non-pretty formatter and parsed with the
  parser `la-typecheck` uses (`lang/tsc.ts`), so they compare byte for byte.
- **`Literal` probe (Python)**: open every project source in the language server; record diagnostics and the hover
  types of every comparison operand, `in` container and `match` subject next to an OLD literal; replace the member
  with a sentinel through `didChange`; collect candidates (decision 30); set every candidate to the sentinel;
  remaining new diagnostics are blind spots. A last round puts a sentinel in each remaining equal string: one that
  draws a diagnostic on itself is typed by another literal type (unrelated), the rest are leftovers (decision 40).
  All rounds run on DEV-2292's probe object (decision 43).
- **Map engine**: resolve every locator (decision 31), build one symbol set, run each rename rule once over the set
  on one snapshot, file each rule's outcomes through DEV-2292's driver (decision 39), merge edits, apply `--keep`,
  then the aligner, then print or write (decision 28).

## Risks / Trade-offs

- [A project that turns `reportArgumentType` / `reportAssignmentType` / `reportReturnType` off blinds the `Literal`
  probe at those sites] → the gate runs with the same config, so such a project already accepts those mismatches;
  the unrewritten equal strings are still listed as leftovers.
- [The bundled TypeScript differs in version from the project's tsc] → mismatched messages leave entries
  unaligned, which is today's behaviour; the parity test pins the matched case.
- [basedpyright changes its baseline auto-pruning] → decision 25's tests run the real checker and fail on a change.
- [Python dry-runs pay two checker runs over the affected files] → only on repos with a baseline listing an affected
  file; the SLayer timing task records the cost.
- [The `Literal` probe checks every project source twice] → comparable to the blind-spot scan; recorded by the
  SLayer timing task.
- [Removing `--name` breaks scripts that use it] → **BREAKING**, named in the release notes; the skills already
  locate by line and column.

## Migration Plan

`--name` → `--symbol` (the declaration's path in `--file`). `dr-mock-lint` keeps its positional form. Release as a
minor version after merge (with DEV-2292's if unreleased), then pin it in SLayer. Archive only after DEV-2292's and
DEV-2289's changes are archived on `main`.

## Approved wording

### plugin/skills/deterministic-refactor/SKILL.md — replaces `## Procedure` and `## Commands` (DEV-2292's approved text)

```markdown
## Procedure

1. **Name the symbols**: each by its file and its path inside it
   (`--file F --symbol Class.method`; also `func.<locals>.inner`,
   `Class.method(param)`, `Alias['value']` for a `Literal` member). Related
   renames go in one rename map: one dry-run, one apply, one gate.
2. **Check the verifier**: run `la-typecheck`. It runs the project's type
   checker in the project env (the one the tests use) against its committed
   baseline, and it must pass before you start. If it prints "nothing to
   check", STOP and tell the user: with no type check there is no guarantee,
   so offer to set one up (`commands.typecheck` and
   `la-typecheck --write-baseline`) first.
3. **Type the receivers** (member renames):
   `dr-compliance --select attr-blindspot --attr OLD <repo>` (one `--attr` per
   old name) lists each receiver the checker cannot type. Type them
   (`la:make-refactor-target-compliant`) until it reports nothing; `dr-refactor`
   refuses a member rename while any remain.
4. **Dry-run** (default):
   `dr-refactor --project <repo> rename --file F --symbol Q --new-name N --docs`,
   or `dr-refactor --project <repo> rename-map MAP --docs`.
   Method renames rename the hierarchy by default. Re-run until it is the rename you want:
   - `stand-in`: a class outside the hierarchy declares `OLD`. `--with PATH:LINE` renames it too
     (a duck-typed implementation: a cache, a fake, a `cast()` target); `--without PATH:LINE` leaves it
     (an unrelated class).
   - `attr-blindspot` on a receiver that cannot be typed (a third-party `Any`): `--allow-blindspots`,
     and tell the user which.
   - a site that must keep the old name (a back-compat test or shim): `--keep PATH:LINE`, or
     `--keep PATH` for a whole file.
   - code still using the back-compat alias of an earlier rename: a `retarget` entry moves it to
     the new name and keeps the alias.
   Show the diff.
5. **Apply**: `--apply` is a GLOBAL flag and goes before the subcommand
   (`dr-refactor --project <repo> --apply rename ...`); trailing it errors.
   It realigns the type-check baseline too; never edit the baseline by hand.
6. **GATE — done only when ALL pass:**
   - `la-typecheck` passes: **no new errors** vs the baseline;
   - `dr-mock-lint <tests>` passes; when the base branch already has findings,
     `dr-mock-lint --base <base-branch> <tests>` reports only the new ones;
   - the full non-integration test suite (`la-config get commands.test`) passes;
   - by hand, only these: each `leftover` line the apply printed, each receiver
     `--allow-blindspots` let through, and the string-only references the language doc lists.
7. Review the diff. The user commits — never commit or `git add -A`.

## Commands

`dr-refactor` subcommands: `rename` / `rename-map` / `retarget` / `move-symbol` /
`move-module`. Dry-run is default; `--apply` writes, baseline included;
`--project` defaults to cwd. Locator: `--symbol Q` (the path inside `--file`;
no match or several exit 2 listing the candidates), `--line [--col]` (1-based)
or `--offset N` (0-based). `rename-map MAP` reads a YAML list of
`{file, symbol, new_name}` or `{file, symbol, retarget}` entries (files relative
to `--project`), resolves every entry before renaming any, and writes all or
nothing. `retarget --file F --symbol OLD --target NEW` rewrites what resolves to
the alias `OLD` to name `NEW`, its target in the same class or module, and leaves
`OLD` in place. `rename`, `rename-map` and `retarget` also take `--with` /
`--without PATH:LINE`, `--keep PATH[:LINE]`, `--allow-blindspots` and `--docs`
(comments, docstrings, strings and prose files: qualified mentions everywhere,
code-marked ones in the declaring files, the rest listed as `leftover`, as are
declarations whose name contains the old name). Move destinations must already
exist, and a `move-symbol` destination is a file of the same language. Run the
repo's formatter afterwards.
```

### plugin/skills/make-refactor-target-compliant/SKILL.md — on top of DEV-2292's approved steps 2 and 4

Step 2, first bullet:

```markdown
   - `dr-compliance --select attr-blindspot --attr NAME <repo>` (one `--attr`
     per name a rename map renames) → `x.NAME`, `getattr(x, "NAME")` and the
     like where `x` is untyped. Each names the receiver to type.
```

Step 4, first bullet:

```markdown
   - the same `dr-compliance --select attr-blindspot` command reports nothing;
```

### plugin/languages/python.md — `## Refactoring`: inserted after DEV-2292's "A rename also rewrites a member named by string …" paragraph

```markdown
A rename of a `Literal` member (`--symbol Alias['value']`) rewrites each string the checker types by that
`Literal`: arguments, assignments, returns, comparisons, `in` tests and `match` cases. It refuses while the
checker needs the old value where no such string stands (a variable assigned it earlier). `retarget` refuses
while a subclass overrides the alias. `--apply` keeps `.basedpyright/baseline.json` aligned by running
`commands.typecheck.python` over the files it changes.
```

and in DEV-2292's "string-only references" bullet, after `config paths,`:

```markdown
strings equal to a renamed `Literal` member that the checker does not type by it (`str` variables, `argparse`
`choices`; each listed as a `leftover`),
```

### plugin/languages/typescript.md — `## Refactoring`: appended to DEV-2292's "A member rename refuses …" paragraph

```markdown
A rename of a string-literal type member (`--symbol Kind['value']`) rewrites every string whose contextual type
is that union. `--apply` keeps `.tsc-baseline.json` aligned: an entry whose message names a renamed symbol
follows it.
```
