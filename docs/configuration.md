# Configuration

`living-architecture.yaml` at the repo root records which parts of the flow a repo uses. `/la:init` writes it.
In a committed file every key but `format` is optional and takes the default shown below. Its presence means the
repo is onboarded: main skills check for it with `la-doctor --require-config`.

```yaml
format: 0.13.0                      # the repo format (below); la-arch-migrate stamps it
exempt: []                          # repo-relative globs that are not the repo's own source (fixtures, generated code)
tracker: linear                     # linear | github | none: where issues and (without OpenSpec) plans live
openspec: true                      # the flow keeps specs and changes under openspec/
architecture: false                 # the repo has a living-architecture model (architecture/index.yaml)
reviewers:
  codex: true                       # the flow runs Codex reviews; a missing Codex MCP server stops it
  sonar:
    project_key: null               # overrides the Sonar project key inferred per PR
issue_key_pattern: "[A-Z][A-Z0-9]+-\\d+"   # ids allowed in arc42 [target: …] tags; GitHub repos use "#\\d+"
commands:
  test: null                        # the full non-integration suite; unset = the repo's documented one
  lint: null
  typecheck:                        # dr-typecheck's checker per language; null turns one off
    python: basedpyright            # basedpyright-compatible (--writebaseline, .basedpyright/baseline.json)
    typescript: tsc --noEmit        # --pretty false is appended
refactor:
  string_forms: []                  # patterns of strings that carry a symbol's name, e.g. 'NODE TABLE (\w+)'
conventions:
  text_ratio_max: 0.15              # max share of comment/docstring-only lines per file group
  rules:                            # the rules la-check-conventions enforces; [] turns the gate off
    - import-not-top
    - text-ratio
    - composite-assert
    - raises-single-throw
```

Types are strict: `codex: 'true'` or `text_ratio_max: '0.2'` is an error naming the key, not a coerced value.
YAML 1.1 booleans (`yes`, `no`, `on`, `off`) are booleans. `issue_key_pattern` must use the portable regex
subset in [`shared/dr/regex-subset.md`](../shared/dr/regex-subset.md), and so must each pattern of
`refactor.string_forms`, which also holds exactly one capturing group: `dr-refactor` searches every string literal
with each pattern and respells the group's text when a class or another module-level symbol of that name is
renamed. `la-config show` prints the resolved
configuration and `la-config get <dotted.key>` prints one value.

`exempt` paths are left out of language detection and exempted from `la-check-conventions`.

`commands.typecheck.python` must run basedpyright under Node and keep `NODE_OPTIONS`: `dr-typecheck` loads its
in-memory patch for pyright#11919 through it. The patch is verified only for the basedpyright versions in
`shared/dr/languages.yaml` (today `1.40.2`), so pin one; any other version, or a run the patch did not reach, exits 2.

## dr's keys and `deterministic-refactor.yaml`

`format`, `exempt`, `commands.test`, `commands.typecheck` and `refactor` are dr's keys: the `dr-*` commands read
them. A repo that uses la keeps them in `living-architecture.yaml`, so it has one file. A repo that uses only dr
keeps them in `deterministic-refactor.yaml`, which `/dr:init` writes and which holds dr's keys alone:

```yaml
format: 0.13.0
exempt: []
commands:
  test: null
  typecheck:
    python: basedpyright
    typescript: tsc --noEmit
refactor:
  string_forms: []
```

A dr command reads `deterministic-refactor.yaml`, else `living-architecture.yaml`; an la command reads only
`living-architecture.yaml`. Both files at the repo root is an error from every command. `dr-config show` prints
dr's resolved keys and `dr-config get <dotted.key>` one value; `dr-doctor --require-config` asks for either file.

## Format

