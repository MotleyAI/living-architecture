## Context

See proposal.md for the motivation. Today a string is linked to a renamed member only by hand-written rules: the
call forms of `string_member_calls`, the keyed dict targets, the dotted patch targets. Every other equal string is a
`leftover`, and a name standing where a rule expects a literal is never followed. Each form of the issue is one more
instance of that shape, so adding a handler per form would leave the class open.

Architecture principles that bind this change (`architecture/system.arc42.md`):

1. Twins: every behaviour both languages share is identical; the conformance corpus decides.
2. Forms, check ids and texts come only from `shared/`.
3. All language-specific code stays in `refactor` (and `lang`).
4. Nothing imports or executes target-repo code: every link here is resolved from source and from the checker.

No model or arc42 edit, no new import edge. The spec stays attached to `refactor`.

Measured on `main` at `7d27e9c4` while planning:

- TypeScript: `const X = 'formula'` returned from a function typed by the renamed union, `const v = 'formula'` passed
  to a typed parameter, and `SECTIONS = ['columns'] as const` read by `d[s]`, each end in exit 0 with a `leftover`,
  and `tsc` fails after `--apply`. TypeScript never prints `literal-unresolved`.
- basedpyright keeps the literal type of an unannotated module constant, class constant, twice-bound local,
  conditional expression and of a loop variable over a tuple of literals. So each of these reads type-checks before
  the rename and draws a new diagnostic under the probe.

## Goals / Non-Goals

**Goals:**

- One mechanism per twin for "a string names a member", driven by registry data.
- One resolver per twin for "a name holds a literal", used by the literal-member rename and the member rename.
- TypeScript refuses where the edited program no longer checks.

**Non-Goals:**

- Strings with no static link: a helper taking a field name, an `Enum` whose values equal field names.
- Keys flowing through `**kwargs` helpers; untyped document bodies and stored documents.
- Pydantic v1 `@validator` (approved scope cut, decision 6).
- A module rename through a module receiver, as for dotted targets today.
- `frozenset(...)` as a source display (approved scope cut, decision 14).

## Decisions

1. **Forms are registry data; one source resolver serves both rename kinds.** Alternative: one handler per form in
   each twin. Taken because the handlers are the structural cause, and principle 2 already puts the call forms in
   `shared/languages.yaml`. `(default)`

   Registry shape (python section; exact keys are settled with the first failing contract test):
   - `string_member_calls` entries gain `silent: true` (`hasattr`) and `default: <position>` (`getattr`: the argument
     whose presence makes a miss raise no error).
   - `name_decorators`: `{call, module, qualname}` for `field_validator` and `field_serializer`; every positional
     argument is a name.
   - `name_reads`: `{attribute, module, qualname}` for `model_fields` and `model_fields_set`, with the read shapes
     each supports (`subscript`, `get`, `in`).
   - `name_class_values`: `__slots__` (shapes: display element, whole string, dict key) and `__match_args__`
     (display element).
   - `compliance_checks` gains `string-blindspot` in both languages.

   Each twin validates the keys it reads on load and fails as a contract error on a malformed entry.

2. **Constant tuple: rewrite the element on a proven use, list the other reads.** Options: (A) rewrite on one
   proven use, `mixed-target` on a conflicting proven use, list other reads; (B) rewrite only when every read is
   proven, else refuse; (C) never rewrite, dedicated blind spot. A taken: without the rewrite the code is certainly
   broken, with it the only risk is listed. `(user)`

3. **A string-named untyped access is its own kind, with a silent variant.** Options: one kind plus a variant for a
   call whose miss raises no error; one kind only. The variant taken: only `getattr(…, default)` and `hasattr` miss
   silently, and those are the sites to find. `(user)`

4. **Approved wording.** `(user, approved wording)` The rendered lines:

   ```
   pkg/m.py:14: string-blindspot: getattr(x, 'columns') — x is Any, so a rename of .columns is unverifiable
   pkg/m.py:18: string-blindspot: getattr(x, 'columns', …) — x is Any, so a rename of .columns is unverifiable and a miss raises no error
   pkg/m.py:31: unverified-read: SECTIONS holds 'columns', rewritten at pkg/m.py:20; this read is not proven to name the renamed member
   ```

   and the two changed texts:

   ```
   compliance.attr-required:   '--select {check} needs --attr NAME'
   compliance.attr-unselected: '--attr needs attr-blindspot or string-blindspot among the selected checks'
   ```

   Templates that render them:

   ```
   compliance.string-blindspot:        '{path}:{line}: string-blindspot: {site} — {receiver} is {type}, so a rename of .{attr} is unverifiable'
   compliance.string-blindspot-silent: '{path}:{line}: string-blindspot: {site} — {receiver} is {type}, so a rename of .{attr} is unverifiable and a miss raises no error'
   refactor.unverified-read:           '{path}:{line}: unverified-read: {name} holds {old!r}, rewritten at {source_path}:{source_line}; this read is not proven to name the renamed member'
   ```

   `{site}` replaces the `{call}({receiver}, {attr!r})` first shown, for the two cases raised with the spec and
   approved with it: `, …` appears only when the call passes further arguments (so `hasattr(x, 'columns')` has
   none), and a TypeScript element access prints `x['columns']`. `(default)`

