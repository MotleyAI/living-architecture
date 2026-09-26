---
name: make-refactor-target-compliant
description: Use BEFORE renaming a Python symbol/attribute to make its blast radius verifiable — annotate the untyped code that might reference it (unannotated params/vars that could hold the class, classes with matching attribute names, subclasses missing @override) so the post-rename type-check gate is sound.
---

**Preflight:** run `la-doctor --expect 0.1.1` once per session before using any `la-*` or `dr-*` command; if it fails, stop and show the user its output.

# Make a refactor's blast radius compliant

A rename is only provable over code the type checker can resolve. This closes
the blind spots first, so the `la:deterministic-refactor` gate afterwards is sound.

## Steps

1. **Identify the target:** the symbol, and for a member rename the attribute
   NAME and its owning class.
2. **Enumerate blind spots (checking machinery):**
   - `dr-compliance --attr NAME <repo>` → `attr-blindspot` sites: `x.NAME` where
     `x` is an unannotated parameter. Each names the parameter to annotate.
   - LSP `workspaceSymbol` / `findReferences` on the class and on NAME to map
     the real reference set; compare against what the checker resolves today.
   - Grep `\.NAME\b` for accesses on receivers the checker treats as `Any`
     (untyped locals, results of untyped calls) — the "right-looking" names.
3. **Make them resolvable (do NOT rename yet):**
   - Annotate the flagged parameters/variables with the owning class (or its
     `Protocol`); annotate the class's own attributes.
   - Add `@typing.override` to overrides in the hierarchy.
   - Spec any mocks of the class (`dr-mock-lint`).
4. **Re-check until the blast radius is typed:**
   - `dr-compliance --attr NAME <repo>` reports no `attr-blindspot`;
   - the project's type checker is clean over the touched files.
5. **Then run `la:deterministic-refactor`.** Every real reference is now
   type-visible; anything left is a genuinely dynamic string reference, which
   that skill's grep step catches.

The `attr-blindspot` report and the `\.NAME\b` grep are heuristics for *finding*
candidates. The guarantee still comes from the type checker after the rename —
this skill's job is to shrink the checker's `Any`-typed surface over the blast
radius to zero.
