# living-architecture

[![CI](https://github.com/MotleyAI/living-architecture/actions/workflows/ci.yml/badge.svg)](https://github.com/MotleyAI/living-architecture/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/living-architecture)](https://pypi.org/project/living-architecture/)
[![npm](https://img.shields.io/npm/v/living-architecture)](https://www.npmjs.com/package/living-architecture)
[![Python](https://img.shields.io/pypi/pyversions/living-architecture)](https://pypi.org/project/living-architecture/)
[![License: MIT](https://img.shields.io/github/license/MotleyAI/living-architecture)](https://github.com/MotleyAI/living-architecture/blob/main/LICENSE)

![living-architecture: a LikeC4 model allows api → core → store and rejects the api → store shortcut; the arc42 principles of core carry enforced, review and target status tags](https://raw.githubusercontent.com/MotleyAI/living-architecture/main/docs/images/living-architecture.png)

**living-architecture is a Claude Code plugin (`la`) and a CLI that keep coding agents from eroding the
architecture of a Python or TypeScript codebase.** You draw the modules and the imports allowed between them as a
[LikeC4](https://likec4.dev) model, and `la-arch-check` fails whenever the real imports and the model disagree.

Every PR an agent writes can be reasonable on its own while the codebase still drifts into spaghetti, one small
shortcut at a time. Telling the agent the rules in `CLAUDE.md` doesn't hold: it will quote a principle back to
you and then add the import that breaks it. So `la` turns the architecture into a check, like a test. A declared
arrow is the only thing that licenses an import, and no arrow means the import is banned.

- **An architecture that is enforced, not just drawn.** Elements of the model map to packages or directories,
  and their arrows decide which may import which. Existing violations are marked `#legacy` and counted against a
  baseline. Each element can carry [arc42](https://arc42.org) principles with status tags, and agents treat the
  model and the principles like tests: changing them needs your approval.
- **A four-stage PR flow.** `/la:pr` interviews you into a Codex-reviewed [OpenSpec](https://github.com/Fission-AI/OpenSpec)
  plan, writes the failing tests, implements until they pass, then loops CI, Codex, CodeRabbit and Sonar reviews
  until every gate is clean. Each stage resumes from the branch name alone, and the plan is archived with the code.
- **Refactoring without import churn.** Python and TypeScript moves and renames rewrite every import
  automatically, and the type checker proves nothing was left dangling.

## What it looks like

A model in `architecture/model.c4` with three packages, where `api` may use `core` and `core` may use `store`:

```
python = system 'python' {
  api = node 'api' { metadata { package 'shop.api' } }
  core = node 'core' { metadata { package 'shop.core' } }
  store = node 'store' { metadata { package 'shop.store' } }

  api -> core
  core -> store
}
```

An agent adds a shortcut from `api` straight to `store`, and the check fails in its review loop and in CI:

```console
$ la-arch-check
model-truth: measured runtime edge python.api -> python.store is missing from the model (import shop.api -> shop.store)
arch_check: 1 finding(s)
```

The match is exact in both directions. An arrow that no import uses fails too, so the model can't go stale:

```console
$ la-arch-check
model-truth: modeled relation python.api -> python.store has no measured runtime edge
arch_check: 1 finding(s)
```

The model is also rendered as a mermaid diagram into the arc42 docs that agents read before every change, and the
check fails when a diagram is out of date. Try the whole loop in five minutes with the
[quickstart example](https://github.com/MotleyAI/living-architecture/blob/main/examples/quickstart/README.md),
or see the model this repo checks itself against in
[`architecture/system.arc42.md`](https://github.com/MotleyAI/living-architecture/blob/main/architecture/system.arc42.md).

## Install

```bash
# the plugin
/plugin marketplace add MotleyAI/living-architecture
/plugin install la@living-architecture

# the commands (la-*, dr-*), pinned to the same version as the plugin, from your repo's ecosystem
uv tool install living-architecture==0.4.0      # Python repos (Python >= 3.11)
npm install -g living-architecture@0.4.0        # TypeScript/JavaScript repos (Node >= 22)
```

The commands come as a PyPI package and an npm package of the same name, with identical behaviour. Each serves
its own ecosystem natively, needs nothing from the other in a single-language repo, and calls the other for the
other language's files in a mixed repo
([details](https://github.com/MotleyAI/living-architecture/blob/main/docs/commands.md#two-twins)). Skills check
that the installed commands match the plugin before they run.

`living-architecture.yaml` records the repo's format version. After an upgrade that changes the format, most
commands refuse to run on the repo until you run `la-arch-migrate` once, and `la-doctor` says so.

## Quick start

### Just the architecture check

You don't need the plugin or the PR flow to enforce the architecture. Tell the checker where your code lives in
`architecture/index.yaml`:

```yaml
python:
  root_package: mypkg      # the package the model's python root maps to
  source_root: src         # optional
legacy_arrows: {baseline: 0}
```

Then write a first model from the imports the code has today, and check it:

```bash
la-arch-scaffold      # writes architecture/model.c4, views.c4 and system.arc42.md from the measured imports
la-arch-check
```

The scaffold allows every import that exists, so the first check passes once any OpenSpec specs you have are
mapped to elements. Tighten it from there: delete the arrows you don't want, or mark them `#legacy`, raise the
baseline to match and run `la-arch-diagrams`. TypeScript and mixed repos are set up the same way; see
[Configuration](https://github.com/MotleyAI/living-architecture/blob/main/docs/configuration.md#languages).

Pin the check in CI to a release, in your ecosystem's form:

```yaml
# Python
- uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
- run: uvx --no-build --from living-architecture==0.4.0 la-arch-check
# TypeScript
- uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
- run: npx -y -p living-architecture@0.4.0 la-arch-check
```

### The whole flow

In the repo you want to onboard, run:

```
/la:init
```

It detects your tracker, test, lint and type-check commands, Codex, Sonar and any existing OpenSpec or
architecture setup, then proposes a `living-architecture.yaml` and asks only about what it cannot detect. It then
offers to set up OpenSpec, record the type-check baseline and build the architecture model with `/la:arch-init`.
After that, start each change with `/la:pr` on a branch named after its issue.

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

## How it differs from other import checkers

Import-boundary checkers already exist: [import-linter](https://github.com/seddonym/import-linter) for Python,
and [dependency-cruiser](https://github.com/sverweij/dependency-cruiser),
[eslint-plugin-boundaries](https://github.com/javierbrea/eslint-plugin-boundaries) and
[Nx module boundaries](https://nx.dev/docs/features/enforce-module-boundaries) for TypeScript. They check
imports against rules you write in a config file. `la` differs in what the rules are and what else is held to
them:

- The rules are a diagram. The LikeC4 model is the check, and the same model is drawn into the docs agents read,
  so the picture and the check can't disagree.
- The model must match the code exactly: an import with no arrow fails, and so does an arrow with no import.
- One model covers Python and TypeScript, in the same repo.
- Grandfathered arrows are pinned to a baseline in `architecture/index.yaml`, so adding one is a visible edit in
  review, never a silent one.
- Each element carries principles with status tags (the test that enforces it, the issue that will, or
  `[review]`), which `la-arch-check` verifies and every stage of the PR flow reads before it acts.

If all you need is layer rules for one language and you don't want a diagram, those tools are lighter.

When you move the pin to a release with a newer repo format, first run that release's `la-arch-migrate` and commit
the result: the check refuses a repo in an older format.

## Prerequisites

Always: `git`, `bash`, `gh` (authenticated) and `jq`.

Per repo language (`la-doctor` checks them):

| Language | Needs |
|---|---|
| Python | Python >= 3.11; the PyPI package; basedpyright in the project env for the type-check gate |
| TypeScript | `node` (>= 22) and `npx`; the npm package; `tsc` in `node_modules` for the type-check gate |

The rest is optional. `/la:init` detects what you have, asks before turning on anything it can't find, and
records the choice in `living-architecture.yaml`:

| Gate | Needs |
|---|---|
| `tracker: linear` | the Linear MCP server |
| `tracker: github` | nothing beyond `gh` |
| `openspec: true` | `npx` (the OpenSpec CLI) |
| `architecture: true` | `npx` (the LikeC4 CLI) |
| `reviewers.codex: true` | the Codex MCP server (`mcp__codex__codex`) |
| Sonar on your PRs | the SonarQube MCP server |

## Background

The ideas behind the plugin, and how it came out of the [SLayer](https://github.com/MotleyAI/slayer) codebase,
which uses it:

- [Why I no longer read code (much)](https://dev.to/egor_kraev_0e262330fbb44b/why-i-no-longer-read-code-much-1d59):
  the four-stage PR flow
- [How I enforce architecture on coding agents](https://dev.to/egor_kraev_0e262330fbb44b/how-i-enforce-architecture-on-coding-agents-141a):
  modularity and principle-based development
- [Living architecture, enforced](https://dev.to/egor_kraev_0e262330fbb44b/living-architecture-enforced-2ffh):
  the LikeC4 import law and the arc42 principles

## Documentation

- [Living architecture, explained](https://github.com/MotleyAI/living-architecture/blob/main/docs/living-architecture-explained.md):
  the problems it solves, one by one
- [Quickstart example](https://github.com/MotleyAI/living-architecture/blob/main/examples/quickstart/README.md):
  the architecture check on a toy repo
- [Skills](https://github.com/MotleyAI/living-architecture/blob/main/docs/skills.md): main and helper skills
- [Configuration](https://github.com/MotleyAI/living-architecture/blob/main/docs/configuration.md): `living-architecture.yaml` and the language sections of `architecture/index.yaml`
- [Commands](https://github.com/MotleyAI/living-architecture/blob/main/docs/commands.md): the `la-*` and `dr-*` commands, and CI
- [Deterministic refactoring](https://github.com/MotleyAI/living-architecture/blob/main/docs/deterministic-refactoring.md)
- [Development](https://github.com/MotleyAI/living-architecture/blob/main/docs/development.md): working from a checkout, layout, releasing
- [Contributing](https://github.com/MotleyAI/living-architecture/blob/main/CONTRIBUTING.md) and
  [release notes](https://github.com/MotleyAI/living-architecture/releases)
