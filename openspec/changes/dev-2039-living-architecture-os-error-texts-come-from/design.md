## Context

See proposal.md (Why). Today about 15 sites across the twins turn an exception into user text themselves
(`str(exc)`, `error.message`), and about 6 decide "absent" with `Path.is_file()` / `existsSync`, which also swallow
permission errors. Python's `OSError` always carries the path it failed on; Node's `EISDIR` from `readFileSync` on a
directory does not (it fails in `read`, not `open`). Both runtimes expose the portable symbolic code (`errno.errorcode`,
`error.code`). PyYAML and the `yaml` package disagree on error positions and wording.

Applicable principles (`architecture/system.arc42.md`): 1 (twins), 2 (texts only from the shared contract), 3
(language-specific code only in `lang` and `refactor`: the renderer is language-neutral and lives in `contract`), 4.
No harness edit and no model change: every touched element already depends on `contract`. No new capability, so no
spec attachment decision.

## Goals / Non-Goals

**Goals:** one renderer and one existence probe per twin, used by every site that reports an OS or YAML error;
byte-identical output in both twins; no crash on an unreadable config or index.

**Non-Goals:**
- Not-a-directory and ELOOP through every command: the issue's matrix is `la-arch-check` and `la-arch-diagrams`;
  other commands share the renderer and are pinned only where listed in tasks.md.
- YAML error line/column (the parsers disagree on positions) and per-reason YAML templates.
- Strict absence for arc42 docs and layout discovery: their `is_file`/`existsSync` predicates already agree across the
  twins (false on any OS error) and never crash; an untraversable `architecture/` fails at the index first.
- The `review` shims' wording (one shared bash script, identical in both twins).
- Schema-validation wording in config and index errors (not OS or YAML text).
- The `dr-refactor` checks-phase refusal of an invalid or unreadable config: that is PR #49 (DEV-2302); this change
  only makes an unreadable config behave as an invalid one.

## Decisions

1. **Templates, not passthrough.** Reverses the 2026-10-03 decision. Weighed: keep passthrough and fix only the
   crashes. Templates win on the twin rule, principle 2 and the issue's later comments. (user)
2. **Within this scope the agent decides, erring on smaller and simpler** ("use your judgement ... erring on the side of
   smaller simpler solutions"). (user)
3. **Templates** (`shared/findings.yaml`, new section):
   ```yaml
     # ---- OS and YAML errors
     os.error: '{path}: {reason}'
     os.not-found: no such file or directory
     os.permission-denied: permission denied
     os.is-a-directory: is a directory
     os.not-a-directory: not a directory
     os.other: 'OS error {code}'
     yaml.invalid: '{path}: invalid YAML'
     yaml.invalid-because: '{path}: invalid YAML: {error}'
   ```
   Keyed by symbolic code, operation-neutral, reason separate from path so `[unreadable]` can print the reason alone.
   `os.other` carries the symbolic code (`unknown` when none): runtime detail was rejected (diverges), fixed text was
   rejected (loses information). (default)
4. **YAML:** every YAML error but a duplicate key, and any non-UTF-8 YAML file, renders `yaml.invalid`; the config
   loaders' duplicate key renders `yaml.invalid-because` with the `yaml.duplicate-key` text. Per-reason profile
   templates rejected as larger; line/column rejected as not portable. The archcheck index loader keeps its
   duplicate-key text (`architecture/index.yaml: <yaml.duplicate-key>`); the c4 index readers keep
   `c4.index-invalid-yaml` / `c4.index-duplicate-key`. (default)
5. **Path selection and rendering:** the path the site passes wins; else Python `filename` / Node `.path` when it is a
   string; `filename2` / `.dest` are never printed; no path at all prints the reason alone. Root and path are made
   absolute lexically against the process cwd (`os.path.abspath` / `path.resolve`, never realpath); a path equal to or
   under the root renders root-relative with `/` separators, else absolute. Pinned by a shared vector file
   `shared/vectors/os-errors.yaml` (code, path, root, explicit path → text) run by both twins' unit tests. (default,
   codex)
6. **Absence:** one `contract` probe per twin: regular file → true; `ENOENT` → false; a non-regular file → false; any
   other stat error propagates. Only `ENOENT` is absent, as the issue's comment asks, which makes not-a-directory
   reachable through `la-arch-diagrams` (`architecture` a regular file). Used for the config files, the c4 index
   readers, the TypeScript refactor workspace's index read and `la-doctor`'s config/index checks. Doctor keeps its own
   `ENOENT`/`ENOTDIR` rule for the plugin-manifest walk up the directory tree. (default, codex)
7. **Node `readFile`:** a `contract` helper with typed overloads, `readFile(path: string): Buffer` and
   `readFile(path: string, encoding: 'utf8'): string`, that sets `error.path` when the error lacks one and rethrows.
   Every read of a target-repo path uses it; stdin (`fd 0`), the contract snapshot load and the `URL`-based package
   version read stay on `readFileSync` with a line-level eslint-disable saying why. `eslint.config.mjs` restricts
   importing `readFileSync` from `node:fs` / `fs`. Without it, any catch-all site prints `EISDIR` without a path in
   Node and with one in Python. (default, codex)
8. **Sites:** config load and format check (both twins), c4 index readers, archcheck index loader, the catch-alls of
   `la-arch-check` (checks and facts), `la-arch-scaffold`, `la-arch-diagrams`, `la-arch-migrate`, `la-affected-tests`,
   conventions `[unreadable]` (both twins), Node `refactor/workspace.ts` index read, Python-only checker and language
   server launch failures (the command is the path), `la-doctor`. An audit maps every other observable OS catch to the
   renderer or to an existing non-OS template (tasks.md). (default, codex)
9. **Non-UTF-8 config is invalid YAML**, as the index already is, rather than a template of its own. (default)
10. **Format check stays permissive.** The format check passes on an unreadable or invalid config (repo-config
    "Every command checks the declared format"); the error surfaces from the command's own config load. (codex)
11. **`dr-refactor` independent of PR #49.** On `main`, `dr-refactor` silently proceeds on an invalid config and crashes
    on an unreadable one. This change makes the unreadable case behave as the invalid one; PR #49's checks-phase
    refusal then covers both, and whichever PR merges second updates the case's golden. (default)
12. **Doctor's stat crash fixed here**, not deferred: same class, small. (default)
13. **Codex findings rejected:** strict absence for arc42 docs and layout discovery (see Non-Goals); chmod cases
    flaky as root (the case format already supports `chmod`, five cases use it, CI runs unprivileged); ELOOP under
    `la-arch-diagrams` (not in the issue's matrix). (rejected (codex))

## Risks / Trade-offs

- [The `readFile` sweep touches ~60 call sites] → mechanical; the eslint restriction keeps new sites on it.
- [Users lose YAML parser detail] → accepted for byte identity; a duplicate key keeps its lines.
- [chmod cases run as root would read the file] → CI and the conformance runner run unprivileged, as for the existing
  chmod cases.
- [PR #49 merging first or second changes `refactor-config-permission-denied`'s golden] → tasks.md notes it.
