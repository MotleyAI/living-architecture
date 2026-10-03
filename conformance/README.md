# Conformance corpus

Each twin's suite runs every applicable case under `cases/` against its installed commands and compares the
exit code, stdout and stderr byte-for-byte. `INVENTORY.md` maps every output branch to its cases.

## A case

`cases/<id>/case.yaml`:

```yaml
kind: neutral | paired | adapter   # paired: one run per language; adapter: one language
languages: [python]                # the fixture languages; required unless neutral
twin: python | typescript          # only this twin invokes the command (forwarding and facts cases)
other_twin: absent                 # the other twin's bin dir is kept off PATH
command: la-arch-check
args: [--root, .]                  # `<VERSION>`, `<CONTRACT_HASH>`, `<ROOT>` are substituted
cwd: sub/dir                       # relative to the repo; default: the repo root
stdin: text
fixture: arch-ok                   # copies fixtures/<name>/{repo,<overlays>}/ first
remove: [path]                     # deleted after the overlays are applied
symlinks: {link: target}
env: {NAME: value}                 # placeholders substituted
hide: [gh]                         # executables removed from PATH
bins: [{dir: name, position: before | after, files: {exe: text}, nonexec: [exe], link: other-dir}]   # fake executables
git: none | [step, ...]            # default: `git init -b main` with no commits
gh: [{match: [argv tokens], stdout: text-or-json, exit: 0}]   # the fake `gh`; first match wins
normalize: [version, contract_hash, {pattern: regex, replace: text}]
expect:
  exit: 0
  stdout: ignore | json | {contains: [text]}   # omitted: byte golden; json: equal as a JSON value
  stderr: ignore | {contains: [text]}
  files: [path]                    # compared with files/<path> after the run; absent reads `<MISSING>`
golden: manual                     # hand-written goldens; the update mode never writes them
note: why this case exists
```

Git steps, applied in order after `git init`: `write: {path: text}`, `commit: message` (stages everything),
`branch: name`, `checkout: name`, `stage: [path]`, `delete: [path]`, `git_rm: [path]`,
`rename: {from: to}`, `origin: [branch]` (creates a local bare `origin` and pushes).

Overlays are `repo/` and one directory per fixture language (`python/`, `node/` for typescript), copied from
the fixture and then from the case, in `languages` order; a later overlay overwrites an earlier one's file. A
paired case runs once per listed language with only that language's overlay; a neutral case applies every
listed overlay to one repo. Goldens are `stdout`, `stderr` and `files/`; for a paired or adapter run,
`<name>.<language>` overrides the shared golden.

## Which twin runs a case

`LA_CONFORMANCE_TWIN` (`python`, the default, or `typescript`) picks the invoking twin; `LA_NODE_BIN_DIR`
holds the npm twin's commands. A twin's own run takes the cases whose fixture languages are none or only its
own and whose command it implements natively (`native` in `shared/cli.yaml`). `LA_CONFORMANCE_CROSS=1` runs
every case. A case with `twin:` runs only through that twin. `npm run conformance` in `node/` runs the npm
twin's own cases; `scripts/conformance-cross` runs every case through each twin, or through one with
`--twin <python|typescript>`. Runs are parallel (`-n auto`); pass `-n 0` to debug a case serially.

## Environment

Commands run with `LC_ALL=C`, `TZ=UTC`, `COLUMNS=80`, a fixed git identity and date, an empty `HOME`, a
fake `gh`, and no network. PATH holds the fake `gh`, the `before` bins, the invoking twin's bin dir, the other
twin's bin dir, the `after` bins and the host tools minus every manifest command, `npx` and `uvx`. The
temporary root is normalized to `<ROOT>`; the repo is `<ROOT>/repo` and `TMPDIR` is `<ROOT>/tmp`.

## Goldens

A normal run only diffs. `LA_UPDATE_GOLDENS=1` writes goldens from one process (it overrides `-n`), and
refuses when the exit code differs from `expect.exit`. Regenerate only with a stated reason (see AGENTS.md) and review the diff.
