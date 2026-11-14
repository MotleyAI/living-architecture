## Why

DEV-1607's method renames in SLayer (about 30 storage, engine and client methods, on la 0.7.0 and 0.8.0) needed
hand work after each `dr-refactor` apply: untyped receivers, duck-typed stand-ins and string-named members were
skipped silently, back-compat sites had to be restored, and doc mentions went stale. The rename's reference set is
"what the checker resolves" and everything outside it is silent, so every session rediscovered the gaps. A member
rename must instead be complete or say loudly what it could not do.

## What Changes

- A member rename refuses while a receiver of the old name is untyped (`Unknown`/`Any`, TS `any`), naming each
  site; `--allow-blindspots` overrides. The scan is the one behind `dr-compliance --attr`.
- A member rename refuses while a class outside the renamed hierarchy (TS: class, interface or type literal)
  declares the old name; `--with PATH:LINE` renames it too in the same diff, `--without PATH:LINE` leaves it.
- A rename rewrites members named by string on a typed object (`getattr`/`setattr`/`hasattr`/`delattr`,
  `monkeypatch.setattr`/`delattr`, `patch.object`, `mocker.patch.object`; TS `vi.spyOn`/`jest.spyOn`, `Reflect.*`,
  `Object.defineProperty`/`getOwnPropertyDescriptor`), and the segments of Python `patch` / `mocker.patch` /
  `monkeypatch` dotted targets that resolve statically to a renamed declaration. An untyped object or callee, or an
  unresolved project target, joins the refusal.
- `--keep PATH[:LINE]` leaves every edit on a line, in a file or under a directory untouched.
- `--docs` rewrites qualified mentions in comments, docstrings, strings and prose files (`.md`, `.rst`, `.txt`),
  and code-marked bare mentions in the declaring files; every other mention is listed as a `leftover`.
- `attr-blindspot` becomes a selectable `dr-compliance` check id, parameterized by `--attr`. **BREAKING**:
  `--attr` with a `--select` that omits `attr-blindspot` is now a usage error (exit 2).
- Both twins implement every item; skills `la:deterministic-refactor`, `la:make-refactor-target-compliant` and
  both language docs describe the new options, the order of steps and the exact hand-checked leftovers.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `refactor`: member-rename refusals (blind spots, stand-ins), string-named member rewrites, `--keep`, `--docs`,
  selectable `attr-blindspot`; the TypeScript rename, compliance check-set and `--attr` requirements change.

## Impact

- `shared/`: `cli.yaml` (new `rename` options, `dr-refactor` prose extensions, `dr-compliance` help),
  `findings.yaml` (new `refactor.*` and `compliance.*` templates), `languages.yaml` (`attr-blindspot` in both
  `compliance_checks`, per-language `string_member_calls`); vendored snapshots via `scripts/sync-shared`.
- Python twin: `living_architecture.refactor` (rename union, compliance scan, new stand-in / string-member / docs /
  keep logic, and DEV-2289's static resolver moved out of `explicit_any.py` into a module shared with the dotted
  patch targets), CLI wiring; npm twin: `src/refactor` likewise.
- Builds on DEV-2289 (Python `explicit-any`, merged into this branch): Python's check list becomes `untyped-def`,
  `unannotated-attr`, `explicit-any`, `mock`, `rope-walk`, `attr-blindspot`; this change archives after DEV-2289's.
- `conformance/cases/` paired cases and `conformance/INVENTORY.md`.
- `plugin/skills/deterministic-refactor`, `plugin/skills/make-refactor-target-compliant`, `plugin/languages/*.md`,
  `docs/deterministic-refactoring.md`, `docs/commands.md`.
- Post-merge: release 0.9.0 and pin it in SLayer.
