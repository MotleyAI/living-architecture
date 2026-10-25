# living-architecture

[![CI](https://github.com/MotleyAI/living-architecture/actions/workflows/ci.yml/badge.svg)](https://github.com/MotleyAI/living-architecture/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/living-architecture)](https://pypi.org/project/living-architecture/)
[![npm](https://img.shields.io/npm/v/living-architecture)](https://www.npmjs.com/package/living-architecture)
[![Python](https://img.shields.io/pypi/pyversions/living-architecture)](https://pypi.org/project/living-architecture/)
[![License: MIT](https://img.shields.io/github/license/MotleyAI/living-architecture)](https://github.com/MotleyAI/living-architecture/blob/main/LICENSE)

![living-architecture: a LikeC4 model allows api → core → store and rejects the api → store shortcut; the arc42 principles of core carry enforced, review and target status tags](https://raw.githubusercontent.com/MotleyAI/living-architecture/main/docs/images/living-architecture.png)

A Claude Code plugin + CLI for agents writing Python and TypeScript code:

* **Normative principles attached to a
[LikeC4](https://likec4.dev) architecture model, which also serves as an import whitelist.** 

* **Enforced by a complete
PR workflow that generates [OpenSpec](https://github.com/Fission-AI/OpenSpec) changes, whose archives double as
ADRs.**

## Introduction

Every PR an agent writes can be reasonable on its own while the codebase still drifts, one shortcut at a time.
Rules in `CLAUDE.md` don't hold: the agent quotes a principle back to you and then breaks it. And six months later,
nobody can say why the code is the way it is. The plugin, `la`, answers all three with files in your repo that have the status
of tests:

- **Principles attached to the parts of your code.** A [LikeC4](https://likec4.dev) model maps your packages to
  elements, and each element carries its own [arc42](https://arc42.org) file of normative principles, each tagged
  with how it is enforced. Every stage of a change starts by reading the principles of what it touches, and
  changing a principle needs your approval.
- **A complete PR workflow.** `/la:pr` interviews you into a Codex-reviewed plan, writes the failing tests,
  implements until they pass, then loops CI, Codex, CodeRabbit and Sonar until every gate is clean. Each stage
  ends at a hard stop and resumes from the branch name alone.
- **A decision record for every PR.** The plan is a validated OpenSpec change. Before the PR merges, its specs
  are folded into the repo's living behaviour specs, and its design, with the decisions and the alternatives it
  rejected, is archived in the same PR as the code: an ADR you never had to write.
- **An architecture that is enforced, not just drawn.** The model's arrows decide which modules may import which,
  and `la-arch-check` fails when the real imports disagree.

For the details, see [How it works](https://github.com/MotleyAI/living-architecture/blob/main/docs/how-it-works.md) and
[Living architecture in questions and answers](https://github.com/MotleyAI/living-architecture/blob/main/docs/living-architecture-in-questions-and-answers.md).

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

### The whole flow

In the repo you want to onboard, run:

```
/la:init
```

It detects your tracker, test, lint and type-check commands, Codex, Sonar and any existing OpenSpec or
architecture setup, then proposes a `living-architecture.yaml` and asks only about what it cannot detect. It then
offers to set up OpenSpec, record the type-check baseline and build the architecture with `/la:arch-init`, which
starts from a model measured from your code and then interviews you about the target structure and the
principles.

After that, start each change on a branch named after its issue with:

```
/la:pr
```

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

## How it relates to other tools

- **Import-boundary checkers** ([import-linter](https://github.com/seddonym/import-linter) for Python;
  [dependency-cruiser](https://github.com/sverweij/dependency-cruiser),
  [eslint-plugin-boundaries](https://github.com/javierbrea/eslint-plugin-boundaries) and
  [Nx module boundaries](https://nx.dev/docs/features/enforce-module-boundaries) for TypeScript) check imports
  against rules in a config file. In `la` the rules are the same diagram the agent reads, they must match the code
  in both directions, one model covers Python and TypeScript, and the import law is only the backbone that the
  principles and the specs hang on. If all you need is layer rules for one language, those tools are lighter.
- **OpenSpec on its own** gives you the spec format and the archive. `la` drives it: the plan stage writes and
  validates the change, the later stages hold the code to it, and the review stage archives it with the PR.
- **ADRs written by hand** tend to stop being written. Here the decision record is a by-product of planning the
  change, so every PR has one.

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

- [How it works](https://github.com/MotleyAI/living-architecture/blob/main/docs/how-it-works.md): the principles, the PR workflow, its ADRs
  and the import check, and how to use the check on its own
- [Living architecture in questions and answers](https://github.com/MotleyAI/living-architecture/blob/main/docs/living-architecture-in-questions-and-answers.md):
  the problems it solves, one by one
- [Skills](https://github.com/MotleyAI/living-architecture/blob/main/docs/skills.md): main and helper skills
- [Configuration](https://github.com/MotleyAI/living-architecture/blob/main/docs/configuration.md): `living-architecture.yaml` and the language sections of `architecture/index.yaml`
- [Commands](https://github.com/MotleyAI/living-architecture/blob/main/docs/commands.md): the `la-*` and `dr-*` commands, and CI
- [Deterministic refactoring](https://github.com/MotleyAI/living-architecture/blob/main/docs/deterministic-refactoring.md)
- [Development](https://github.com/MotleyAI/living-architecture/blob/main/docs/development.md): working from a checkout, layout, releasing
- [Contributing](https://github.com/MotleyAI/living-architecture/blob/main/CONTRIBUTING.md) and
  [release notes](https://github.com/MotleyAI/living-architecture/releases)
