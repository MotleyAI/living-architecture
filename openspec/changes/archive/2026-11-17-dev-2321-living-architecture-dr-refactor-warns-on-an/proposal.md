## Why

On a 2,272-entry SLayer map, `dr-refactor --apply rename-map … --docs` ran 28 minutes, then exited 2 with nothing
written. The only reasons it gave were two lines, `--keep FILE matches nothing this rename touches`, that read like
notes. An unneeded whole-file keep leaves the outcome exactly as asked, so it should not refuse. An unmatched line
keep should still refuse, but say so plainly and as soon as it can be known, not after the `conflicts` phase.

## What Changes

- A `--keep PATH` naming an existing file or directory that matches no edit and no blind spot prints
  `refactor.keep-unneeded` (a `WARNING:` line on stderr) and the run goes on, writing under `--apply`. Whole-path
  keeps leave the up-front textual check (only `refactor.site-missing` applies to them there).
- A `--keep PATH:LINE` that matches nothing is still refused (exit 2). At the end of the computation it names the
  nearest edited line of its file (`refactor.keep-unmatched-near`), or uses `refactor.keep-unmatched` when the file
  holds no edit.
- The up-front keep check gets tighter. Without `--docs`, an old-name spelling inside a comment (other than a Python
  type comment) no longer counts, so a comment-only line keep is refused in `checks`.
- A new *site resolution* step, after every group's rules, the global import planning and the final keep filtering,
  and before `conflicts`. It decides every keep and every `--with` / `--without` site exactly. A refusing site
  finding there stops the run before `conflicts`, with or without `--fail-fast`.
- A Python module rename refuses every `--with` / `--without` in `checks`, since a module has no stand-ins. Its keeps
  are resolved right after rope's change set, before `conflicts`.
- `refactor.keep-unmatched` and `refactor.not-stand-in` end with ", so nothing was refactored".
- **BREAKING** (output): the goldens of the keep and `not-stand-in` cases change. A whole-path keep that matched
  nothing now exits 0 with a warning instead of 2.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `refactor`: the `--keep` requirement (warning vs refusal, nearest edited line), the cheap `checks` (whole-path keeps,
  comments without `--docs`, module-rename stand-in sites), the stand-in classification requirement (`not-stand-in`
  decided at site resolution), the one-report requirement (stop at site resolution) and the phases requirement (no
  `conflicts` after a refusing site finding).

## Impact

- Code: `python/src/living_architecture/refactor/` (`rename_map.py`, `sites.py`, `rope_refactor.py`) and
  `node/src/refactor/` (`rename.ts`, `sites.ts`).
- Contract: `shared/findings.yaml` (two templates changed, two added), synced to both twins by `scripts/sync-shared`.
- Conformance: new paired and adapter cases, realigned goldens of the existing keep and `not-stand-in` cases,
  `conformance/INVENTORY.md`.
- Docs: `docs/deterministic-refactoring.md`.
- Out of scope: retarget's planned imports editing kept lines (DEV-2322).
