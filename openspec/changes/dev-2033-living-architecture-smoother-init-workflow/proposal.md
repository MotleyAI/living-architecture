## Why

Onboarding a repo is manual and lossy. Nothing asks the user what the repo has, so the flow decides by
itself: it asks again on every change whether to use OpenSpec, assumes CodeRabbit is off when there is no
config file, and silently skips Codex when its server is missing. Building the first architecture model means hand-writing a throwaway import-graph script. The
README lists every skill and command, so a newcomer cannot tell where to start. This change adds one guided,
mostly detected setup (`la:init`), records each gate as an explicit decision in `living-architecture.yaml`,
makes the first model a deterministic scaffold, and rewrites the docs around onboarding.

## What Changes

- **`la:init` skill**: detects the tracker, Codex, Sonar, test/lint/type-check commands and existing
  OpenSpec/architecture setup. It proposes a full `living-architecture.yaml` with a source for each key and
  asks only about opinion-based or undetected keys. It writes the file, then offers the OpenSpec scaffold,
  the type-check baseline and `la:arch-init`. When another skill finds no config, it runs a fast path and
  hands back.
- **Explicit gates in the config**: new keys `tracker` (`linear | github | none`), `openspec`,
  `architecture`, `reviewers.codex` and `conventions.rules`.
- **BREAKING**: `reviewers.coderabbit` and `reviewers.sonar.enabled` are removed. Both bots are now detected
  per PR. `reviewers.sonar.project_key` stays as an override.
- **`la-doctor --require-config`**: a missing config file is a finding that names `/la:init`. When the file
  exists, the doctor also checks that the `openspec`/`architecture` flags agree with the disk, and rejects
  `tracker: none` together with `openspec: false`.
- **`la-check-conventions`** reports only the rules listed in `conventions.rules`, in both twins.
- **New `la-pr-reviewers`** reports whether CodeRabbit and Sonar ran on a PR, plus the Sonar project key.
  **BREAKING**: `la-wait-for-reviews` loses `--skip-coderabbit` and the manifest's `gate` field, and detects
  CodeRabbit the same way.
- **New `la-arch-scaffold`** writes a starter model, views, `system.arc42.md` and the rest of `index.yaml`
  from the measured top-level units and import edges of every declared language, all in one atomic write.
  The facts exchange between twins gains a top-level mode that needs no model.
- **Skills**:
  - New `la:arch-init` (guided architecture bootstrap). The Init and Migrate sections leave
    `la:living-architecture`, which becomes a reference.
  - `la:arch-slice` is renamed `la:arch-cleanup`.
  - Main skills preflight with `--require-config`; helpers never gate on the config file.
  - `la:pr` follows `tracker` (with GitHub linked-branch lookup) and `openspec`.
  - The Codex steps follow `reviewers.codex` and stop when the server is missing.
  - `la-typecheck` is a local gate in pr-implement and pr-review.
  - `process-reviews` owns one review sweep; `pr-review` owns the loop. The duplication between them goes.
- **Docs**:
  - An onboarding README with an intro based on "Living-architecture explained", a quick start and the
    main skills only.
  - New `docs/` pages: `living-architecture-explained.md`, `skills.md` (main vs helper),
    `configuration.md`, `commands.md`, `deterministic-refactoring.md` and `development.md`.

## Capabilities

### New Capabilities
- `repo-config`: the gate keys of `living-architecture.yaml`, `la-doctor --require-config`, and the
  config/disk consistency checks.
- `review-detection`: per-PR detection of CodeRabbit and Sonar (`la-pr-reviewers`, `la-wait-for-reviews`).
- `arch-scaffold`: `la-arch-scaffold`, and the top-level facts mode it relies on.

### Modified Capabilities
- `conventions`: a requirement selecting which rules the gate enforces.
- `shared-contract`: the config-schema and YAML-profile requirements, whose scenarios name the removed
  `reviewers.coderabbit` and `reviewers.sonar.enabled` keys.

## Impact

- `shared/`: `schema/living-architecture.schema.json`, `schema/facts.schema.json` (from DEV-2025),
  `cli.yaml` (`la-doctor --require-config`, `la-pr-reviewers`, `la-arch-scaffold`, no `gate`),
  `findings.yaml`, `scripts/` (new `pr-reviewers.sh`, a shared detection helper, `wait-for-reviews.sh`).
  Both snapshots are re-synced and the contract hash changes.
- Both twins: `config`, `doctor`, `review`, `archcheck` and `conventions`, plus `lang` for top-level facts.
- `plugin/skills/`: new `init` and `arch-init`; `arch-slice` renamed to `arch-cleanup`; edits to `pr`, the
  four stages, `process-reviews`, `living-architecture`, `deterministic-refactor` and `codex-review`.
- `README.md`, new `docs/`, `living-architecture.yaml` of this repo, `architecture/index.yaml` (spec
  mapping), `conformance/` cases plus `INVENTORY.md`, and `python/tests/test_skills.py`.
- Builds on DEV-2025 (language roots, npm twin, facts provider) and DEV-2026 (native conventions in both
  twins, `la-typecheck`), both merged on main.
- Target repos with `reviewers.coderabbit` or `reviewers.sonar.enabled` delete those keys. `la:init`
  proposes this edit.
