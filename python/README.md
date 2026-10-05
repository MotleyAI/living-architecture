# living-architecture

A Claude Code plugin (`la`) plus its command-line tools for **spec-driven
development with an enforced living architecture**:

- **PR flow** — `/la:pr` runs a change through four resumable stages
  (plan → failing tests → implementation → review loop), keyed on the Linear
  issue whose branch name matches the current branch, with OpenSpec as the
  behaviour corpus.
- **Living architecture** — one LikeC4 model, arc42 principles per node, and
  `la-arch-check`, which enforces the model as the repo's single import law and
  cross-checks code, model, docs, and specs.
- **Review processing** — `/la:process-reviews` waits for CI and review bots,
  then triages CI failures, Codex, and (when enabled) CodeRabbit and SonarQube
  findings into one fix plan.
- **Deterministic refactoring** — rope-driven renames and moves whose
  completeness is proven by the type checker, not trusted.

## Install

```bash
# the plugin
/plugin marketplace add MotleyAI/living-architecture
/plugin install la@living-architecture

# the commands (la-*, dr-*), pinned to the same version as the plugin
uv tool install living-architecture==0.2.2
```

Skills run `la-doctor --plugin <skill dir>` first and stop if the installed
commands don't match the plugin's version.

The commands have two native implementations (twins) with one contract: the PyPI
package serves Python repos, and the npm package `living-architecture` (Node ≥ 22,
same command names; published from a later release) serves TypeScript/JavaScript
repos. Either twin checks a Python, TypeScript or mixed repo with identical
output: it hands the other language's work to the other twin at the same version,
found on `PATH` (or `<repo>/node_modules/.bin`) or run through `uvx`/`npx`, and
exits 2 with an install hint when that twin is unreachable.

**Prerequisites:** `git`, `bash`, `gh` (authenticated), `jq`; `npx` for the
OpenSpec and LikeC4 CLIs; the Linear MCP server for the spec flow; the Codex MCP
server (`mcp__codex__codex`) for plan, test, and diff reviews; the SonarQube MCP
server if Sonar is enabled; and a type checker in the target repo (the
refactoring and architecture gates compare against its recorded baseline).

## Skills

| Skill | Purpose |
|---|---|
| `la:pr` | Entry point: rehydrate the Linear issue, detect the stage, dispatch |
| `la:pr-plan`, `la:pr-tests`, `la:pr-implement`, `la:pr-review` | The four stages |
| `la:openspec-init` | Initialize or repair OpenSpec in a repo |
| `la:living-architecture` | Set up or maintain the architecture layer |
| `la:arch-slice` | Retire a batch of `#legacy` import arrows with verified moves |
| `la:process-reviews` | Triage CI, Codex, CodeRabbit, and Sonar feedback into a plan |
| `la:fetch-coderabbit-threads`, `la:fetch-failed-pr-checks`, `la:reply-to-pr-thread` | Single-source review helpers |
| `la:codex-review` | Codex review of the current diff |
| `la:concise-comments` | Comment/docstring rules and a trimming pass |
| `la:deterministic-refactor`, `la:make-diff-compliant`, `la:make-refactor-target-compliant` | Verified refactoring |

## Commands

