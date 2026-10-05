# living-architecture

A Claude Code plugin (`la`) plus its command-line tools that keep agent-written code from drifting into
spaghetti, and keep each change on a reviewed plan.

- **An architecture that is enforced, not just drawn.** A LikeC4 model maps nodes to code modules, and its
  arrows decide which module may import which. `la-arch-check` measures the real imports against the model.
  Grandfathered arrows are marked `#legacy` and only ever shrink. Each node carries arc42 principles with
  status tags, and agents treat the model and the principles like tests: changes need your approval.
- **A four-stage PR flow.** `/la:pr` interviews you into a Codex-reviewed OpenSpec plan, writes the failing
  tests, implements until they pass, and then loops CI, Codex, CodeRabbit and Sonar reviews until every gate
  is clean. Each stage resumes from the branch name alone, and the plan is archived with the code.
- **Refactoring without import churn.** Python and TypeScript moves and renames rewrite every import
  automatically, and the type checker proves nothing was left dangling.

The longer version is in
[Living architecture, explained](https://github.com/MotleyAI/living-architecture/blob/main/docs/living-architecture-explained.md).

## Install

```bash
# the plugin
/plugin marketplace add MotleyAI/living-architecture
/plugin install la@living-architecture

# the commands (la-*, dr-*), pinned to the same version as the plugin, from your repo's ecosystem
uv tool install living-architecture==0.3.0      # Python repos
npm install -g living-architecture@0.3.0        # TypeScript/JavaScript repos (Node >= 22)
```

The commands ship as two twins with one contract: a PyPI package and an npm package of the same name. Each
serves its own ecosystem natively, needs nothing from the other in a single-language repo, and calls the other
for the other language's files in a mixed repo
([details](https://github.com/MotleyAI/living-architecture/blob/main/docs/commands.md#two-twins)). Skills
check that the installed commands match the plugin before they run.

## Quick start

In the repo you want to onboard, run:

```
/la:init
```

It detects your tracker, test, lint and type-check commands, Codex, Sonar and any existing OpenSpec or
architecture setup, then proposes a `living-architecture.yaml` and asks only about what it cannot detect. It
then offers to set up OpenSpec, record the type-check baseline and build the architecture model with
`/la:arch-init`. After that, start each change with `/la:pr` on a branch named after its issue.

## Skills

| Skill | Purpose |
|---|---|
| `la:init` | Onboard a repo: detect its tools, write `living-architecture.yaml`, offer the next setup steps |
| `la:pr` | Run a change through plan → failing tests → implementation → review |
| `la:arch-init` | Build the first architecture model from the measured code, then its principles |
| `la:arch-cleanup` | Retire a batch of `#legacy` arrows, or carve a new boundary, with verified moves |
| `la:deterministic-refactor` | Rename or move Python or TypeScript code, proven complete by the type checker |

These skills call helper skills that you can also run on their own; see
[Skills](https://github.com/MotleyAI/living-architecture/blob/main/docs/skills.md).

## Languages

A repo's languages are those with a root marker (`pyproject.toml`/`setup.py`; `tsconfig.json`) and source
files, or a `commands.typecheck` entry; `la-config get languages` lists them. The architecture model declares
one section per language in `architecture/index.yaml`, and a mixed repo has both:

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

Pin the architecture check in CI to a release, in your ecosystem's form:

```yaml
# Python
- uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
- run: uvx --no-build --from living-architecture==0.3.0 la-arch-check
# TypeScript
- uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
- run: npx -y -p living-architecture@0.3.0 la-arch-check
```

## Prerequisites

Always: `git`, `bash`, `gh` (authenticated) and `jq`.

Per repo language (`la-doctor` checks them):

| Language | Needs |
|---|---|
| Python | the PyPI twin; basedpyright in the project env for the type-check gate |
| TypeScript | `node` (>= 22) and `npx`; the npm twin; `tsc` in `node_modules` for the type-check gate |

Per gate, as `living-architecture.yaml` enables it:

| Gate | Needs |
|---|---|
| `tracker: linear` | the Linear MCP server |
| `tracker: github` | nothing beyond `gh` |
| `openspec: true` | `npx` (the OpenSpec CLI) |
| `architecture: true` | `npx` (the LikeC4 CLI) |
| `reviewers.codex: true` | the Codex MCP server (`mcp__codex__codex`) |
| Sonar on your PRs | the SonarQube MCP server |

## Documentation

- [Living architecture, explained](https://github.com/MotleyAI/living-architecture/blob/main/docs/living-architecture-explained.md)
- [Skills](https://github.com/MotleyAI/living-architecture/blob/main/docs/skills.md): main and helper skills
- [Configuration](https://github.com/MotleyAI/living-architecture/blob/main/docs/configuration.md): `living-architecture.yaml`
- [Commands](https://github.com/MotleyAI/living-architecture/blob/main/docs/commands.md): the `la-*` and `dr-*` commands, and CI
- [Deterministic refactoring](https://github.com/MotleyAI/living-architecture/blob/main/docs/deterministic-refactoring.md)
- [Development](https://github.com/MotleyAI/living-architecture/blob/main/docs/development.md): working from a checkout, layout, releasing
