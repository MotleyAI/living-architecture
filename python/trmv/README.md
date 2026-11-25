# deterministic-refactor

Verified renames and moves for Python and TypeScript code. `dr-refactor` rewrites every import and reference, and
`dr-typecheck` checks the result against the repo's committed type-check baseline, so a refactor that missed a
reference fails instead of slipping through. `dr-compliance` reports the constructs that would make a refactor
unverifiable, and `dr-mock-lint` the test doubles not bound to the real type.

```bash
uv tool install deterministic-refactor        # Python repos (Python >= 3.11)
npm install -g deterministic-refactor         # TypeScript/JavaScript repos (Node >= 22)
```

A repo configures it in `deterministic-refactor.yaml`, or in `living-architecture.yaml` when it also uses
[living-architecture](https://github.com/MotleyAI/living-architecture), which builds on this package. The Claude Code
plugin `dr` drives the commands; see [deterministic refactoring](https://github.com/MotleyAI/living-architecture/blob/main/docs/deterministic-refactoring.md).
