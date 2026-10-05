## Context

DEV-2025 (merged on main) added language roots in `index.yaml` and the model,
the npm twin, and a per-language facts exchange (`la-arch-check --language L --emit facts`). Every
command-level behaviour below lands in both twins. DEV-2026 (merged on main) made `la-check-conventions`
native in both twins and added `la-typecheck` with the per-language `commands.typecheck` map. Skill behaviour
is prose and is pinned only structurally (`python/tests/test_skills.py`).

Applicable `system.arc42.md` principles: 1 (twins identical, the corpus decides), 2 (parameters, defaults and
texts only from `shared/`), 3 (language-specific code only in `lang`/`refactor`; scaffold id rules are
language-neutral and live in `archcheck`) and 4 (tools never import or execute target-repo code, except a
configured `commands.*` command).

Spec placement in `architecture/index.yaml`, following DEV-2025's precedent (a twinned spec maps to its
PyPI-twin node, e.g. `arch-check` → `python.archcheck`, `twin-forwarding` → `python.twin`):
- `repo-config`: `cross_cutting_specs`, touching `python.config` and `python.doctor`.
- `review-detection`: `python.review` metadata `specs`.
- `arch-scaffold`: `python.archcheck` metadata `specs`.
- `conventions`: the rule selection is an added requirement of the existing spec, already mapped to
  `python.conventions`.

## Goals / Non-Goals

**Goals:** onboarding in one short interview; every gate an explicit, doctor-checked decision; helpers that work
in any repo; a deterministic first model.

**Non-Goals:**
- No `make-diff-compliant` gate in the flow.
- No CI wiring by `la:init` or `la:arch-init`.
- No release or version bump.
- No migration skill for `index.yaml` `nodes:` (`la-arch-check` keeps refusing it).
- No deterministic tests of interview branches (skill prose).

## Decisions

**D1: Config presence means "onboarded", detected by `la-doctor --require-config`.** Only main skills (except
`la:init`) and the four stages pass it. If their preflight output contains the missing-config finding, they
run `la:init`'s fast path, then re-run the full preflight and stop on anything left. Helpers keep the plain
preflight. Alternatives:
- each skill testing for the file itself: N copies, and it ignores `--root` resolution;
- making the file mandatory for every command: breaks helpers and CI-only `la-arch-check`.

**D2: `openspec`/`architecture` are explicit flags kept consistent with the disk by the doctor.** The flag is
the decision and the directory its result. The marker for architecture is `architecture/index.yaml` in both
directions, so an unrelated `architecture/` docs folder is not a conflict. Consistency checks run only when
the file exists, so unconfigured repos keep today's behaviour. Alternatives:
- disk-only: a declined OpenSpec gets asked again on every change;
- a tri-state "declined" flag: an absent key would still mean "whatever is on disk".

**D3: Review bots are facts of the PR, not config.** CodeRabbit is present if it has a status check or any
comment on the PR; the comment signal closes the race where a fresh push hasn't posted its status yet. Sonar
is present if a check name contains `sonar`. A single detection function in the script bundle serves
`la-pr-reviewers` and `la-wait-for-reviews`. The project key is the only remaining Sonar setting, because it
cannot always be inferred. Alternative: keeping the flags only for skills, which leaves a setting whose only
effect is ignoring feedback that really exists.

**D4: `reviewers.codex` is a repo-level decision.** When it is on and the MCP server is missing, the flow
stops rather than skipping, so the repo's review bar never depends on who runs the flow. Alternative:
runtime detection, which silently weakens the review.

**D5: `tracker: linear | github | none`.**
- GitHub join: the branch's leading `<N>-` (after any `<user>/`) must be among issue N's linked branches
  (`gh issue develop --list N`). GitHub has no reverse lookup, so a miss asks whether to proceed with the
  typed brief only.
- The plan store with OpenSpec off is a tracker comment (`gh issue comment` for GitHub).
- `none` with `openspec: false` is a doctor finding, because the plan would not survive a reset.
- `la:init` proposes `issue_key_pattern` `#\d+` for GitHub.

