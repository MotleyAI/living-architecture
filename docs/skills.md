# Skills

The skills come in two plugins: `trmv` (verified renames and moves and the type-check gate) and `la` (the
architecture workflow), which depends on `trmv`. Each plugin's skills come in two roles.

- **Main skills** are the ones you invoke. Each one except `la:init` and `trmv:init` starts with its plugin's doctor,
  `la-doctor --plugin <skill dir> --require-config` or `trmv-doctor --plugin <skill dir> --require-config`. In a repo
  with no config file, that preflight runs the fast path of its plugin's init skill and then continues.
- **Helper skills** are invoked by main skills, or by you for a single task. They never require the config file,
  so they work in any repo. The four `la:pr` stages are helpers that `la:pr` dispatches to; `la:pr`'s preflight
  covers them.

## Main skills

| Skill | Purpose |
|---|---|
| `la:init` | Onboard a repo: detect its tools, propose `living-architecture.yaml`, set up OpenSpec and offer the type-check baseline and `la:arch-init` |
| `la:pr` | Run a change through plan → failing tests → implementation → review, resumable from the branch name |
| `la:arch-init` | Build the first architecture model from a measured scaffold, then the principles and spec mapping |
| `la:arch-cleanup` | Retire a batch of `#legacy` arrows, or carve a new boundary, with verified moves |
| `trmv:init` | Onboard a repo to trmv: detect its test and type-check commands, write trmv's keys, offer the type-check baseline |
| `trmv:rename-move` | Rename or move Python or TypeScript code, with a type-check gate that proves nothing was missed |

## Helper skills

| Skill | Purpose |
|---|---|
| `la:pr-plan` | Stage 1 of `la:pr`: interview, Codex-reviewed plan, OpenSpec change |
| `la:pr-tests` | Stage 2 of `la:pr`: the failing test suite for the plan |
| `la:pr-implement` | Stage 3 of `la:pr`: implement until green, then open the PR |
| `la:pr-review` | Stage 4 of `la:pr`: the review loop until every gate is clean, then archive |
| `la:process-reviews` | One sweep over CI, Codex, CodeRabbit and Sonar feedback, triaged into a fix plan |
| `la:fetch-coderabbit-threads` | Unresolved CodeRabbit threads and nitpicks on a PR |
| `la:fetch-failed-pr-checks` | Failed CI checks on a PR, with a log excerpt of each |
| `la:reply-to-pr-thread` | Reply to a PR review thread |
| `la:codex-review` | Codex review of the current diff |
| `la:openspec-init` | Initialize or repair OpenSpec in a repo |
| `la:living-architecture` | Reference for the architecture layer: model syntax, arc42 tags, maintenance |
| `la:concise-comments` | Rules for concise comments and docstrings, and a trimming pass |
| `trmv:make-diff-compliant` | Bring the source files a PR touches up to the refactor-compliance conditions |
| `trmv:make-refactor-target-compliant` | Make a planned rename's blast radius verifiable before running it |
