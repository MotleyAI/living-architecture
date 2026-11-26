# type-rename-move

Verified renames and moves for Python and TypeScript code. `trmv-refactor` rewrites every import and reference, and
`trmv-typecheck` checks the result against the repo's committed type-check baseline, so a refactor that missed a
reference fails instead of slipping through. `trmv-compliance` reports the constructs that would make a refactor
unverifiable, and `trmv-mock-lint` the test doubles not bound to the real type.

```bash
uv tool install type-rename-move        # Python repos (Python >= 3.11)
npm install -g type-rename-move         # TypeScript/JavaScript repos (Node >= 22)
```

A repo configures it in `trmv.yaml`, or in `living-architecture.yaml` when it also uses
[living-architecture](https://github.com/MotleyAI/living-architecture), which builds on this package. The Claude Code
plugin `trmv` drives the commands; see [Renames and moves](https://github.com/MotleyAI/living-architecture/blob/main/docs/rename-and-move.md).
