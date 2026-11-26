## 1. Harness and model (approval first)

- [x] 1.1 Extend the conformance harness with git steps for a linked worktree (run the command inside it), a write
  into the git common directory (stealth files), a `.git/info/exclude` entry, a named remote and a submodule;
  document them in `conformance/README.md`; verify with a harness self-test case per step
- [ ] 1.2 Show the user the exact `architecture/model.c4` edit (node `leaks` with `specs ['stealth-leaks']` in both
  roots' `la`, arrows `la.cli -> la.leaks`, `la.review -> la.leaks`, `la.leaks -> la.config`,
  `la.leaks -> la.contract`, plus any arrow the measured imports of trmv's typecheck, lang and config need) and wait
  for the OK before editing; until it lands, `la-arch-check` reports `spec group stealth-leaks is mapped by no
  element` (expected since this change was planned); verify `la-arch-check` passes after implementation

## 2. Shared contracts

- [ ] 2.1 `shared/trmv/`: stealth path registry, `stealth` derived key, `environment_dirs` and `fingerprint_files`
  per language in `languages.yaml`, `--base` for `trmv-typecheck` in `cli.yaml`, findings for the multi-file
  message, stealth refusals and the merge-base errors; run `scripts/sync-shared` and verify `--check` passes
- [ ] 2.2 `shared/la/`: la stealth path registry, `leaks.allow` in the config schema, the waiver-ledger schema,
  `vectors/stealth-leaks.yaml` (core and waivable tokens), `la-leak-check` in `cli.yaml`, findings for the leak hits,
  the ledger errors, the registry findings and the private-store finding; run `scripts/sync-shared` and verify
  `--check` passes

## 3. Tests (pr-tests stage)

- [x] 3.1 Conformance cases for every scenario of the delta specs (repo-config, doctor, typecheck, conventions,
  affected-tests, refactor, stealth-leaks), listed in each tree's `INVENTORY.md`; every new findings template
  produced by a golden; verify they fail before implementation
- [x] 3.2 Twin unit tests for the resolver (common-dir resolution, subdir, linked worktree, submodule, outside git),
  the base resolver, the merge-base cache key and worktree cleanup, the token matcher and the ledger matcher, in
  both twins

## 4. trmv

- [ ] 4.1 Config resolver: the four-file lookup, the multi-file error, the derived `stealth` key, the stand-in rule,
  `architecture: true` refusal, `trmv-config show` stderr note; verify the repo-config conformance cases pass in
  both twins
- [ ] 4.2 Shared base resolution in `changes` (remote-tracking refs); verify the affected-tests and refactor cases
- [ ] 4.3 `lang`: preparing a checker environment for another revision (link environment directories, repo-relative
  diagnostics); verify its unit tests
- [ ] 4.4 `typecheck`: `--base`, merge-base baseline in a temporary worktree, cache under `<C>/trmv/typecheck/`,
  stealth refusals of `--write-baseline` and `--realign-from`; verify the typecheck cases in both twins
- [ ] 4.5 `trmv-doctor`: stealth config as source, trmv registry findings; verify the doctor cases
- [ ] 4.6 `la-arch-migrate` stamps a stealth file in place; verify its case

## 5. la

- [ ] 5.1 `la.config`: lookup through trmv, local-file refusal in stealth, `leaks.allow` validation,
  `openspec_store`; verify the repo-config cases
- [ ] 5.2 `la-doctor`: stealth config as source, la registry findings, private-store finding, plan store in
  stealth; verify the doctor and repo-config cases
- [ ] 5.3 New node `la.leaks` and `la-leak-check` (both twins); verify the stealth-leaks cases
- [ ] 5.4 Reply scripts scan the body in stealth before any `gh` call; verify the reply cases with a fake `gh`
- [ ] 5.5 `la-check-conventions`: ledger in stealth, inline waivers ignored, RED verdict names the ledger; verify the
  conventions cases

## 6. Skills (exact wording approved by the user before each edit)

- [ ] 6.1 `/la:init` and `/trmv:init`: offer normal or stealth setup when no config exists; stealth writes the stealth
  config (`architecture: false` for la), never edits `.gitignore`, never commits, offers no `--write-baseline`, CI
  recipe or `/la:arch-init`
- [ ] 6.2 `/la:pr`: rehydrate without tracker writes in stealth; detect the durable plan from the private store
  (`--store`) or `<C>/living-architecture/plans/<CHANGE_ID>.md`; stage-end commits go to the store's git repo, never
  la or OpenSpec files into the repo; preflight skips migrated paths outside the worktree
- [ ] 6.3 `/la:pr-plan`, `/la:pr-tests`, `/la:pr-implement`, `/la:pr-review`: the stealth branches for OpenSpec
  (`--store`), the plan file, no tracker comments or state changes, the text rule, `la-leak-check --base <PR base>`
  before every push and at every sweep, `la-leak-check --text -` on the PR title and body before `gh pr create`,
  passing the PR's real base remote
- [ ] 6.4 `/la:process-reviews` and `/la:reply-to-pr-thread`: the text rule; post only through the reply commands
- [ ] 6.5 `/la:openspec-init`: set up and register the private store (`openspec store setup --path ... --init-git`)
  in stealth when the repo tracks no `openspec/`; refuse when the CLI has no `store` command
- [ ] 6.6 `/la:arch-init` and `/la:arch-cleanup`: refuse in stealth

## 7. Docs and gates

- [ ] 7.1 `docs/configuration.md`: a "Stealth mode" section (locations, lookup, what is refused, OpenSpec and plans,
  leak check, typecheck baseline, waiver ledger, base refs)
- [ ] 7.2 Run the enforcement bundle (`la-arch-check`, LikeC4 validation, `trmv-typecheck`) and the local test scope;
  verify all pass
