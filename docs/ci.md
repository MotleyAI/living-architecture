# Running the checks in CI

Give this to your AI agent to set up CI. It adds a GitHub Actions job that runs the three architecture checks on
every pull request: `la-arch-check` (imports against the model, principle tags), `likec4 validate` (the model
itself) and `la-typecheck` (types against a baseline that only shrinks).

## Before the workflow

1. Commit `living-architecture.yaml`, `architecture/` and the type-check baseline (`.basedpyright/baseline.json`
   for Python, `.tsc-baseline.json` for TypeScript). `la-typecheck --write-baseline` creates a missing one.
2. Find the version to pin: `la-doctor` prints it as `ok: la tools X.Y.Z; …`. Pin that exact version everywhere
   below.

## The workflow

For a Python or a mixed Python + TypeScript repo:

```yaml
# .github/workflows/architecture.yml
name: architecture
on:
  pull_request:
  push:
    branches: [main]
jobs:
  architecture:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: 22    # the TypeScript twin and likec4 both need it
      - run: uvx --no-build --from living-architecture==0.6.0 la-arch-check
      - run: npx -y likec4@1.60.0 validate architecture
      - run: uv sync          # the project env, with basedpyright in it; only la-typecheck needs it
      - run: uvx --no-build --from living-architecture==0.6.0 la-typecheck
```

For a TypeScript-only repo, drop `setup-uv` and use these steps after `setup-node`:

```yaml
      - run: npx -y -p living-architecture@0.6.0 la-arch-check
      - run: npx -y likec4@1.60.0 validate architecture
      - run: npm ci           # puts tsc in node_modules; only la-typecheck needs it
      - run: npx -y -p living-architecture@0.6.0 la-typecheck
```

Replace `main` with the repo's default branch, and `uv sync` or `npm ci` with the repo's own install command
(`pnpm install --frozen-lockfile`, `yarn install --immutable`, …). `--no-build` installs only prebuilt wheels.

## Mixed repos

Use the Python workflow above; it is enough for `la-arch-check`. The Python twin hands the TypeScript files to
the npm twin through `npx`, at the same version. `la-typecheck` checks every repo language whose
`commands.typecheck` entry is not `null`, so in a mixed repo it usually needs both project environments: add the
TypeScript install (`npm ci`) before it.

## Node 22 is required

`setup-node` with `node-version: 22` serves more than `likec4`: in a mixed repo the Python twin runs the npm twin,
which needs Node 22 or later. On the runner's older default Node it crashes (on Node 18:
`TypeError: found.toSorted is not a function`).

## What needs a project install

- `la-arch-check` and `likec4 validate` need none. TypeScript imports resolve through the `tsconfig` paths
  without `node_modules`, so run them before any install step. The exception: a `tsconfig.json` that `extends` a
  package (`@tsconfig/node22/tsconfig.json`) cannot be read without `node_modules`, so install first.
- `la-typecheck` needs the checker and the project's dependencies, so the install must include the checker:
  declare `basedpyright` and `typescript` as dev dependencies. It looks for the checker in `.venv/bin` or
  `node_modules/.bin` at the repo root, then on `PATH`.
- Pin `basedpyright` to a version la has verified its pyright#11919 patch for (today `1.40.2`). `la-typecheck`
  applies the patch in memory and exits 2 on any other version.

## Poetry and projects outside the repo root

`uv sync` assumes a uv project at the repo root. Otherwise install the project the way the repo's CI already does
(for example `poetry install`, or `npm ci` in `web/`) and make the checker findable. `la-typecheck` runs
`commands.typecheck.<language>` from the repo root, so either:

- Set the command in `living-architecture.yaml`, which also works locally. Run it through the project's tool
  (`uv run --project backend basedpyright -p backend --baselinefile .basedpyright/baseline.json`), or give the
  checker's path (`web/node_modules/.bin/tsc -p web --noEmit`); a path is resolved from the repo root. With `-p`,
  basedpyright keeps its baseline in that directory unless `--baselinefile` points it to the repo root, where
  `la-typecheck` expects it. A Python command must run basedpyright under Node and keep `NODE_OPTIONS`, which
  carries la's patch.
- Or put the environment's `bin` directory on `PATH` for later CI steps, for example
  `echo "$PWD/backend/.venv/bin" >> "$GITHUB_PATH"`. For Poetry, `poetry env info --path` prints the
  environment's directory.

## Repos that already type-check in CI

If the repo's CI already gates type errors with its own baseline, drop the `la-typecheck` step and its install
step. Keep `commands.typecheck` in `living-architecture.yaml` as it is: the skills run `la-typecheck` locally.

## Triggers, path filters and required checks

- Trigger on `pull_request` and on pushes to the default branch only. `on: [push, pull_request]` runs every
  check twice on a PR branch.
- Do not add `paths:` or `paths-ignore:` filters. The checks cover the whole repo: a change anywhere (a new
  import, a moved file, a model edit) can break them.
- Make the `architecture` job a required status check in a branch protection rule or ruleset on the default
  branch, so a failing check blocks the merge. GitHub's Free plan offers this only for public repos; for a
  private repo it needs a paid plan. Without it, the check only reports.

## Moving the pin

When you move the pin to a release with a newer repo format, first run that release's `la-arch-migrate` and
commit the result: the commands refuse a repo in an older format.
