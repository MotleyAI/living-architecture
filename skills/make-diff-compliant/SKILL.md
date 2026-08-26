---
name: make-diff-compliant
description: Use to bring exactly the Python files a PR/branch touches up to the deterministic-refactor compliance conditions (typed, @override, spec-bound mocks), so a future refactor over them is verifiable. Scoped to the diff — grows compliance monotonically, no repo-wide migration.
---

# Make the diff compliant

Raise compliance one PR at a time instead of a big-bang migration: every diff
leaves the files it touched fully refactor-verifiable.

## Steps

1. **Changed Python files:**
   `git diff --name-only <base>...HEAD -- '*.py'` (base = the PR's target branch).
2. **Report:** `dr-compliance <changed files>` → `untyped-def` /
   `unannotated-attr` / `mock` violations.
3. **Fix each, within the changed files:**
   - `untyped-def` → add param and return annotations.
   - `unannotated-attr` → annotate the attribute (class-body `x: T`, or
     `self.x: T = ...`).
   - `mock` → bind to a spec: `create_autospec(X, spec_set=True)`,
     `MagicMock(spec_set=X)`, `patch(..., autospec=True)`, or a `Protocol` fake.
   - Add `@typing.override` to any override among the changed methods.
4. **Re-check until clean:**
   - `dr-compliance <changed files>` exits 0;
   - the project's type checker shows no new errors on those files;
   - `dr-mock-lint <changed tests>` passes.
5. Run the non-integration test suite. Review. The user commits.

Never weaken existing annotations. Keep edits within the diff's files unless a
fix requires annotating an immediate caller.
