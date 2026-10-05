# Commands

The skills drive these commands; you can also run them directly. `<command> --help` prints the options.

| Command | Purpose |
|---|---|
| `la-doctor [--plugin DIR] [--require-config]` | Check tool/plugin versions, the repo config against the disk, and `git`/`gh` |
| `la-config get <key>` / `la-config show` | Print the resolved repo config |
| `la-arch-check` | Architecture cross-check (exit 0 OK, 1 findings, 2 broken setup) |
| `la-arch-scaffold` | Write a starter model, views and `system.arc42.md` from the measured top-level units and imports |
| `la-arch-diagrams` | Regenerate the mermaid view diagrams embedded in arc42 docs |
| `la-check-conventions <PR>` / `--base BRANCH` | Imports-at-top, text-ratio and test-assertion gate on changed `.py` and TS/JS files |
| `la-count-comments` | Count comment and doc (docstring, JSDoc) lines, or the net change vs a git ref |
| `la-typecheck [--write-baseline]` | Type-check each applicable language against a baseline that only shrinks |
| `la-pr-reviewers <PR>` | Which review bots ran on a PR (CodeRabbit, Sonar and its project key), as JSON |
| `la-wait-for-reviews <PR>` | Wait for CI and, when it is on the PR, the CodeRabbit review to settle |
| `la-fetch-failed-pr-checks <PR>` | Failed checks plus their failed-step logs |
| `la-fetch-coderabbit-threads <PR>` | Unresolved CodeRabbit threads, nitpicks, outside-diff comments |
| `la-reply-to-pr-thread`, `la-reply-invalid-coderabbit` | Reply to a review thread (body on stdin) |
| `dr-refactor`, `dr-compliance`, `dr-mock-lint` | See [Deterministic refactoring](deterministic-refactoring.md) |

## Two twins

The commands have two native implementations (twins) with one contract: the PyPI package serves Python repos,
and the npm package `living-architecture` (Node ≥ 22, same command names) serves TypeScript/JavaScript repos.
Either twin checks a Python, TypeScript or mixed repo with identical output: it hands the other language's work
to the other twin at the same version, found on `PATH` (or `<repo>/node_modules/.bin`) or run through
`uvx`/`npx`, and exits 2 with an install hint when that twin is unreachable.

## Conventions gate and type checks

`la-check-conventions` and `la-count-comments` route each file to its language by extension (`.py`;
`.ts/.tsx/.mts/.cts/.js/.jsx/.mjs/.cjs`) and print one report whichever twin runs them; the other language's
files are analysed by its twin. A Python repo whose diff touches TS/JS files has them checked too, which needs
the npm twin (`npx` is enough). List generated or vendored files under `conventions.exempt`, and pick the
enforced rules with `conventions.rules`. An explicit path with an unknown extension is skipped with a warning.
Waive a flagged line with `# ALLOW(<rule>): <reason>` or `// ALLOW(<rule>): <reason>`.

`la-typecheck` checks a language when `commands.typecheck` sets it, or when the repo has its files and a root
marker (`pyproject.toml`/`setup.py`; `tsconfig.json`). The checker is looked up in `.venv/bin` or
`node_modules/.bin` first, then on `PATH`. Python keeps basedpyright's own baseline; TypeScript keeps
`.tsc-baseline.json`, a multiset of diagnostics keyed by file, code and message, so moved lines are not new
errors. New errors exit 1; fixed ones shrink the baseline. Run `la-typecheck --write-baseline` once to create
the missing baselines. Suppress a genuine false positive with `// @ts-expect-error — <reason>`, never
`@ts-ignore`.

## Architecture checks in CI

Pin the checker to a release; it needs no per-repo code beyond `architecture/`. `--no-build` installs only
prebuilt wheels:

```yaml
- uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
- run: uvx --no-build --from living-architecture==0.2.3 la-arch-check
```
