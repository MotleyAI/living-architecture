Session rule: before starting each task group, estimate whether the group fits in the remaining context. If
it does not, stop at the group boundary, tick what is done, commit, and ask the user to start a new session.

## 1. Prerequisites

- [x] 1.1 Merge DEV-2025's branch into this branch (`git merge` with a quoted ref; never rebase). If DEV-2025 is not yet implemented and merged, STOP and tell the user, because nothing below can start. Verify: `node/` exists, `index.yaml` has language sections, and the full suites of both twins pass.
- [x] 1.2 Re-read the DEV-2025 specs as archived (arch-check, twin-forwarding, shared-contract) and check that this change's specs still line up. Any mismatch is a plan change: present the exact diff to the user before editing. Verify: `openspec validate dev-2033-living-architecture-smoother-init-workflow --strict` passes.

## 2. Shared contract

- [x] 2.1 `shared/schema/living-architecture.schema.json`: add `tracker`, `openspec`, `architecture`, `reviewers.codex` and `conventions.rules` (enum of the registry rule ids, default all); remove `reviewers.coderabbit` and `reviewers.sonar.enabled`, plus the if/then rule. Verify: the repo-config and shared-contract config scenarios have cases.
- [x] 2.2 `shared/cli.yaml`: add `la-doctor --require-config`, `la-pr-reviewers` (script command) and `la-arch-scaffold`; add `--top-level` to the internal facts options; remove `gate` from `la-wait-for-reviews` and from the manifest header. Verify: the manifest-driven parser tests pass in both twins.
- [x] 2.3 `shared/findings.yaml`: add templates for missing config (naming `/la:init`), each consistency finding, scaffold refusals (existing file, id collision) and the written-path line. Verify: 7.4's mapping covers each new id.
- [x] 2.4 `shared/scripts/`: add a shared detection helper (CodeRabbit by status or comment; Sonar check and key precedence) and `pr-reviewers.sh`; make `wait-for-reviews.sh` use the helper and drop `--skip-coderabbit`. Verify: the review-detection cases pass.
- [x] 2.5 Run `scripts/sync-shared`. Verify: the drift test passes and both snapshots carry the new contract hash.

## 3. Config and doctor (both twins)

- [x] 3.1 Config resolution with the new keys and removals in both twins. Verify: conformance `la-config` cases (defaults, removed keys, unknown tracker, unknown rule, falsy values kept, YAML 1.1 `codex: no`).
- [x] 3.2 `la-doctor --require-config` and the consistency checks (only when the file exists; `architecture/index.yaml` as the marker; fixed finding order) in both twins. Verify: one conformance case per repo-config doctor scenario, including the unrelated `architecture/` directory and several inconsistencies.
- [x] 3.3 Remove the `skip-coderabbit` gate code from both twins' `review` node and add the `la-pr-reviewers` shim. Verify: conformance cases with a fake `gh` for every review-detection scenario, run through both twins.

## 4. Conventions gate (both twins)

- [x] 4.1 `la-check-conventions` honours `conventions.rules` in the invoking twin's report (file errors only when some rule applies; waivers for rules that are not configured have no effect). Verify: conformance cases for every scenario of the conventions delta, run through both twins.

## 5. Arch scaffold (both twins)

- [x] 5.1 Top-level facts mode (`--top-level`): in each adapter, attribute module edges to top-level units, read no model, exclude self-edges; extend `facts.schema.json` if needed. Verify: conformance cases (no model, intra-unit edge, forwarded).
- [x] 5.2 `la-arch-scaffold`: precondition checks, id derivation and collisions, in-memory rendering of the model, views, arc42 (with generated diagrams) and the index additions, then the writes. Verify: conformance cases for Python, TS and mixed repos, a cycle, an isolated unit, a hyphenated unit, a leading digit, a collision (repo unchanged), an existing model, a missing index and an unreachable twin.
- [x] 5.3 Scaffold-then-check cases: no specs gives `la-arch-check` exit 0; an unmapped spec gives exactly the unmapped findings. Verify: both goldens.

## 6. Skills