| Command | Purpose |
|---|---|
| `la-doctor` | Check tool/plugin versions, the repo config, and `git`/`gh` |
| `la-config get <key>` / `la-config show` | Print resolved repo config |
| `la-arch-check` | Architecture cross-check (exit 0 OK, 1 findings, 2 broken setup) |
| `la-arch-diagrams` | Regenerate the mermaid view diagrams embedded in arc42 docs |
| `la-check-conventions <PR>` / `--base BRANCH` | Imports-at-top, text-ratio and test-assertion gate on changed `.py` and TS/JS files |
| `la-count-comments` | Count comment and doc (docstring, JSDoc) lines, or the net change vs a git ref |
| `la-typecheck [--write-baseline]` | Type-check each applicable language against a baseline that only shrinks |
| `la-wait-for-reviews <PR>` | Wait for CI and the CodeRabbit review to settle |
| `la-fetch-failed-pr-checks <PR>` | Failed checks plus their failed-step logs |
| `la-fetch-coderabbit-threads <PR>` | Unresolved CodeRabbit threads, nitpicks, outside-diff comments |
| `la-reply-to-pr-thread`, `la-reply-invalid-coderabbit` | Reply to a review thread (body on stdin) |
| `dr-refactor`, `dr-compliance`, `dr-mock-lint` | See [Deterministic refactoring](#deterministic-refactoring) |

## Repo config

Optional `living-architecture.yaml` at the repo root; without it every value
takes its default.

```yaml
reviewers:
  coderabbit: false                 # /la:pr flow's CodeRabbit steps run only when true (la-* CR commands always work)
  sonar:
    enabled: false                  # SonarQube steps run only when true
    project_key: my-org_my-repo     # required when enabled
issue_key_pattern: "[A-Z][A-Z0-9]+-\\d+"   # ids allowed in arc42 [target: …] tags
commands:
  test: pytest -m "not integration" # the full suite the flow runs; unset = the repo's documented one
  lint: ruff check .
  typecheck:                        # la-typecheck's checker per language; null turns one off
    python: basedpyright            # basedpyright-compatible (--writebaseline, .basedpyright/baseline.json)
    typescript: tsc --noEmit        # --pretty false is appended
conventions:
  text_ratio_max: 0.15              # max share of comment/docstring-only lines
  exempt: []                        # repo-relative globs skipped by la-check-conventions
```

Types are strict: `coderabbit: 'true'` or `text_ratio_max: '0.2'` is an error
naming the key, not a coerced value. `issue_key_pattern` must use the portable
regex subset in [`shared/regex-subset.md`](shared/regex-subset.md).

## Conventions gate and type checks

`la-check-conventions` and `la-count-comments` route each file to its language
by extension (`.py`; `.ts/.tsx/.mts/.cts/.js/.jsx/.mjs/.cjs`) and print one
report whichever twin runs them; the other language's files are analysed by
its twin. **Breaking:** a Python repo whose diff touches TS/JS files now has
them checked, which needs the npm twin (`npx` is enough). List generated or
vendored TS/JS (for example `docs/static/*`) under `conventions.exempt`. An
explicit path with an unknown extension is skipped with a warning. Waive a
flagged line with `# ALLOW(<rule>): <reason>` or `// ALLOW(<rule>): <reason>`.

`la-typecheck` checks a language when `commands.typecheck` sets it, or when
the repo has its files and a root marker (`pyproject.toml`/`setup.py`;
`tsconfig.json`). The checker is looked up in `.venv/bin` or
`node_modules/.bin` first, then on `PATH`. Python keeps basedpyright's own
baseline; TypeScript keeps `.tsc-baseline.json`, a multiset of diagnostics
keyed by file, code and message, so moved lines are not new errors. New
errors exit 1; fixed ones shrink the baseline. Run `la-typecheck
--write-baseline` once to create the missing baselines. Suppress a genuine
false positive with `// @ts-expect-error — <reason>`, never `@ts-ignore`.

## Upgrading to language roots

`index.yaml` holds one section per language and the model one root element per
language; `la-arch-check` exits 2 on a top-level `root_package`. Once per repo:

1. Move `root_package`/`source_root` into a `python:` (or `typescript:`) section;
   repo-owned keys must start with `x-`.
2. Wrap every top-level model element and relation, unchanged, in
   `python = system '<title>' { … }`; relation names stay relative to the root.
3. Add `of python` to every view (`view system of python { … }`) and qualify
   `cross_cutting_specs` `touches` (`core` → `python.core`).
4. Run `la-arch-check` until green. Diagrams need no regeneration; findings now
   name elements fully qualified (`python.core`).

```yaml
python:
  root_package: mypkg
  source_root: src
typescript:                 # a second language: its own root element `typescript`
  root_package: src
  source_root: web
```

## Upgrading from `index.yaml` `nodes:`

Node mapping now lives in the LikeC4 model; `index.yaml` keeps only repo-wide
settings, and `la-arch-check` exits 2 while it still has `nodes:`. Once per repo:
move each `nodes.<id>` entry into a `metadata { }` block on model element `<id>`
(`package`, `claims`, `packages`, `arc42`, `specs`), drop `children:` and
`virtual:` (the model's nesting and `#virtual` kinds already say both), delete
`nodes:`, and run `la-arch-check` until green:

```
python = system 'My package' {
  api = node 'API' {
    metadata {
      package 'mypkg.api'
      specs ['api']
    }
    handlers = node 'Handlers'   // maps to mypkg.api.handlers
  }
}
```

## Architecture checks in CI

Pin the checker to a release; it needs no per-repo code beyond
`architecture/`. `--no-build` installs only prebuilt wheels:

```yaml
- uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
- run: uvx --no-build --from living-architecture==0.2.2 la-arch-check
```

## Working from a local checkout

To use and edit the plugin at the same time, run everything from a clone
instead of a marketplace install:

```bash
git clone https://github.com/MotleyAI/living-architecture ~/src/living-architecture
uv tool install -e ~/src/living-architecture/python
ln -s ~/src/living-architecture/plugin ~/.claude/skills/la
```

Claude Code loads a plugin directory under `~/.claude/skills/` in place (it shows
as `la@skills-dir` in `claude plugin list`), so this works in every launcher,
including IDE and git-client integrations. The alternative is
`alias claude='claude --plugin-dir ~/src/living-architecture/plugin'`, but
launchers that don't read your shell aliases need that flag added to their own
command settings.

- Do **not** also install `la` from the marketplace — both copies would load and
  every skill would appear twice. If it is installed, `/plugin uninstall
  la@living-architecture` first.
- Python edits take effect on the next command run (editable install). Edits
  under `shared/` (texts, schemas, the CLI manifest, the review scripts) take
  effect after `scripts/sync-shared`, which refreshes the vendored copy the
  commands load. Adding or renaming a command (in `shared/cli.yaml` and
  `python/pyproject.toml`) needs `uv tool install -e` again.
- SKILL.md edits take effect from the next Claude Code session.
- To try an unreleased checker in a repo that pins a release, `pip install -e
  <checkout>/python` into that repo's environment; its next dependency sync
  restores the pin.

## Repository layout

| Path | Holds |
|---|---|
| `plugin/` | the Claude Code plugin: skills |
| `python/` | the PyPI twin (`living-architecture`): every `la-*`/`dr-*` command |
| `node/` | the npm twin (`living-architecture`): the language-neutral commands and the TypeScript arch-check, conventions and type check; forwards the Python-only `dr-*` commands |
| `shared/` | the contract the commands obey: config and index schemas, finding texts, the CLI manifest, conventions and language registries, review scripts, test vectors |
| `conformance/` | the byte-exact corpus pinning every command's observable output |
| `architecture/` | this repo's own LikeC4 model and arc42 principles |
| `scripts/sync-shared` | vendors `shared/`, `README.md` and `LICENSE` into both twins |
| `scripts/conformance-cross` | runs every conformance case through both twins' entry points |
| `scripts/release-check` | checks a release tag against both twins' versions and contract hashes |

See [AGENTS.md](AGENTS.md) for how to change any of them.

## Releasing

In `python/`, bump the version with `uv version <new>`, then in
`node/package.json` and `plugin/.claude-plugin/plugin.json` (the tests fail
until all agree), and update the pins in this README. Run `scripts/sync-shared` and commit the refreshed copies. Tag
`v<version>` and publish a GitHub release for it; the `Publish` workflow first
runs `scripts/release-check` (every version equals the tag, both contract hashes
agree) and publishes neither twin otherwise. The npm job skips while
`node/package.json` is `"private": true`.

## Deterministic refactoring

Rename and move Python code with automatic import/reference rewriting — and,
the actual point, a **deterministic check that the refactor left nothing
dangling**.

The rename tool (`rope`) is best-effort: no refactoring tool reliably rewrites
every type-annotated `obj.attr`, `super()` call, and subclass override. So it is
never trusted — it is *verified*. A strict type-check proves no dangling static
reference remains; `@typing.override` turns a missed override into an error; a
mock-spec lint turns a missed dynamic (mock) reference into a failure. Green ⇒
provably no dangling reference.

Tools:
- `dr-refactor` — rope mutator: `rename` / `move-symbol` / `move-module`
- `dr-mock-lint` — fail on mocks not bound to a spec
- `dr-compliance` — report the constructs that make a refactor un-verifiable

### What a fully compliant repo must fulfill

A repo is *refactor-verifiable* when a missed rename is **guaranteed to surface
as a failing check**. That holds only when:

1. **Target code is typed.** Functions annotated (params + return), class
   attributes annotated, and every variable/parameter that holds an instance of
   a class annotated. An unannotated `x.attr` is unresolvable, so a miss there
   is invisible — determinism is bought with type coverage. (`dr-compliance` +
   Ruff `ANN*` enforce this.)
2. **A type checker runs against the project's own environment.** mypy or
   basedpyright resolving imports via the project venv — the *same* interpreter
   the tests use — passing, or at a recorded baseline.
3. **Overrides are marked.** `@typing.override` on every override, with
   `reportImplicitOverride` (basedpyright) or mypy strict enabled, so a base
   rename that orphans an override is an error, not a silent break.
4. **Mocks are spec-bound.** No bare `Mock()`/`MagicMock()`/`patch()`; every
   double bound via `spec_set=` / `autospec=True` / a `Protocol` fake. A stale
   mock member then fails (`AttributeError`, or a type error for typed fakes).
   (`dr-mock-lint` enforces this.)
5. **The gate is wired into CI/pre-commit.** type-check (no new errors vs
   baseline) + `dr-mock-lint` + the test suite, on every change.

`dr-compliance` mechanically checks 1, 3-adjacent (via the type checker), and 4,
and reports each violation as `file:line: <kind>: <message>`.

### Using it on an existing repo

#### 1. One-time setup

- Install the tools (see Install above).
- Add a type checker to the project's dev dependencies, pointed at its venv —
  it must resolve imports the way the tests do:

  ```toml
  # pyproject.toml
  [tool.basedpyright]
  venvPath = "."
  venv = ".venv"
  pythonVersion = "3.11"
  typeCheckingMode = "standard"      # already errors on attribute access
  reportImplicitOverride = "error"
  ```

  (Equivalently `mypy --strict --python-executable .venv/bin/python`.)
- Add `dr-mock-lint <tests>` and the type checker to `.pre-commit-config.yaml`
  and CI. Record the current type-error set as the baseline — you do **not**
  need a clean whole repo, only "no *new* errors" per change.

The mutator (`rope`) does **not** belong in the project's dependencies — it
reads source and needs nothing installed. Only the verifier needs the env.

#### 2. Keep every PR compliant — skill `make-diff-compliant`

Bring exactly the files a PR touches up to the five conditions before it merges,
so compliance grows monotonically with the diff instead of requiring a big-bang
migration. The skill runs `dr-compliance` on the changed files, adds the missing
annotations / `@override` / mock specs, and loops until the type checker and
`dr-mock-lint` are clean on the diff. See `plugin/skills/make-diff-compliant/`.

#### 3. Do a refactor — skill `deterministic-refactor`

Locate the symbol with the editor/LSP → `dr-refactor` dry-run → apply → run the
gate (type checker shows no new errors, `dr-mock-lint` passes, tests pass, grep
the string-only references no static tool sees) → review the diff. See
`plugin/skills/deterministic-refactor/`.

#### 4. Make a refactor's blast radius compliant first — skill `make-refactor-target-compliant`

Before renaming `X` or `X.attr`, close the blind spots the gate would otherwise
miss: code that *might* reference the target but is currently invisible to the
checker — untyped parameters/variables that could hold an `X`, classes whose
attribute names match the target ("right-looking" names), subclasses missing
`@override`. The skill drives `dr-compliance --attr <name>` to enumerate those
sites, annotates them, and re-checks until the blast radius is fully typed —
so the post-rename gate is sound. See `plugin/skills/make-refactor-target-compliant/`.
