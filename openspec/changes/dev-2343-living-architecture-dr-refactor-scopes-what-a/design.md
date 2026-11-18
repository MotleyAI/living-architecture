## Context

See proposal.md for the motivation. Today a `--docs` mention is decided per entry in the Python twin (each
`SymbolRename` classifies the mentions of its own old name, and two entries' edits meet in `RenameMap.merged` as a
`refactor.map-conflict`) and per old-name group in the npm twin (a group with two new names lists every mention). In
both, a code-marked bare mention is scoped by file only (`declaring`). The symptoms of DEV-2340 items 9 and 22 and
the twin difference are instances of one structural cause: the mention has no owner finer than the file, and it is
not resolved once over the run.

Architecture: no model or arc42 change. System principles 1 (twins identical, the conformance corpus decides), 2
(flags, findings and config keys only from `shared/`) and 3 (language-specific code only in `lang` and `refactor`)
apply. The spec stays in the existing `refactor` capability.

## Goals / Non-Goals

**Goals:**

- One mention resolution over all entries of a run in each twin: a mention gets exactly one entry or is listed, so a
  docs `map-conflict` cannot arise and the twins cannot disagree on it.
- Listed mentions become answerable per line (`--docs-pick`), kept literals by class (`--keep-literal`), and
  mini-language strings by declaration (`refactor.string_forms`).

**Non-Goals:**

- Per-word sense carve-outs for `--docs` and strings with a static link to a member (out of scope in the issue).
- Code-marked mentions in a subclass declared in a non-declaring file stay listed.
- No `KEY=VALUE` form for `--keep-literal`, no whole-file pick, no column in a pick, no config form of the literal
  keep, no callee declarations for untyped bodies.

## Approach

- **Mention resolution.** The scan of mentions stays per old name. The decision moves to one resolver that sees
  every entry's renamed declarations: for each mention it computes the candidate entry (qualified owner, owning
  class, or the file's declarations) and returns a rewrite for one entry or a listing. In Python this runs once per
  old name over the entries sharing it, not once per entry; in the npm twin it replaces the group's
  `newName !== null` shortcut. Class spans come from the AST (Python: `ClassDef` with decorators; TypeScript: the
  declaration node and `getJSDocCommentsAndTags`), member lookup from the class graph (Python) and the checker
  (TypeScript), both already used by the string-member rule.
- **Picks.** A pick is resolved at site resolution, beside keeps, over the final listed mentions: it turns a
  listing into an edit. Keeps are applied after picks, so a kept line drops the picked edit.
- **Literal keep.** The matching literals' spans are collected per file that holds an edit, blind spot or leftover
  (a syntactic scan), and filtered by span overlap in the same place `--keep` filters, before the conflict phase.
- **String forms.** A rule of the rename of a class or module-level symbol, run with or without `--docs`, over the
  raw source text of each string region the mention scanner already yields. Its sites are recorded as handled so the
  `--docs` mention scan skips them. Patterns are validated at config load by the existing regex-subset checker
  (`contract/regex`), plus the one-capturing-group count.

## Decisions

1. **Mentions resolve once over all entries; an undecided mention is listed, not refused.** Options: keep Python's
   refusal (`map-conflict`), or list as the npm twin does. Taken: list, because it matches the existing simple-name
   collision rule and makes the twins agree. `(default)`
2. **The owning class is the innermost enclosing class whose lookup finds OLD; the file-level fallback requires
   every module-level and class-member declaration of OLD in the file to be renamed to one name.** Options: the
   nearest enclosing class regardless of its members, or the first that has the member. Taken: the first that has
   it, so a helper class's docstring falls back to the file. `(default)`
3. **A TypeScript class owns its JSDoc; a Python class does not own comments above it.** A Python docstring sits
   inside the class; a TypeScript one sits before it. `(default)`
4. **The string-opening code mark is removed.** The issue's Outcome states that a plain word in a string is
   rewritten only when qualified. `(default, from the issue)`
5. **The pick acts on any listed mention: `--docs-pick PATH:LINE[=ENTRY]` on `rename` and `rename-map`.** Options:
   conflict sites only on `rename-map`, or any listed mention. Taken: any listed mention. `(user)`
