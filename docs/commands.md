# Commands

The skills drive these commands; you can also run them directly. `<command> --help` prints the options. The
`dr-*` commands come with the `deterministic-refactor` package, the `la-*` commands with `living-architecture`,
which depends on it.

| Command | Purpose |
|---|---|
| `dr-doctor [--plugin DIR] [--require-config]` | Check the installed dr tools' major.minor series matches the `dr` plugin, the config dr reads, `git`, and each repo language's executables (`node`/`npx` for TypeScript) |
| `dr-config get <key>` / `dr-config show` | Print dr's resolved config; `get languages` prints the repo languages, `get lang.<language>.<key>` a language fact |
| `dr-typecheck [--write-baseline \| --realign-from REF]` | Type-check each applicable language against a baseline that only shrinks |
| `dr-refactor`, `dr-compliance`, `dr-mock-lint` | See [Deterministic refactoring](deterministic-refactoring.md) |
| `la-doctor [--plugin DIR] [--require-config] [--require-plan-store]` | Everything `dr-doctor` checks, against the `la` plugin, plus the dr installation la needs (a `dr-doctor` on `PATH` at la's version and contract) and `gh` |
| `la-config get <key>` / `la-config show` | Print the resolved repo config (`living-architecture.local.yaml` merged over it); `get languages` prints the repo languages, `get lang.<language>.<key>` a language fact |
| `la-arch-check` | Architecture cross-check (exit 0 OK, 1 findings, 2 broken setup) |
| `la-arch-scaffold` | Write a starter `architecture/model.c4`, `architecture/views.c4` and `system.arc42.md` from the measured top-level units and imports |
| `la-arch-diagrams` | Regenerate the mermaid view diagrams embedded in arc42 docs |
| `la-arch-migrate` | Convert the repo to the current `format` one released format at a time: a repo without one first gets a legacy `architecture/model/*.c4` model merged into `architecture/model.c4` and the retired `arc42` key format converted; then stamp `format` (verified, all-or-nothing) |
| `la-check-conventions <PR>` / `--base BRANCH` | Imports-at-top, text-ratio and test-assertion gate on changed `.py` and TS/JS files |
| `la-count-comments` | Count comment and doc (docstring, JSDoc) lines, or the net change vs a git ref |
| `la-typecheck` | Deprecated alias of `dr-typecheck` until 0.15.0: same output and exit, plus one deprecation line on stderr |
| `la-affected-tests --base BRANCH` | Print the test files a change can affect, one per line, without running them |
| `la-pr-reviewers <PR>` | Which review bots ran on a PR (CodeRabbit, Sonar and its project key), as JSON |
| `la-wait-for-reviews <PR>` | Watch CI, Sonar and, when it is on the PR, CodeRabbit until they settle, printing each new failed check, review comment and finished Sonar analysis once |
| `la-fetch-failed-pr-checks <PR> [--check NAME]` | Failed checks plus a log excerpt of each; `--check` keeps the one with that Details URL or name |
| `la-fetch-review-comments <PR>` | Unresolved threads, review bodies and conversation comments from every reviewer, each marked answered; CodeRabbit's nitpicks and outside-diff comments |
| `la-reply-to-pr-thread`, `la-reply-invalid-coderabbit` | Reply to a review thread (body on stdin) |

## Two twins

Each package has two native implementations (twins) with one contract: its PyPI package serves Python repos, and
its npm package of the same name (Node ≥ 22, same command names) serves TypeScript/JavaScript repos. Either twin
checks a Python, TypeScript or mixed repo with identical output: it hands the other language's work to the other
twin of the same package at the same version, found on `PATH` (or `<repo>/node_modules/.bin`) or run through
`uvx`/`npx`, and exits 2 with an install hint when that twin is unreachable. A single-language repo never needs
the other twin.

A repo language is one with a root marker (`pyproject.toml`/`setup.py`; `tsconfig.json`) and a tracked or
unignored, non-exempt file, or with an explicit `commands.typecheck` command; `commands.typecheck.<language>:
null` turns its type check off but keeps the language. `dr-config get languages` (or `la-config get languages`)
prints them, and skills read the language facts they need with `dr-config get lang.<language>.<key>` (`source_extensions`, `source_globs`,
`test_globs`, `declaration_globs`, `comment_prefix`, `suppression`, `waiver`, `baseline_file`, `markers`).

The `dr-*` commands route each input by file language: `dr-compliance` and `dr-mock-lint` print one block per
language, in registry order, and exit with the highest code; a directory expands to the repo languages' files
(every registered language's when the repo has none), never declaration files or `node_modules`.
`dr-refactor` runs in the language of its `--file`, its `--module` or its rename map's entries (one language per map);
`generate-map` in `--language`, else the one language with sources under the project. A Python rename and Python `dr-compliance
--attr` start the basedpyright bundled with the PyPI package as a language server, with the pyright#11919 patch,
outside the project; it reads the project's own configuration and interpreter.

## Conventions gate and type checks

`la-check-conventions` and `la-count-comments` route each file to its language by extension (`.py`;
`.ts/.tsx/.mts/.cts/.js/.jsx/.mjs/.cjs`) and print one report whichever twin runs them; the other language's
files are analysed by its twin. A Python repo whose diff touches TS/JS files has them checked too, which needs
the npm twin (`npx` is enough). List generated or vendored files under `exempt`, and pick the
enforced rules with `conventions.rules`. An explicit path with an unknown extension is skipped with a warning.
Waive a flagged line with `# ALLOW(<rule>): <reason>` or `// ALLOW(<rule>): <reason>`.

`dr-typecheck` checks every repo language whose `commands.typecheck` entry is not `null`. The checker is looked up in `.venv/bin` or
`node_modules/.bin` first, then on `PATH`. For Python it patches basedpyright in memory against pyright#11919,
whose dropped diagnostics depend on file order and thread count; the command must run a verified basedpyright
(today `1.40.2`) under Node and keep `NODE_OPTIONS`, else the run exits 2. Python keeps basedpyright's own
baseline; TypeScript keeps `.tsc-baseline.json`, a multiset of diagnostics keyed by file, code and message, so moved lines are not new
errors. New errors exit 1; fixed ones shrink the baseline. Run `dr-typecheck --write-baseline` once to create
the missing baselines.

A basedpyright baseline entry holds its error's rule and columns, without a line. A hand edit or a script that
changes the text earlier on a baselined line, or moves the file, therefore brings the error back as new
(`dr-refactor` realigns the baseline for its own edits). `dr-typecheck --realign-from REF` moves each Python entry
to where its error is now, then checks. `REF` is a commit where the baseline matched: `HEAD` for an uncommitted
edit. It follows the renames git reports since `REF`, never changes the number of entries, and leaves an error
that is really new as new. A failing Python check without the flag, in a repo with a baseline, names it. TypeScript is checked as without it.

Suppress a genuine false positive with `// @ts-expect-error — <reason>`, never
`@ts-ignore`.

## Affected tests

`la-affected-tests --base BRANCH` compares the working tree with `origin/BRANCH` (after a best-effort fetch, killed after
`base_fetch_timeout_seconds` in `shared/dr/cli.yaml` and never prompting for credentials) and
prints, one repo-relative path per line in code-point order, the test files the change can affect: the tests it
added or changed (committed, staged, unstaged or untracked) and every test whose imports, type-only ones included,
reach a changed or deleted file. Python imports resolve by dotted suffix against every file in the repo;
TypeScript ones under each file's nearest `tsconfig.json`. It needs no architecture index or config, never runs
a test, and exits 0 even when nothing is selected. A change touching both languages needs both twins.

The selection is exact only for imports. Goldens, snapshots, data files read at runtime, fixtures and conftest
fan-out, dynamic imports and code run in a subprocess are left to judgement; the `/la:pr` skills add them to the
local test scope and leave the full suite to CI. Printed helpers and fixtures that match a test glob are not
filtered out.

## Architecture checks in CI

See [Running the checks in CI](ci.md).
