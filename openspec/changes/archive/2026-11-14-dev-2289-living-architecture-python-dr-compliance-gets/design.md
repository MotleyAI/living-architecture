## Context

See proposal.md for the motivation. Python's `dr-compliance` checks are AST checks in
`living_architecture.refactor.compliance`; only `--attr` starts the bundled basedpyright language server. The
TypeScript twin's `explicit-any` reports every `AnyKeyword` node, so in TypeScript a syntactic check is already
exact. In Python `Any` is an ordinary name, so the check must resolve names.

There is no structural cause behind the gap: check sets are per language by design ("Compliance check sets are per
language"), and Python simply lacks this check.

**Architecture.** The principles of `architecture/system.arc42.md` that apply:
1. Twins — the new conformance cases decide; TypeScript's output stays byte-identical.
2. Texts and parameters come only from `shared/` — the template is `findings.yaml`'s, the spellings `Any` /
   `object` are `languages.yaml` facts.
3. Language-specific code lives only in `lang` and `refactor` — the check lives in `python.refactor`, reusing
   `lang`'s Python import-resolution helpers where they fit (the `refactor -> lang` arrow exists).
4. Tools never import or execute target-repo code — resolution parses source only, including re-exported modules.

No model or arc42 change. The behaviour attaches to the existing `refactor` spec, owned by `python.refactor`.

## Goals / Non-Goals

**Goals:**
- Report every written `Any` reference in a Python file, one finding per site, in the default check set.
- Resolve spellings, aliases-on-import, module aliases and first-party re-exports from source alone.

**Non-Goals:**
- Following value aliases (`A = Any; x: A` reports only line `A = Any`).
- Statement-order (flow-sensitive) resolution; the scope's bindings decide.
- Re-exports through third-party packages or stdlib modules other than `typing` / `typing_extensions`.
- PEP 695 syntax on interpreters that cannot parse it: such a file gets `parse-error`, as for every check; no
  conformance case uses PEP 695.
- A version bump; it happens at release.

## Decisions

1. **Resolving `Any`: in-file AST resolution plus static following of first-party re-exports.** Weighed: AST only;
   basedpyright's `reportExplicitAny` through the language server; the union of both. A probe showed basedpyright
   misses `t.Any`, reports `Alias = Any` twice (alias name and `Any`), and would start the language server on every
   default run. Static following of first-party re-exports closes the one gap AST-only leaves (a project's own
   `compat` module) without the checker. (user)
2. **`explicit-any` joins Python's default set**, after `unannotated-attr`. Weighed: opt-in through `--select`.
   The diff-compliance sweep runs only the default set, so opt-in would miss the issue's goal; TypeScript parity.
   (user)
3. **Every reference that resolves to `Any`, not annotations only.** This extends the issue's "annotation" wording:
   `cast(Any, …)`, alias values, `TypeVar` bounds, generic calls and bases blind a rename just as annotations do, and
   TypeScript reports `as any` too. (user)
4. **One shared, parameterised template** with two new language facts, `any_type` (`Any` / `any`) and `top_type`
   (`object` / `unknown`), over a separate Python template. (user, approved wording):
   ``compliance.explicit-any: '{path}:{line}: explicit-any: an `{any}` type — use a real type or `{top}`'``
5. **`plugin/languages/python.md` fix line** (user, approved wording):
   ``- `explicit-any` → a real type (a dict of known keys becomes a `TypedDict` or a Pydantic model), or `object`
   narrowed where it is used.``
6. **Shadowing:** a name resolves to `Any` only when every binding of it in its resolving scope imports `Any`.
   (default)
7. **Strings and type comments:** forward-reference strings and `# type:` comments are read; other strings are not.
   (default)
8. **First-party root:** the parent of the topmost `__init__.py` package chain above the importing file; an
   unresolvable module never resolves to `Any`. (default)
9. **The "Language-specific id" scenario and `compliance-select-other-language-check` switch to `tsconfig`**, which
   stays TypeScript-only. (default)
10. **No version bump in this PR.** (default)
11. PEP 695 syntax follows Python's annotation scopes where the interpreter parses it: type parameters bind in their
    own scope, which holds bounds, constraints, annotations and class bases, and sees an enclosing class's names. On
    Python 3.11 such a file gets `parse-error` like every check, so no conformance case uses it; unit tests skip
    below 3.12. (codex)
12. Resolution follows Python's real scoping, not statement order: annotations are often deferred, so a scope's
    bindings decide. Function locals, class scope (visible to a method's parameter annotations and decorators, not
    to its body), comprehensions, `global` / `nonlocal`, except-handler and match bindings are each tested,
    and a `try`/`except ImportError` pair that binds `Any` both ways resolves. (codex)
13. A string is read only as a forward reference — a whole annotation or an element of a type expression's
    subscript — never as a `Literal[...]` argument nor `Annotated[...]` metadata. (codex)
14. Type comments: assignment and argument comments parse as expressions, signature comments in `func_type` mode;
    `# type: ignore` and unparsable comments are skipped silently. (codex)
15. First-party resolution is the defined rule in the spec: `<root>/a/b.py` or `<root>/a/b/__init__.py`, directories
    without `__init__.py` allowed below the root, relative imports against the file's package, star imports through
    a literal `__all__` else every public name, `__init__.py` re-exports followed, cycles end unresolved. (codex)
16. Aliases are not followed: the site is where `Any` is written, as TypeScript's `type A = any`. (codex)
17. Both twins' contract tests pin the new facts; a Python test pins the `Any` / `object` rendering; the unchanged
    TypeScript goldens pin TypeScript. (codex)
18. `compliance-all-checks` and its fixture stay unchanged as the "no `Any`, output unchanged" proof, except that
    findings now print in line order (a file's findings were sorted as text, putting line 16 before line 4); a new
    default-run case (no `--select`) shows `Any` reported. (codex, user)
19. `typing` / `typing_extensions` always mean the real modules, even with a first-party module of that name; tested
    with a local `typing.py`, a third-party re-export and a rebound module alias. (codex)
20. Rejected (codex): narrowing the check to annotations only — decision 3 is the user's.
21. Rejected (codex): asserting that a missing template parameter fails — that is the existing `message()`
    behaviour, which this change does not touch.
22. Rejected (codex): an extra forwarding case for Python `explicit-any` through the npm twin — CI's
    `scripts/conformance-cross --twin` already runs every Python adapter case through both twins.

## Risks / Trade-offs

- [A rebinding of `Any` after use, in the same scope, hides the use] → Deliberate (decision 6/12); real code does not
  rebind `Any`, and order-insensitivity is what deferred annotations need.
- [Default runs on existing Python repos gain findings] → Intended; the sweep exists to remove them.
- [Import-root heuristic misjudges an unusual layout] → The miss is a false negative only; the rule is spelled out
  in the spec and tested on flat and `src/` layouts.
