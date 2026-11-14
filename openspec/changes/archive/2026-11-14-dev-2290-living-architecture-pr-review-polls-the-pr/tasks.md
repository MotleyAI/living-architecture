## 1. Tests (pr-tests stage; all fail before implementation)

- [x] 1.1 Add one neutral conformance case per ADDED scenario of `specs/review-detection/spec.md` ("la-wait-for-reviews prints each new item once"): `shim-wait-for-reviews-*` with a fake `gh`, `LA_WAIT_POLL_SECONDS: '0'`, cross-poll dedupe expressed with sequenced `responses`; only the malformed-file case seeds the state file (`write:` of `not json`); goldens `golden: manual`, hand-written from the spec's line formats; verify each fails against the current script
- [x] 1.2 Add cases for the new MODIFIED scenarios ("Rate limited while checks run", "Rate limited, then reviewed before the checks finish") and verify they fail
- [x] 1.3 Add `shim-fetch-failed-pr-checks-check-*` cases for each scenario of `specs/failed-pr-checks/spec.md` and verify they fail
- [x] 1.4 Add matching tests to `python/tests/test_review_scripts.py` where a conformance case cannot express the scenario (the concurrent-run union: another run's key written mid-run; a second run prints nothing new; outside a git repository); verify they fail
- [x] 1.5 List every new case in `conformance/INVENTORY.md` under the review-shim sections; `uv run pytest -q python/tests/test_conformance.py -k inventory` passes

## 2. Implementation (pr-implement stage)

- [x] 2.1 `shared/scripts/fetch-failed-pr-checks.sh`: `--check X` keeps failed checks whose Details URL or name equals X; verify 1.3 passes
- [x] 2.2 `shared/scripts/wait-for-reviews.sh`: one poll loop at `LA_WAIT_POLL_SECONDS` reading the gate, Sonar suites, CodeRabbit comments/reviews and settle evidence on every poll; progress to stderr; item lines to stdout with the design's keys; exit codes per the MODIFIED settle requirement; verify 1.1–1.2 pass
- [x] 2.3 State file at `git rev-parse --git-path la/reviews/<owner>/<repo>/<PR>.json`: read (missing → empty; malformed → warn + empty), re-read + union + atomic rename on write, warn and continue on a failed write, in-memory with a stderr note outside git; verify the state scenarios and 1.4 pass
- [x] 2.4 `shared/cli.yaml` help texts per design decision 14; update the script header comments and usage to match
- [x] 2.5 Run `scripts/sync-shared`; `scripts/sync-shared --check` passes
- [x] 2.6 Update the `stderr` goldens of every existing `shim-wait-for-reviews-*` case to the new progress output: by hand for the `golden: manual` cases (the update mode never writes them), with `LA_UPDATE_GOLDENS=1` for the rest; review the diff so only progress lines moved to stderr appear (the `stdout` goldens were aligned to the item lines in pr-tests); state the reason in the commit message
- [x] 2.7 Apply the skill edits of design decisions 15 (`plugin/skills/process-reviews/SKILL.md`) and 16 (`plugin/skills/pr-review/SKILL.md`) verbatim; `npx -y @anthropic-ai/claude-code plugin validate plugin` passes
- [x] 2.8 Run the local test scope (`la-affected-tests --base main` plus the conformance corpus through both twins: `uv run pytest -q` in `python/` for the shim cases, `npm run build && npm run conformance` in `node/`), lint, `la-typecheck`, `la-check-conventions --base main`, `la-arch-check`, `openspec validate dev-2290-living-architecture-pr-review-polls-the-pr --strict`; all green
