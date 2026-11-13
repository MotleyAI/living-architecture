## Why

The Python `dr-refactor rename` runs rope, which knows less about references than the type-check gate does. It
skips forward-reference strings, keyword arguments of Pydantic and dataclass fields, calls through annotated
receivers, `super()` calls in overrides, and dict-literal keys that feed a model. It also fails outright on any
`async def`. Python `dr-compliance --attr` flags only unannotated parameters, so `Unknown` and `Any` receivers stay
invisible to the rename and to the gate. SLayer's vocabulary rename (DEV-1607) hits all of these at scale and is
blocked on them.

## What Changes

- A Python symbol rename adds every reference basedpyright resolves for each renamed declaration of the hierarchy
  to rope's edits. That covers forward-reference strings, field keyword arguments, annotated and inferred receivers,
  and `super()` calls.
- basedpyright `1.40.2` becomes a dependency of the PyPI twin (it was the `verify` extra, which is removed). The
  language server runs from la's own environment, against the project's configuration and interpreter, with la's
  pyright#11919 patch. Nothing it starts writes into the project or runs target-repo code.
- A field rename of a Pydantic model or a `TypedDict` (a keyed class) also rewrites:
  - `cls(old=...)` in the owner's classmethods, and `X.model_construct(old=...)`;
  - the key `"old"` in dict literals whose static target is the owner or a subclass: `model_validate`,
    `Cls(**...)`, `model_construct(**...)`, `model_copy(update=...)`, `model_dump` / `model_dump_json`
    `include` / `exclude`, `TypedDict`-annotated parameters, variables and returns, nested literals typed through
    a field, and a dict variable bound once whose every use is such a sink.
- Every rewrite is proven from types and fails closed: an `Unknown`, `Any`, ambiguous or unresolved target, or an
  aliased field, is left unchanged.
- `async def` methods and functions rename with any locator (a rope patch).
- rope's refusals print the `refactor.cannot-rename` finding instead of a traceback.
- A field rename whose owner chain has a base basedpyright cannot resolve, and a language server that fails, are
  refused with new findings, writing nothing.
- Python `dr-compliance --attr NAME` reports every `x.NAME` whose receiver basedpyright types as `Unknown`, `Any`,
  or a union containing either. Both twins share one `compliance.attr-blindspot` text; the TypeScript output is
  unchanged.
- `plugin/languages/python.md` lists exactly what a rename leaves unrenamed.
- **BREAKING** for Python `dr-compliance --attr` output: the finding text changes, and `Unknown`/`Any` receivers
  beyond unannotated parameters are reported.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `refactor`: Python renames gain the basedpyright reference union, keyed-class keyword arguments and dict keys,
  `async def` support, and refusal findings. Python `--attr` reports typed `Unknown`/`Any` receivers. The permitted
  edit regions cover names inside forward-reference strings and typed dict keys. The TypeScript rename pins its
  contextually typed object-literal keys.

## Impact

- Code: `python/src/living_architecture/refactor/` (reference union, keyed-class rewrites, `async def` patch,
  refusals, `--attr`), `python/src/living_architecture/lang/` (language-server session, patch preload extended to
  the server bundle), `node/src/refactor/` (the shared `--attr` template id only).
- Architecture: `architecture/model.c4` gains `refactor -> lang` in the python root; `system.arc42.md`'s embedded
  diagram is regenerated.
- Contract: `shared/findings.yaml` (`refactor.pyright-failed`, `refactor.unresolved-base`,
  `compliance.pyright-failed`, the changed `compliance.attr-blindspot`, `compliance.ts-attr-blindspot` removed);
  vendored snapshots via `scripts/sync-shared`.
- Dependencies: `basedpyright==1.40.2` in `python/pyproject.toml` `dependencies`; the `verify` extra removed;
  `uv.lock`.
- Tests: Python unit tests, new conformance cases with `conformance/INVENTORY.md` rows, the `--attr` goldens.
- Docs: `plugin/languages/python.md`, `docs/deterministic-refactoring.md`, `docs/commands.md`.
- Upstream: an issue and a PR on python-rope/rope for the `async def` header check.
- Downstream: DEV-1607 pins the release carrying this (not part of this change).
