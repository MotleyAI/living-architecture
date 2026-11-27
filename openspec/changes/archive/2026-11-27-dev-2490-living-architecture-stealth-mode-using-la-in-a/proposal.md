## Why

la and trmv assume the repo has adopted them: they commit `living-architecture.yaml` or `trmv.yaml`, the
`architecture/` model, `openspec/`, baselines and `.gitignore` entries, and the flow's commits, PR text and review
replies speak la's vocabulary. A contributor to a repo they don't own cannot use the tools there without these
traces showing up in its history or on its PRs. Stealth mode lets one person use the tools and the `/la:pr` flow in
such a repo so that nothing committed, pushed or posted shows that they were used.

## What Changes

- A **stealth directory** per repo under the git common directory: `<git-common-dir>/living-architecture/` (la's
  config, plans, waiver ledger, private OpenSpec store) and `<git-common-dir>/trmv/` (trmv's config, the typecheck
  baseline cache). Shared by every worktree; git cannot track it. A config file there switches stealth on; there is
  no flag.
- **Config lookup** (one resolver in trmv, used by la): a root config file first, else the stealth one; more than one
  is an error naming them all. `la-config get stealth` and `trmv-config get stealth` print whether stealth is on.
  Stealth configs refuse `architecture: true`; la's accepts `leaks.allow`; a repo-root
  `living-architecture.local.yaml` is an error in stealth.
- **Doctors** accept the stealth config for `--require-config` and fail while any la or trmv file from a shared
  registry is present in the worktree (tracked, staged or untracked) outside what the repo tracked at HEAD.
- **OpenSpec** stays an independent choice. In stealth, `openspec: true` uses the repo's tracked `openspec/` if it
  has one, else a private OpenSpec store in the stealth directory (`la-config get openspec_store` prints its id);
  `openspec: false` keeps the plan in the stealth directory, which `--require-plan-store` accepts for any tracker.
- **New `la-leak-check`** (node `la.leaks`): scans the branch name, commit messages and added lines and paths since
  the merge-base, or stdin text, for la/trmv tokens from the shared contract. `la-reply-to-pr-thread` and
  `la-reply-invalid-coderabbit` refuse to post a leaking body in stealth.
- **`trmv-typecheck` in stealth** without a tracked baseline compares against the checker's errors at the merge-base
  (new `--base`), computed in a temporary worktree and cached by commit and fingerprint; `--write-baseline` is
  refused, and `--realign-from` too when no baseline is tracked.
- **`la-check-conventions` in stealth** ignores inline `ALLOW(...)` comments and reads waivers from a ledger in the
  stealth directory.
- **Base refs**: every `--base` accepts a remote-tracking ref (`upstream/main`), so forks compare with the real base.
- **Skills**: `/la:init` and `/trmv:init` offer stealth setup; the `/la:pr` stages, `/la:process-reviews`,
  `/la:reply-to-pr-thread` and `/la:openspec-init` follow stealth rules (no la files in the repo, no tracker writes,
  no la vocabulary in posted text, the leak check before each push and post); `/la:arch-init` and `/la:arch-cleanup`
  refuse in stealth.
- Docs: a "Stealth mode" section in `docs/configuration.md`.

## Capabilities

### New Capabilities
- `stealth-leaks`: `la-leak-check` and the reply commands' refusal to post text that shows la or trmv was used.

### Modified Capabilities
- `repo-config`: the stealth config location and switch, stealth-only keys and refusals, the doctors' stealth gates,
  OpenSpec and the plan store in stealth.
- `doctor`: `trmv-doctor` accepts and checks the stealth config.
- `typecheck`: the merge-base baseline in stealth, `--base`, and the stealth refusals of `--write-baseline` and
  `--realign-from`.
- `conventions`: the stealth waiver ledger.
- `affected-tests`: `--base` accepts a remote-tracking ref.
- `refactor`: `trmv-mock-lint --base` accepts a remote-tracking ref.

## Impact

- trmv: `config` (resolver, stealth keys), `changes` (base resolution), `typecheck` (merge-base baseline, cache),
  `lang` (preparing a checker environment for another revision), `doctor`; `shared/trmv/` (schema, findings, CLI,
  language facts, path registry).
- la: `config`, `doctor`, `conventions` (ledger), `review` (reply refusal), new `leaks` node; `shared/la/` (schema,
  findings, CLI, token list).
- Both twins, the conformance harness (worktree, exclude and submodule steps) and both corpora.
- `architecture/model.c4` (node `la.leaks` and its arrows in both roots) and `architecture/index.yaml`.
- Skills in `plugin/la/` and `plugin/trmv/`; `docs/configuration.md`.
