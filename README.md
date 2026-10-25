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

## How it works

### Principles live with the code they govern

Each element of the model, at any depth, can have an `architecture/<element id>.arc42.md` file. Its principles
hold for that element and everything inside it; `system.arc42.md` holds the cross-cutting ones. Every principle
carries a status tag: the test or check that enforces it, the issue that will make it hold, or `[review]` for one
that is believed to hold but not yet enforced. For the `core` package of a toy shop:

```markdown
## Principles

1. Every order total is computed in `core`, never by a caller. [enforced: test:tests/test_pricing.py]
2. `core` never reads the clock; callers pass the time in. [target: SHOP-42]
3. Order rules hold for every caller, so nothing reaches `store` around `core`. [review]
```

`la-arch-check` verifies the tags. `la-arch-diagrams` writes the element's part of the model into the file as a
mermaid diagram, and the check fails when it is out of date, so an agent reads structure and rules in one place. Your OpenSpec specs are mapped to elements too, so every
spec has an owner in the architecture.

Agents treat the model and the principles like tests: every change to them needs your explicit approval. When a
change strains a principle, the agent first makes the code comply.

### `/la:pr` takes a change from issue to mergeable PR

Start on a branch named after its issue (Linear or GitHub) and run `/la:pr`. It works out the stage from the
branch and dispatches to it:

| Stage | What happens |
|---|---|
| 1. Plan | Interviews you, knowing the code, to find the edge cases and the interactions with the rest of it. Names the principles that apply. Codex reviews the plan, and it is written as a validated OpenSpec change: proposal, design, tasks and scenarios. |
| 2. Tests | Writes failing tests from the plan's scenarios. Codex reviews them for completeness against the plan. |
| 3. Implement | Implements until every test passes, then commits, pushes and opens the PR on your go-ahead. If the plan turns out wrong, it stops and asks: the plan has the status of the tests. |
| 4. Review | Loops the deterministic gates (conventions, type check, architecture), CI, CodeRabbit, Sonar and Codex, triaging and fixing every finding until all of them are clean. Then archives the OpenSpec change on your go-ahead. |

Every stage ends at a hard stop, so you can reset the session between stages: everything the next stage needs is
on disk or in the issue tracker.

### Every merged PR leaves its ADR

Archiving folds the change's spec deltas into `openspec/specs/`, which always describes how the system behaves
now, and moves the change itself, in the same PR as the code, to a dated folder:

```
openspec/changes/archive/2026-10-24-declared-format-version/
  proposal.md   why the change was made, and what it changes
  design.md     the decisions, each with the alternatives it rejected
  tasks.md
  specs/        the behaviour it added, changed or removed
```

So when you wonder why a line is written the way it is, find the PR that introduced it and read its design. One
decision from this repo's own archive:

> **One repo-wide key `format` in `living-architecture.yaml`**, over a key in `index.yaml` or one per file: the
> user chose one number; the first action on any older repo is a deterministic migration.

An element's arc42 rationale links the archived changes it derives from, so the principles point back to the
decisions behind them.

### The model is checked against the imports

The elements of `architecture/model.c4` map to packages or directories, and an arrow is the only thing that
licenses an import:

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

Imports the code has today but the target architecture doesn't want are marked `#legacy` and counted against a
baseline that the skills only ever lower; `/la:arch-cleanup` retires them a batch at a time. The moves that takes
are done by `/la:deterministic-refactor`, which rewrites every import for you (rope for Python, the TypeScript
language service for TypeScript) and has the type checker prove nothing was left dangling.

Try the check in five minutes with the
[quickstart example](https://github.com/MotleyAI/living-architecture/blob/main/examples/quickstart/README.md),
or see the model and principles this repo holds itself to in
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

### The whole flow

In the repo you want to onboard, run:

```
/la:init
```

It detects your tracker, test, lint and type-check commands, Codex, Sonar and any existing OpenSpec or
architecture setup, then proposes a `living-architecture.yaml` and asks only about what it cannot detect. It then
offers to set up OpenSpec, record the type-check baseline and build the architecture with `/la:arch-init`, which
starts from a model measured from your code and then interviews you about the target structure and the
principles. After that, start each change with `/la:pr` on a branch named after its issue.

### Just the architecture check

You can enforce the model without the plugin or the PR flow. Tell the checker where your code lives in
`architecture/index.yaml`:

```yaml
python:
  root_package: mypkg      # the package the model's python root maps to
  source_root: src         # optional
legacy_arrows: {baseline: 0}
```

Then declare in `living-architecture.yaml`, at the repo root, that the repo has an architecture model:

```yaml
architecture: true
```

Stamp the repo format, write a first model from the imports the code has today, and check it:

```bash
la-arch-migrate       # adds format: to living-architecture.yaml
la-arch-scaffold      # writes architecture/model.c4, views.c4 and system.arc42.md from the measured imports
la-arch-check
```

The scaffold allows every import that exists, so the first check passes once any OpenSpec specs you have are
mapped to elements. Then mark the arrows you don't want as `#legacy`, set `legacy_arrows.baseline` to their count
and run `la-arch-diagrams`. That is the one time to raise the baseline. To retire a legacy arrow later, remove it
together with the imports behind it and lower the baseline to the new count, all in one change: the check fails
on an arrow or an import left alone, and on any difference between the count and the baseline. TypeScript and
mixed repos are set up the same way; see
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

When you move the pin to a release with a newer repo format, first run that release's `la-arch-migrate` and commit
the result: the check refuses a repo in an older format.

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
