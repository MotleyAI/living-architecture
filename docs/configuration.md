# Configuration

`living-architecture.yaml` at the repo root records which parts of the flow a repo uses. `/la:init` writes it.
Every key is optional and takes the default shown below. Its presence means the repo is onboarded: main skills
check for it with `la-doctor --require-config`.

```yaml
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
  typecheck:                        # la-typecheck's checker per language; null turns one off
    python: basedpyright            # basedpyright-compatible (--writebaseline, .basedpyright/baseline.json)
    typescript: tsc --noEmit        # --pretty false is appended
conventions:
  text_ratio_max: 0.15              # max share of comment/docstring-only lines per file group
  exempt: []                        # repo-relative globs skipped by la-check-conventions
  rules:                            # the rules la-check-conventions enforces; [] turns the gate off
    - import-not-top
    - text-ratio
    - composite-assert
    - raises-single-throw
```

Types are strict: `codex: 'true'` or `text_ratio_max: '0.2'` is an error naming the key, not a coerced value.
YAML 1.1 booleans (`yes`, `no`, `on`, `off`) are booleans. `issue_key_pattern` must use the portable regex
subset in [`shared/regex-subset.md`](../shared/regex-subset.md). `la-config show` prints the resolved
configuration and `la-config get <dotted.key>` prints one value.

## Gates and the disk

`openspec` and `architecture` are decisions, and their directories are the result. When the file exists,
`la-doctor` reports each mismatch:

- `openspec: true` without an `openspec/` directory, or `openspec: false` with one;
- `architecture: true` without `architecture/index.yaml`, or `architecture: false` with it (an `architecture/`
  directory without `index.yaml` is not a living-architecture setup);
- `tracker: none` with `openspec: false`, which leaves no place for the plan to survive a session reset.

## Review bots

CodeRabbit and Sonar are not configured: `la-pr-reviewers <PR>` detects them on each PR. CodeRabbit counts as
present when it has a status check or has commented on the PR. Sonar counts as present when a check's name
contains `sonar`. The Sonar project key comes from `reviewers.sonar.project_key`, then `sonar.projectKey` in
`sonar-project.properties`, then the `id` parameter of the Sonar check's URL.

## Upgrading an existing config

`reviewers.coderabbit` and `reviewers.sonar.enabled` were removed; a config that still sets them is an error
naming the key. Delete them (keep `reviewers.sonar.project_key` if you set one). `/la:init` proposes this edit.