5. **TypeScript: full parity.** Options: (A) source following, the in-memory check with `literal-unresolved`, and
   the tuple rule; (B) refuse only; (C) Python only. A taken: one contract for both languages, and TypeScript stops
   exiting 0 on a program it broke. `(user)`

6. **Forms next to the issue's list.** In: the other reads of `model_fields` (`.get`, `in`, `not in`) and
   `model_fields_set`; `__match_args__`; a class-level constant as a source. Out: Pydantic v1 `@validator`
   (deprecated, unused in the repos this serves). `(user)`

7. **The listing covers every rewritten source literal, `Literal` constants included.** Alternative: only the
   tuples of names. Taken: one rule for one mechanism. `(user)`

8. **Defaults accepted with the form list.** Field-name strings are rewritten despite an alias; only the matching
   decorator argument changes and `"*"` is untouched; a validator on a base without the field stays a `leftover`;
   a chain of once-bound names is followed and a conditional value is not; a module receiver is covered for every
   registered string-member form. `(default)`

9. **`string-blindspot` is a check id of its own.** Codex found that the spec requires every printed compliance
   kind to be a check id. Options: (A) register it, so `--select attr-blindspot` reports accesses only and
   `--select string-blindspot` the string forms; (B) keep the kind `attr-blindspot` and change only the text; (C)
   exempt the kind in the spec. A taken. `(codex)`, choice `(user)`

10. **Sources are literals in project source files only.** A dependency, a `.pyi` stub or a `.d.ts` file is never
    rewritten: the site stays `literal-unresolved` (literal rename) or a `leftover` (member rename). `(codex)`

11. **A module receiver resolves by the dotted-target rules.** The object argument's dotted path, expanded through
    its file's imports, resolves to exactly one project module with the existing static resolver, then `M.OLD` as a
    dotted target. Unresolved is a `leftover` with `{where}` `patch target`. `(codex)`

12. **Class-body values are owned by lookup on the containing class.** This covers a subclass's `__match_args__`
    naming an inherited attribute. One lookup lands in one class, so no mixed case arises here. `(codex)`

13. **Decorators and reads match by resolved declaration.** `module` + `qualname`, as the call forms do; an aliased
    import matches, a same-named project function does not. `(codex)`

14. **A loop yields a literal source set.** Only elements exactly OLD are rewritten. `frozenset(...)` is a call, not
    a display, and is not a source. `(codex)`

15. **Supported bindings are a closed list.** A plain or annotated assignment of one name, a `for` or comprehension
    target of one name (TypeScript: `const`, a once-assigned `let`, `for…of`, the first parameter of an array-method
    callback). Everything else has no sources. `(codex)`

16. **The TypeScript check compares before and after.** Only diagnostics absent before the edit count, across every
    project holding an edited file, positions mapped back through the edits. The check runs in process on the
    language service the rename already holds; a thrown error ends the run as any internal failure does, before
    anything is written. `(codex)`

17. **New rewrites refuse on a collision.** A decorator, class-body value or source display that already holds NEW
    prints `refactor.name-conflict` and writes nothing. `(codex)`

18. **Coverage is per syntax and callee.** tasks.md names each conformance case; each twin has structural tests of
    the registry keys; `sync-shared --check` and `conformance-cross` are tasks. `(codex)`

19. **Rejected: make every unverified read a refusing blind spot.** `rejected (codex)`: decisions 2 and 7 chose
    the listing.

20. **Rejected: split the TypeScript work into its own change.** `rejected (codex)`: decision 5; the probe results
    above are the reason it belongs here.

21. **An untyped use through a name is a read, not a blind spot.** `getattr(x, s)` with `x: Any` is listed by
    `unverified-read` when the source is rewritten and is otherwise silent, as a non-literal member argument is
    today. `(default)`

22. **The two refusing literal scenarios keep their titles.** OpenSpec does not let a MODIFIED requirement drop a
    scenario. "Narrowed local refuses" and "Blind spot in a file without the string" now describe a twice-bound
    name, which still refuses; the once-bound cases they used to describe are new scenarios that rewrite.
    `(default)`

## Risks / Trade-offs

- [A rewritten source changes a read the tool cannot prove] → every such read is listed (`unverified-read`); a
  conflicting proven use refuses (`mixed-target`); `--keep` on the source line leaves it.
- [`--select attr-blindspot` output shrinks for existing callers] → marked BREAKING in the proposal; the rename's
  refusal still covers both checks; minor version bump.
- [Many goldens change kind] → 43 cases mention `attr-blindspot`; only those printing a string form change. Each
  golden diff is reviewed against "the same line with the new kind and site", nothing else.
- [The TypeScript in-memory check costs a second program check] → it runs only for a literal-member rename and only
  over projects holding an edited file.
- [Static scope analysis misjudges a binding] → the supported bindings are a closed list; anything else has no
  sources, which falls back to today's behaviour.

## Migration Plan

Released as a minor version of both packages and `plugin.json`. Callers selecting `attr-blindspot` to see string
forms add `string-blindspot`.
