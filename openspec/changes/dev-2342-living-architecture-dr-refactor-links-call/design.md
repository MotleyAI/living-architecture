## Context

See proposal.md for the motivation. The four cases reduce to two structural causes.

1. A site is linked to the renamed declaration only when the checker's go-to-definition lands on it, and a site that is
   not linked is not reported. Measured on `main`:
   - Item 19: go-to-definition on a keyword of a decorated callee returns nothing, because the callee evaluates to the
     decorator's return value. The checker's signature of that value still names the parameter for `@contextmanager`,
     `@asynccontextmanager` and a `ParamSpec`-typed decorator; for `@functools.lru_cache` it is
     `(*args: Hashable, **kwargs: Hashable)`.
   - Item 20: a keyword `q(old=…)` binds `q`'s `**kw`, which no rule follows into `Query(**kw)`.
   - Item 13: the checker types `list(getattr(planned, "xs", ()) or ())` as `list[Never]` (the `Any` is lost against the
     empty-tuple default), so the loop variable is `Never`, and the scan counts only `Unknown` and `Any`.
2. The hierarchy rule joins every declaration whose roots meet, so `A.__init__` and `B.__init__` join through
   `Base.__init__` (item 21). Constructors are not called through a base-typed receiver.

Principles of `architecture/system.arc42.md` that apply: 1 (twins: the Python forms are adapter cases, the constructor
rule is a paired case), 2 (every new or changed text lives in `shared/`), 3 (the code stays in `refactor` and `lang`),
4 (the signature proof runs in the checker on text held in memory; no target-repo code runs). `python.refactor` has no
arc42 file of its own. No model, arc42 or `index.yaml` edit is needed.

## Goals / Non-Goals

**Goals:**

- Every `old=` keyword and every `x.old` read of a parameter, field or member rename is proven linked, proven unrelated,
  or listed as a blind spot.
- One flow rule for `**kwargs` with three sink kinds (keyed class, function, constructor), not one rule per sink.
- Constructor parameter renames stay in their class in both twins.

**Non-Goals:**

- `**kwargs` flows through local copies and aliases (`x = kw`, `dict(kw)`, `kw.copy()`, `update`, `|`) and through
  dict-building helpers (`kw` as a plain argument, returned dicts): they are reported, not followed.
- An opaque mapping unpacked into a call (`f(**mapping)`, `K(**mapping)`): unchanged and not reported, as today.
- A `dr-compliance` check for unlinked keywords.
- A list of known signature-preserving wrappers.
- An opt-in flag for spreading a constructor parameter rename.
- `Unpack[TypedDict]` kwargs, dict parameters passed positionally, string-named members with a static link.

## Decisions

1. **`**kw` flow forms: direct forms only** (the sinks, the key forms, `{…, **kw}` at a sink, chains of carriers).
   Weighed: plus local copies and aliases; plus dict-building helpers. Taken because each form is provable from its
   shape, while a wrong key rewrite type-checks clean (Pydantic ignores extra keys). A survey of SLayer's `**kw`
   functions put the direct forms far ahead of the others. (user)
2. **The flows apply to parameter renames too**, with function and constructor sinks, which changes the scenario
   "Unresolved keyword sites are unchanged". Weighed: fields of keyed classes only, as the issue words it. Taken because
   the flow is one mechanism and the parameter case fails at runtime with nothing reported. (user; approved extension)
3. **A callee whose signature the checker types without the parameter is a blind spot**, renamed with
   `--unsure include`. Weighed: rewriting when the callee name resolves to the decorated `def` (a guess that type-checks
   clean when wrong); a list of known wrappers in `languages.yaml`. (user)
4. **`Never` joins the unverifiable receiver types.** Weighed: any access the checker links to no declaration, which
   also reports existing type errors and gated branches. (user)
5. **A keyword on a callee typed `Unknown`, `Any` or `Never` is a blind spot**, as an access on such a receiver is.
   Weighed: only the two cases with a provable link to the declaration. (user; approved extension)
6. **A keyword is linked by a proof from the checker**: its signature at the call binds `old` before and `new` after
   the renamed declarations are renamed in memory. Weighed: "the callee name resolves to the `def` and the signature has
   `old`", which accepts a wrapper whose same-named parameter is not the declaration's. The proof reuses the run's probe
   round (an export with files opened as modified texts), with a new position fact: the names a call's signature binds
   by keyword, per callable alternative. (default)
7. **Constructors have no hierarchy and no opt-in flag**: a `rename-map` entry per constructor renames several.
   Weighed: a `--with`-style opt-in. (default)
8. **An unresolved or mixed carrier lists every `F(old=…)`, related to the renamed class or not**, as untyped receivers
   are listed. Weighed: listing only carriers that mention the renamed class, which is a guess. (default)
