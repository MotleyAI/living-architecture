# How it works

## Principles live with the code they govern

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

## `/la:pr` takes a change from issue to mergeable PR

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

## Every merged PR leaves its ADR

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

## The model is checked against the imports

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

See the model and principles this repo holds itself to in
[`architecture/system.arc42.md`](../architecture/system.arc42.md).

## Just the architecture check

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
[Configuration](configuration.md#languages).

Pin the check in CI to a release, in your ecosystem's form:

```yaml
# Python
- uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
- run: uvx --no-build --from living-architecture==0.4.1 la-arch-check
# TypeScript
- uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
- run: npx -y -p living-architecture@0.4.1 la-arch-check
```

When you move the pin to a release with a newer repo format, first run that release's `la-arch-migrate` and commit
the result: the check refuses a repo in an older format.
