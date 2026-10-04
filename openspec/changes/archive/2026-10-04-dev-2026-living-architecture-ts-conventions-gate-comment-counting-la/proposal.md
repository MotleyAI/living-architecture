## Why

The conventions gate and the comment counter only understand Python, so a TS/JS change passes the gate unchecked
and a TS-only repo has to reach for the PyPI twin to run them. Nothing ratchets type errors through one command
either: each skill names the checker and its baseline by hand. This is PR 3 of 4 under DEV-1990; it builds on the
npm twin, the facts transport and the language roots of DEV-2025.

## What Changes

- **TS adapter, part 2** (npm twin `lang`): the conventions rules for `.ts/.tsx/.mts/.cts/.js/.jsx/.mjs/.cjs`
  (import-not-top after import/first + n/global-require, text-ratio, composite-assert, raises-single-throw,
  `// ALLOW(<rule>): <reason>` waivers) and comment/JSDoc line counts, with TS-worded findings.
- **Routing by extension**: `la-check-conventions` and `la-count-comments` become neutral. Each file is analysed by
  its language's adapter (natively, or through the other twin as a schema-checked facts document); waivers,
  test-file classification, text-ratio, ordering and the verdict run once in the invoking twin, so the output is
  the same whichever twin runs. Explicit paths with an unknown extension are skipped with a warning.
  **BREAKING**: a Python repo whose diff touches TS/JS files now has them checked (needs the npm twin); explicit
  unknown-extension paths are no longer analysed as Python.
- Changed files are listed NUL-delimited, fixing non-ASCII paths that git quoted and the gate then skipped.
- **`la-typecheck [--write-baseline]`** in both twins: runs each applicable language's checker (basedpyright
  passthrough; the repo's own tsc against an auto-shrinking `.tsc-baseline.json` multiset) under one exit-code and
  baseline contract; `--write-baseline` initialises missing baselines only.
- **New config key** `commands.typecheck`: a per-language map of checker commands with schema defaults; `null`
  turns a language off.
- **Principle 4** of `system.arc42.md` gains one exception: a configured command (`commands.*`).
- This repo's model gains `typecheck` in both roots and `conventions` in the `typescript` root.

## Capabilities

### New Capabilities
- `conventions`: the conventions gate and the comment counter for every language — routing by extension, the TS
  rules and line sets, the cross-twin facts document, and the shared report.
- `typecheck`: the `la-typecheck` command — applicable languages, checker commands, the baseline contract and its
  TS multiset ratchet.

### Modified Capabilities
- `twin-forwarding`: `la-check-conventions` and `la-count-comments` are no longer Python-only, and the PyPI twin no
  longer ignores non-Python files.

## Impact

- `shared/`: `languages.yaml` (TS `markers`, `files_label`, `comment_prefix`, `suppression`; `local_bin` and
  `baseline_file` for both; `type_checker` removed), `conventions.yaml` (TS descriptions), `cli.yaml`
  (`la-typecheck`, internal facts options, conventions commands neutral), `findings.yaml`,
  `schema/living-architecture.schema.json` (`commands.typecheck`), new `schema/conventions-facts.schema.json`, new
  `vectors/command-split.yaml`. Contract hash changes.
- PyPI twin: `conventions` (routing, facts, labels), `lang` (facts, basedpyright adapter), new `typecheck` node,
  `cli`.
- npm twin: new `conventions` and `typecheck` nodes, `lang` (rules, line sets, tsc adapter and baseline), `cli`.
- Conformance: TS, mixed and typecheck cases; deliberate re-blesses (unknown-extension paths, empty-diff label,
  `la-config show`).
- `architecture/` (approval-gated edits), `AGENTS.md`, `README.md`.