6. **The pick requires `--docs`; an unmatched or ambiguous pick refuses with exit 2; keeps win over picks.**
   `(default)`
7. **Declared forms: `refactor.string_forms` in config for mini-languages; untyped bodies declined.** Options:
   decline both; forms only; forms plus callee declarations (`refactor.python.keyed_arguments`). Taken: forms only.
   A body can be typed, and a callee declaration without a discriminator would be wrong for a REST or MCP function
   that carries many schemas. `(user)`
8. **A form pattern has one unnamed capturing group and never matches a literal part holding a non-ASCII
   character.** The shared regex subset rejects named groups and is twin-identical on ASCII only. `(default)`
9. **Forms apply to renames of classes and other module-level symbols only, with the simple-name collision rule.**
   A member named in a mini-language string names no owner. `(user, part of decision 7)`
10. **The literal keep is the flag `--keep-literal KEY`, key name only.** Options: flag, config
    (`refactor.keep_literals`), or both. Taken: the flag, because a migration fixture and a current-version document
    both carry the key and only the run can tell them apart. `(user)`
11. **`--keep-literal` matches TypeScript object literals as well as Python dict displays.** One flag surface in both
    twins. `(default)`
12. **An unmatched `--keep-literal` warns and the run goes on**, as a directory keep does. `(default)`
13. **The no-owning-class rule applies to code-marked mentions only.** Codex finding 1: the plan's wording could be
    read as rewriting any bare module-level word. `(codex)`
14. **The selectable site of a pick is the line; no column.** Codex finding 2 asked for a column or occurrence
    discriminator. `rejected (codex)`: `--keep` and `--without` select by line, leftover lines print no column, and
    the spec now states that a pick rewrites every listed mention of the line.
15. **Forms match the raw source text between the quotes; escapes are not decoded.** Codex finding 3: decoded
    matching cannot map offsets back to source identically in both twins. `(codex)`
16. **The `--docs` requirement is MODIFIED in the delta, not only the goldens.** Codex finding 4. `(codex)`
17. **`--keep-literal` filters edits, blind spots and leftovers by span overlap with the literal.** Codex finding 5.
    `(codex)`
18. **A TypeScript class owns only the JSDoc comments the compiler attaches to its declaration**, not every leading
    comment. Codex finding 6. `(codex)`
19. **A lookup that cannot be completed lists the mention; TypeScript lookup covers every merged declaration.** Codex
    finding 7. `(codex)`
20. **Added scenarios:** several mentions and two old names on a picked line, disagreeing picks, a kept line under a
    pick, a key collision inside a kept literal. Codex findings 8 and 9. `(codex)`
21. **The schema, `config.yaml`, `cli.yaml`, `findings.yaml` and both snapshots are tasks of their own.** Codex
    finding 10. `(codex)`

### Approved wording

Finding texts for `shared/findings.yaml` `(user, approved wording)`:

- `refactor.pick-needs-docs`: `--docs-pick needs --docs, so nothing was refactored`
- `refactor.pick-unmatched`: `--docs-pick {site} names no listed mention, so nothing was refactored`
- `refactor.pick-ambiguous`: `--docs-pick {site}: entries {first} and {second} both mention {old} here; add =ENTRY, so nothing was refactored`
- `refactor.keep-literal-unneeded`: `WARNING: --keep-literal {key} matches nothing this rename touches`

Not yet approved, to be shown to the user before they are written: the `--docs-pick` and `--keep-literal` help
texts in `shared/cli.yaml`, the `refactor.string_forms` description in the schema, the `shared/regex-subset.md`
edit, and the wording of `plugin/skills/deterministic-refactor/SKILL.md`.

## Risks / Trade-offs

- [A project relies on the string-opening rewrite] → those strings are now listed, so the run names every one, and
  `--docs-pick` rewrites them.
- [A form pattern matches by simple name, a declared convention and not a proof] → a collision lists instead of
  rewriting; the rewrite shows in the diff.
- [`--docs-pick` can respell a plain English word] → only on a line the user named, and it shows in the diff.
- [Goldens pinning the old behaviour change] → each is updated deliberately with the reason in the commit message,
  after the user approves aligning that file (the `/la:pr` stopping policy).