**D6: `conventions.rules` is enforced by the command.** One key expresses both "drop a rule" and "gate off"
(`[]`). File errors appear only when some rule checks the file. Alternative: a skill-side `enabled`, which is
all-or-nothing and untested.

**D7: The type-check gate is `la-typecheck`.** DEV-2026 owns the command, the per-language
`commands.typecheck` map and the baselines (`.basedpyright/baseline.json`, `.tsc-baseline.json`). `la:init`
detects each language's checker and proposes a `commands.typecheck` entry only where the default does not
fit, then offers `la-typecheck --write-baseline` when an applicable language has no baseline. The ratchet
rule (never re-record; root-fix; shrink only) has one description, at the gate in pr-implement and
pr-review. `la:arch-cleanup` and `la:deterministic-refactor` stop when `la-typecheck` checks no language.

**D8: Scaffold measures through a top-level facts mode.** DEV-2025's facts attribute edges to elements of an
existing model, and a forwarded twin reads that model from disk. `--top-level` attributes module edges to
top-level units with no model at all, so scaffold computes every output in memory before writing anything,
which makes it atomic. Alternative: writing nodes first, asking for element facts and then appending
arrows, which leaves partial files on failure and blocks retries. The scaffold guarantees a clean
`la-arch-check` only when no specs exist; otherwise unmapped-spec findings remain for `la:arch-init` to
resolve.

**D9: Scaffold inputs come from `index.yaml`.** `la:arch-init` writes the language sections, and the scaffold
completes only absent keys. The index schema stays the single description of a language root. Alternative:
per-language CLI flags duplicating that schema.

**D10: Skill roles.**
- Main skills: `la:init`, `la:pr`, `la:arch-init`, `la:arch-cleanup`, `la:deterministic-refactor`.
- Everything else is a helper. `docs/skills.md` is the source, and a test checks that it agrees with the
  skills directory, the preflight variant and the README table.
- `la:living-architecture` becomes a reference: no Init, no Migrate.
- `la:arch-init` holds the bootstrap and refers to the reference for syntax.

**D11: `la:init` order.**
1. detect;
2. propose the YAML with a source for each key;
3. one question round;
4. run the chosen OpenSpec scaffold;
5. write the file with flags matching the disk (`architecture: false` until `la:arch-init` finishes);
6. `la-doctor --require-config`;
7. offer the type-check baseline and `la:arch-init`.

The fast path (triggered by another skill) stops after step 6. A re-run on a configured repo edits in place.
A config with removed keys is read as raw YAML, and the skill proposes the conversion and validates it.

**D12: `process-reviews` is one sweep; `pr-review` is the loop.**
- process-reviews owns all per-source knowledge: detection, the wait, fetching, validation, invalid
  handling (including the reply-to-every-unresolved-thread rule) and the conventions gate's only full
  description.
- Run standalone, it ends with the grouped plan and waits; invoked from pr-review, it returns the triaged
  list for autonomous fixing.
- pr-review keeps the gate tiers, the push-once policy, the complete-CI rule, the symptom-versus-structural
  rule, convergence and the archive.

**D13: Docs.** `README.md` is the PyPI long description too, so its `docs/` links are absolute
`https://github.com/MotleyAI/living-architecture/blob/main/docs/...` URLs. The `docs/` pages use relative
links to each other.

## Risks / Trade-offs

- [Removed config keys break existing configs] → the schema error names the key, and `la:init` proposes the
  edit.
- [Sonar detection depends on check names containing `sonar`] → `reviewers.sonar.project_key` covers key
  inference, and an undetected Sonar is visible in the plan header's source counts.
- [`codex: true` committed while a teammate lacks Codex] → the flow stops with a clear message; flipping the
  key is an explicit repo decision.
- [Scaffold ids are sanitised] → titles keep the raw names, and collisions are an error rather than a
  silent merge.