- [x] 6.1 New `plugin/skills/init/SKILL.md` per design D11 (detection list, the proposal with a source per key, one question round with pros/cons/recommendation, OpenSpec scaffold before writing, `issue_key_pattern` per tracker, the fast path, editing in place, converting legacy keys). Verify: `test_skills.py` passes.
- [x] 6.2 New `plugin/skills/arch-init/SKILL.md` (preconditions including a `la-typecheck` baseline, writing the language sections, `la-arch-scaffold`, the wedge interview, principles drafted from CLAUDE.md/AGENTS.md and approved one by one, folding in ADRs, spec mapping, green check, flipping `architecture: true`, no CI). Remove Init and Migrate from `living-architecture`, point it to `la:arch-init`, and keep it as reference plus maintenance. Verify: `test_skills.py`.
- [x] 6.3 Rename `arch-slice` to `arch-cleanup` (directory, frontmatter, every reference). It gates on `la-typecheck` and stops when that checks no language; `deterministic-refactor` does the same. Verify: `test_skills.py` reference check; no `arch-slice` left (`grep -r arch-slice plugin docs README.md AGENTS.md`).
- [x] 6.4 Preflight: main skills except `init`, plus the four stages, use `--require-config` with the D1 routing text; helpers keep the plain line. Verify: new `test_skills.py` check.
- [x] 6.5 `la:pr` and the stages: tracker per config (D5, GitHub linked-branch join, plan comment per tracker), `OPENSPEC` from config, "the tracker" wording, Codex per `reviewers.codex` (stop if missing), the `la-typecheck` gate in pr-implement and pr-review with the single ratchet description. Verify: `test_skills.py`.
- [x] 6.6 Split `process-reviews` / `pr-review` per D12 (detection via `la-pr-reviewers`, ending standalone versus when invoked, CodeRabbit reply rule moved, single conventions-gate description, duplicated non-terminal block removed); `codex-review` follows `reviewers.codex`. Verify: `test_skills.py`, and a read-through confirming no rule is lost (list each moved rule in the commit message).

## 7. Docs, this repo and tests

- [x] 7.1 `docs/living-architecture-explained.md` (the "Living-architecture explained" Notion page, https://app.notion.com/p/Living-architecture-explained-3ebfa3f9cb6080ed9ddffa056f77a5dd, fetched with the Notion MCP; it is also the source for the README intro in 7.2. Content cleaned up, real skill names, two parts), `docs/skills.md` (Main / Helper sections), `docs/configuration.md`, `docs/commands.md`, `docs/deterministic-refactoring.md` (moved), `docs/development.md` (local checkout, releasing, layout). Verify: the link test in 7.3.
- [x] 7.2 Rewrite `README.md`: Notion-style intro, quick start (`/la:init`), main-skills table, prerequisites split into required and per-gate, absolute `docs/` links; remove "Upgrading from nodes:" and "Upgrading to language roots" with no replacement page (no repo uses the old layouts); move the two-twins paragraph to `docs/commands.md`, keeping one README line that the commands ship as a PyPI and an npm package. Update AGENTS.md references. Verify: the 7.3 tests and `scripts/sync-shared`.
- [x] 7.3 `test_skills.py`: `docs/skills.md` lists every skill exactly once; main skills (except `init`) and the stages use `--require-config` and helpers don't; the README skills table equals the main skills; relative links in README and `docs/` resolve; absolute `blob/main/docs/` links name existing files.
- [x] 7.4 Map every new `findings.yaml` id to a named conformance case and list every new case in `conformance/INVENTORY.md`. Verify: the registry-coverage and inventory tests pass.
- [x] 7.5 This repo: explicit `living-architecture.yaml` (`tracker: linear`, `openspec: true`, `architecture: true`, `codex: true`, the commands). Present, then (with the user's per-edit OK) write any arc42 or model edit. Verify: `la-doctor --require-config` and `la-arch-check` exit 0.

## 8. Final gate

- [x] 8.1 Full suites of both twins, ruff, basedpyright, `scripts/sync-shared --check`, `npx -y @anthropic-ai/claude-code plugin validate plugin`, `la-arch-check`, and `openspec validate dev-2033-living-architecture-smoother-init-workflow --strict`, all green.
- [x] 8.2 Add the spec placement from design.md Context (before the archive, since live-change spec groups count for spec-mapping): repo-config under cross_cutting_specs in index.yaml; review-detection and arch-scaffold in the specs metadata of python.review and python.archcheck. Verify: la-arch-check exits 0.
