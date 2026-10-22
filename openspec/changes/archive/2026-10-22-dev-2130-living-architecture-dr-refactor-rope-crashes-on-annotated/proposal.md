## Why

`dr-refactor rename` crashes before printing a diff on valid Python. For example, it crashes on every
`Annotated[..., Field(description=...)] = default` parameter (the FastMCP/Pydantic style) and on an f-string
implicitly concatenated with a later literal. It then dumps a raw rope traceback whose line is not the
offending construct. The cause is structural. rope's `_PatchingASTWalker` hand-lists each node's tokens and
sub-nodes, and finds every next token by forward text search. Source text a visitor omits becomes a gap, and a
`(`, `=` or quote inside that gap is matched as a later token. The walker then crashes, or it silently
computes wrong scope regions, and rope uses those regions to decide which scope a name belongs to. Patching
one gap at a time, as 0.3.x did for keyword-only arguments, leaves the class open: a sweep of SLayer and the
stdlib found six more gaps. This change blocks a rename in SLayer.

## What Changes

- **Walker-coverage invariant.** It is defined once in the Python `refactor` node and holds after rope walks a
  module:
  - every AST node gets a region, except context/operator nodes, `with` items and f-/t-string internals;
  - every string literal's region covers exactly its source.
  
  A test sweep runs it over a checked-in grammar corpus, the running interpreter's stdlib and this repo's
  Python sources.
- **Walker fixes** for every gap the invariant finds, each with repro tests and a canary showing that
  unpatched rope still fails:
  - the full signature grammar: parameter, `*args` and `**kwargs` annotations, and return annotations
    (`def` and `async def`; `lambda` shares the argument walker);
  - an f-string's region ends after every implicitly concatenated piece;
  - class keywords (`metaclass=`, class kwargs);
  - the `else` of `try/except/else/finally`;
  - `rb`/`Rb`/`bR`-style string prefixes;
  - Python 3.14 t-strings.
- **Runtime guard in `dr-refactor`.** A walker failure or an invariant violation while rope computes the
  changes stops the refactor with a findings-registry message on stderr, exit 1 and nothing written. The
  message names the file and the line of the construct, and says it is a rope bug, not a source error. A
  silent gap is refused like a crash. Other exceptions propagate unchanged.
- **Preflight.** A new Python `dr-compliance` check, `rope-walk`, runs by default and reports every file the
  walker cannot handle, with the same line. **BREAKING** (output contract only): the default Python check set
  grows from three to four.
- **Dry-runs write nothing.** The Python `dr-refactor` no longer creates `.ropeproject/` in the target
  project.
- **Shared contract.**
  - Two new finding templates: `compliance.rope-walk` and `refactor.rope-walk`.
  - `rope-walk` added to Python's `compliance_checks`.
  - `dr-compliance` help lists `rope-walk`.
  - The npm twin needs only the synced snapshot.
- **Docs.** The `docs/deterministic-refactoring.md` checks table and the `plugin/languages/python.md`
  compliance-fix line.
- **CI.** Python 3.14 joins the test matrix.
- **Release.** The versions move to 0.3.3. One consolidated python-rope/rope issue is filed, after the
  user's go-ahead.

## Capabilities

### New Capabilities

### Modified Capabilities
- `refactor`:
  - New requirement: Python refactors are computed over a fully walked source, and a walker gap is
    refused with a located finding.
  - New requirement: a Python dry-run writes nothing.
  - New requirement: the Python `rope-walk` compliance check.
  - Modified requirement "Compliance check sets are per language": Python's default set and its output gain
    `rope-walk`.

## Impact

- **Python twin.**
  - `refactor/rope_patches.py`: patches, the invariant, line localization and the guard.
  - `refactor/rope_refactor.py`: the `Project` is opened without a rope folder; guard errors are translated.
  - `refactor/compliance.py`: the `rope-walk` check.
  - Tests: `test_rope_patches.py`, `test_compliance.py`, the refactor tests and `test_contract.py`
    (`NEW_TEMPLATES`, `UNPRODUCED_BY_DESIGN`).
- **Shared.** `findings.yaml`, `languages.yaml` and `cli.yaml`, with every snapshot synced.
- **Conformance.**
  - The `compliance-help` golden is re-blessed.
  - Every refactor case gains `.ropeproject` `<MISSING>` file expectations.
  - New `compliance-rope-walk-clean` and a neutral `--select rope-walk` case on a TS file.
  - `INVENTORY.md`.
- **CI.** `.github/workflows/ci.yml` (3.14).
- **Versions.** `python/pyproject.toml`, `python/uv.lock`, `node/package.json`, `node/package-lock.json`,
  `plugin/.claude-plugin/plugin.json`, and the README/docs version mentions.
- **No arc42 or model change.**
  - P2: the raw traceback is replaced by registry texts.
  - P3: everything stays in `refactor`.
  - P4: rope only parses target code.
  - No new import edge.