`format` is the repo format: the version that introduced the format of the file that declares it. Each file has
its own series: `living-architecture.yaml` (with everything under `architecture/`) follows la's releases, and
`deterministic-refactor.yaml` dr's. Every command except `la-arch-migrate`, the doctors and the review shims checks
the file it read first and exits 2 on any other format. For `living-architecture.yaml`, a newer one names the `la`
to upgrade to, and an older or missing one says to run `la-arch-migrate`, which converts the repo one released
format at a time, starting from the declared one, and stamps the current format (from 0.4.0 to 0.13.0 it moves
`conventions.exempt` to the top-level `exempt`). For `deterministic-refactor.yaml`, a newer one names the dr to
upgrade to. `la-doctor` and `dr-doctor` report the same refusal as a problem. Without a committed file there is
nothing to check; the local file cannot set `format`.

## Languages

A repo's languages are those with a root marker (`pyproject.toml`/`setup.py`; `tsconfig.json`) and source
files, or a `commands.typecheck` entry, which a language needs when its marker is not at the root (like the
`web/tsconfig.json` below); `la-config get languages` lists them. The architecture model declares one section
per language in `architecture/index.yaml`, and a mixed repo has both:

```yaml
python:
  root_package: mypkg                 # the package the python root maps to
  source_root: src                    # optional
typescript:
  root_package: src                   # the directory the typescript root maps to
  source_root: web                    # optional
  tsconfig: web/tsconfig.json         # optional: default the nearest tsconfig.json
legacy_arrows: {baseline: 0}
```

When a language's code sits in several sibling directories under one `source_root`, list them with
`root_packages: [app, packages/ui]` instead of `root_package`. The roots must be disjoint directories; unit ids stay
relative to `source_root`, and without a `tsconfig` key each TypeScript root resolves imports under its own nearest
`tsconfig.json`.

Python root packages may also sit under several import roots, as in a uv workspace: list them with
`source_roots: [packages/a/src, packages/b/src]` instead of `source_root`. Each root package must sit under exactly
one entry, and unit ids stay dotted. TypeScript takes one `source_root`.

## Gates and the disk

`openspec` and `architecture` are decisions, and their directories are the result. When the file exists,
`la-doctor` reports each mismatch:

- `openspec: true` without an `openspec/` directory, or `openspec: false` with one;
- `architecture: true` without `architecture/index.yaml`, or `architecture: false` with it (an `architecture/`
  directory without `index.yaml` is not a living-architecture setup);
- with `--require-plan-store`, which `la:pr` passes: `tracker: none` with `openspec: false`, which leaves
  no place for the plan to survive a session reset.

## Local overrides

A contributor who lacks the repo's tracker or Codex can override those settings in
`living-architecture.local.yaml` at the repo root, without editing the committed file:

```yaml
tracker: none
reviewers:
  codex: false
```

It may set only `tracker` and `reviewers.codex`; any other key is an error naming the key and the file. It is a
deep merge over `living-architecture.yaml` (or over the defaults when there is none): mappings merge key by key,
so `reviewers.sonar` stays as committed. Every command sees the merged configuration. `la-config show` prints a
note on stderr for each key the local file sets; `la-config get` prints none.

The file holds one person's settings, so it must stay out of git: add `living-architecture.local.yaml` to
`.gitignore` (`/la:init` offers to). `la-doctor` fails while git has it tracked (staged included) or does not
ignore it. A local file alone does not onboard a repo: `la-doctor --require-config` still asks for the committed
file.

## Review bots

CodeRabbit and Sonar are not configured: `la-pr-reviewers <PR>` detects them on each PR. CodeRabbit counts as
present when it has a status check or has commented on the PR. Sonar counts as present when a check's name
contains `sonar`. The Sonar project key comes from `reviewers.sonar.project_key`, then `sonar.projectKey` in
`sonar-project.properties`, then the `id` parameter of the Sonar check's URL.

## Upgrading an existing config

`reviewers.coderabbit` and `reviewers.sonar.enabled` were removed; a config that still sets them is an error
naming the key. Delete them (keep `reviewers.sonar.project_key` if you set one). `/la:init` proposes this edit.
