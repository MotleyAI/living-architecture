# Conformance corpus

Each twin's suite runs every applicable case under `cases/` against its installed commands and compares the
exit code, stdout and stderr byte-for-byte. `INVENTORY.md` maps every output branch to its cases.

## A case

`cases/<id>/case.yaml`:

```yaml
kind: neutral | paired | adapter   # neutral: every twin; paired/adapter: the twins in `languages`
languages: [python]                # required unless neutral
command: la-arch-check
args: [--root, .]                  # `<VERSION>` is replaced by the installed version
cwd: sub/dir                       # relative to the repo; default: the repo root
stdin: text
fixture: arch-ok                   # copies fixtures/<name>/{repo,<language>}/ first
remove: [path]                     # deleted after the overlays are applied
symlinks: {link: target}
env: {NAME: value}
hide: [gh]                         # executables removed from PATH
git: none | [step, ...]            # default: `git init -b main` with no commits
gh: [{match: [argv tokens], stdout: text-or-json, exit: 0}]   # the fake `gh`; first match wins
normalize: [version, {pattern: regex, replace: text}]
expect:
  exit: 0
  stdout: ignore | {contains: [text]}   # omitted: compare with the `stdout` golden
  stderr: ignore | {contains: [text]}
  files: [path]                    # compared with files/<path> after the run
golden: manual                     # hand-written goldens; the update mode never writes them
note: why this case exists
```

Git steps, applied in order after `git init`: `write: {path: text}`, `commit: message` (stages everything),
`branch: name`, `checkout: name`, `stage: [path]`, `delete: [path]`, `git_rm: [path]`,
`rename: {from: to}`, `origin: [branch]` (creates a local bare `origin` and pushes).

The case's own `repo/` and `<language>/` overlays are copied over the fixture. Goldens are `stdout`, `stderr`
and `files/`; a `<name>.<language>` golden overrides the shared one for that language.

## Environment

Commands run with `LC_ALL=C`, `TZ=UTC`, `COLUMNS=80`, a fixed git identity and date, an empty `HOME`, a
fake `gh`, and no network. The temporary root is normalized to `<ROOT>`; the repo is `<ROOT>/repo` and
`TMPDIR` is `<ROOT>/tmp`.

## Goldens

A normal run only diffs. `LA_UPDATE_GOLDENS=1` writes goldens, and refuses when the exit code differs from
`expect.exit`. Regenerate only with a stated reason (see AGENTS.md) and review the diff.