9. **`dr-compliance` does not report unlinked keywords**: the verdict needs the renamed declaration, which `--attr NAME`
   does not name. Weighed: a new `--select` check. (default)
10. **`{receiver}` keeps the parentheses written around it** (`(g or planned).old` was shown as `g or planned.old`).
    (default)
11. **In every callable alternative**: a keyword is linked only when each overload and each union member the checker
    considers at the call binds `old` before and `new` in the same parameter after; otherwise it is unlinked. (codex)
12. **Requirements are stated by fact, not by decorator**: "a callee whose signature the checker types without the
    parameter". `lru_cache` is the fixture, as the shipped basedpyright types it. (codex)
13. **A constant key of a dict literal unpacked into a carrier** is treated like the keyword `F(old=…)`: rewritten for
    a renamed verdict, an unlinked keyword for a mixed or unresolved one. (codex)
14. **Carrier verdicts are a join over sinks**: any unresolved gives unresolved; renamed with other gives mixed; all
    renamed gives renamed; all other gives other. A sink that is a carrier yields that carrier's verdict; carriers in a
    call cycle are unresolved. (codex)
15. **A decorated callee is tied to the renamed declaration by go-to-definition on the callee expression**: aliases and
    bound methods followed, a class through the constructors the checker resolves, any member of a union. (codex)
16. **A class declaring both `__init__` and `__new__` with a parameter `old`**: Python passes the keyword to both, so it
    is rewritten only when the run renames both parameters to the same name; with only one renamed it is an unlinked
    keyword, whichever constructor the checker resolves it to. (codex; revised in review)
17. **The unresolved-carrier fixture holds one function per unresolved use**, a nested scope shadowing `kw` (which stays
    resolved) and a two-carrier cycle. (codex)
18. **`scripts/sync-shared` and `conformance/INVENTORY.md` are explicit tasks.** (codex)
19. **The out-of-scope line "keyword-only parameters as such" is dropped**: the generic parameter rules cover them.
    (codex)
20. rejected (codex): "the plan does not update the spec". The delta spec of this change does.
21. rejected (codex): reporting an opaque `F(**mapping)` into a carrier. An opaque mapping at a keyed sink is not
    reported today, the issue does not ask for it, and it would list every `**mapping` call of the project. (user)
22. **Approved wording**, each (user, approved wording):
    - `refactor.unlinked-keyword: '{path}:{line}: unlinked-keyword: {callee}({old}=...) — the checker does not link {old}= to the renamed declaration, so a rename of {old} is unverifiable'`
    - `refactor.blindspots: '{count} blind spot(s) of {names}: type or resolve them, or pass --allow-blindspots'`, with
      `{names}` `.formula` for a member and `models=` for a keyword, joined by `, `.
    - `refactor.unsure-warning: 'WARNING: --unsure=include also renames occurrences the checker cannot resolve; it may rewrite unrelated attributes or keywords of the same name.'`
    - `--allow-blindspots` help, in all three places of `shared/cli.yaml`:
      `'list the blind spots of the old name (untyped receivers, unlinked keywords) and rename anyway (default: refuse)'`
    - `plugin/skills/deterministic-refactor/SKILL.md`, step 4, a new bullet after the `attr-blindspot` bullet:

      ```
         - `unlinked-keyword`: a call keyword `OLD=` the checker cannot link to the renamed parameter or field (a
           decorator that erases the signature, a `**kwargs` helper that copies its dict or passes it on). Read each
           listed call: `--unsure include --allow-blindspots` renames them, `--allow-blindspots` alone leaves them.
           Tell the user which.
      ```

    - The same file, step 6, last gate bullet: `each receiver `--allow-blindspots` let through` becomes
      `each receiver and keyword `--allow-blindspots` let through`.
    - `docs/deterministic-refactoring.md`, after the sentence on untyped receivers: "A parameter or field rename
      refuses the same way while a call keyword of the old name cannot be linked to it."

## Risks / Trade-offs

- [The checker's signature of a call is read from basedpyright internals in the export hook] → the hook is already
  pinned to verified basedpyright versions and refuses any other; the new fact is covered by the decorated-callee cases,
  which fail if a version types these decorators differently.
- [Parameter and field renames can now refuse where they proceeded] → the lines name each site; `--keep`,
  `--allow-blindspots` and `--unsure include` are the existing ways through, and the skill describes them.
- [A rename of a common name lists unrelated calls on untyped callees and unresolved carriers] → the same cost member
  renames already carry for untyped receivers; typing the callee removes the line.
- [The probe re-types files that depend on the renamed declarations] → one extra export per run, only when an `old=`
  keyword is unresolved, and its result is cached with the index.
- [`refactor.blindspots` changes its placeholder] → the value keeps the leading `.` for members, so existing goldens are
  byte-identical; callers that format it move from `attr=` to `names=`.
