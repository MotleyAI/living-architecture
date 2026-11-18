## Why

In four cases a Python `dr-refactor rename` ends clean but links the wrong set of sites to the renamed declaration, with
nothing refused or listed (DEV-2342, items 13, 19, 20 and 21 of DEV-2340). Three miss sites: the call keywords of a
decorated function, keywords that reach a field through a `**kwargs` helper, and an attribute read on a receiver the
checker types `Never`. One renames too many: a constructor parameter rename spreads to sibling classes' constructors.
On SLayer these left over 5,000 call sites to fix by hand and about 100 wrongly renamed lines.

## What Changes

- A parameter rename rewrites the call keywords of a decorated function when the checker's signature at the call follows
  the declaration (`@contextmanager`, `@asynccontextmanager`, a `ParamSpec`-typed decorator), proven on the renamed text
  held in memory.
- A rename of a field of a keyed class, or of a parameter, follows `**kwargs` carriers into the class, function or
  constructor: the carrier's call keywords, dict literals unpacked into it, and the `kw["…"]`, `kw.get/pop/setdefault("…")`
  and `"…" in kw` strings.
- **BREAKING**: a keyword the rename cannot link is a blind spot (`refactor.unlinked-keyword`): a callee whose signature
  the checker types without the parameter, a carrier whose flow is mixed or unresolved, or a callee typed `Unknown`,
  `Any` or `Never`. Parameter and field renames refuse on them without `--allow-blindspots`; `--unsure include` renames
  them.
- **BREAKING**: a keyword forwarded through `def wrap(**kw): return f(**kw)` and a constant key of `f(**{"old": …})`
  are renamed with `f`'s parameter; they were left unchanged.
- A receiver the checker types `Never` is a blind spot, in `dr-refactor` and `dr-compliance --attr`; `{receiver}` keeps
  the parentheses written around it.
- **BREAKING**: a parameter rename on `__init__` or `__new__` renames that constructor only (and its overload group),
  never another class's.
- Shared texts: the new `refactor.unlinked-keyword`; `refactor.blindspots` takes `{names}`; `refactor.unsure-warning` and
  the `--allow-blindspots` help mention keywords; the `deterministic-refactor` skill and the refactoring doc describe
  the new blind spot.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `refactor`: keyword linking through the checker's signature and through `**kwargs` carriers, unlinked keywords as
  blind spots, `Never` receivers, and constructor parameter renames without a hierarchy.

## Impact

- `python/src/living_architecture/refactor/` (rename rules, keyed sinks, blind-spot scan, hierarchy) and
  `python/src/living_architecture/lang/` (the checker export and its hook).
- `shared/findings.yaml`, `shared/cli.yaml` and each twin's vendored snapshot; the contract hash changes, so the next
  release raises the minor version.
- `node/`: the TypeScript twin loads the changed texts; its constructor parameter rename is pinned by a paired case.
- `conformance/`: new cases, `INVENTORY.md`, and the re-blessed golden of `refactor-rename-param-unresolved-keywords`.
- `plugin/skills/deterministic-refactor/SKILL.md`, `docs/deterministic-refactoring.md`.
- No architecture model or arc42 change: no new import edge, and the spec stays owned by `python.refactor`.
