# Quickstart: the architecture check in five minutes

A toy Python shop with three packages and a model of how they may depend on each other. One function takes a
shortcut the model does not allow, and `la-arch-check` catches it.

```
src/shop/
  api/     takes orders
  core/    the order rules
  store/   persists orders
architecture/
  model.c4          the LikeC4 model: nodes mapped to packages, and the allowed arrows
  views.c4          the views drawn from the model
  system.arc42.md   the principles, with the model's diagram embedded
  index.yaml        where the Python root is, and the legacy-arrow baseline
```

The model allows `api -> core` and `core -> store`, and nothing else:

```
api -> core
core -> store
```

## Run it

Install the commands as in the [main README](../../README.md#install), or run them through `uvx` (prefix each
command below with `uvx --from living-architecture`). Then, from a clone of this repo:

```console
$ cd examples/quickstart
$ la-arch-check --root .
model-truth: measured runtime edge python.api -> python.store is missing from the model (import shop.api -> shop.store)
arch_check: 1 finding(s)
```

`post_order_fast` in `src/shop/api/__init__.py` calls `store` directly, skipping the order rules in `core`. No
arrow licenses that import, so the check fails (exit 1). An agent that wrote this would see the same finding in
its review loop or in CI.

## Fix it: remove the shortcut

Delete `post_order_fast` and its `from shop.store import save` import:

```console
$ la-arch-check --root .
arch_check: OK
```

## Or: grandfather it as legacy

Sometimes the code is already like that and the fix has to wait. Add the arrow to `architecture/model.c4`,
marked `#legacy`:

```
api -> core
core -> store
api -> store #legacy
```

The check now fails differently:

```console
$ la-arch-check --root .
baseline-ratchet: model has 1 legacy arrow(s), baseline is 0
diagrams-fresh: architecture/system.arc42.md diagram python is stale; run la-arch-diagrams
arch_check: 2 finding(s)
```

Every legacy arrow has to be counted in `architecture/index.yaml`. Raise the baseline to
`legacy_arrows: {baseline: 1}`, which is an edit a reviewer sees, then refresh the diagram:

```console
$ la-arch-diagrams --root .
architecture/system.arc42.md
$ la-arch-check --root .
arch_check: OK
```

The diagram in `system.arc42.md` now draws the legacy arrow dashed.

## The arrow has to go when the import does

Now remove the shortcut after all. The model still declares `api -> store`, and a declared arrow with no
import behind it fails too:

```console
$ la-arch-check --root .
model-truth: modeled relation python.api -> python.store has no measured runtime edge
arch_check: 1 finding(s)
```

Delete the arrow, lower the baseline back to 0 and run `la-arch-diagrams --root .` again, and the check
passes. The model can't go stale in either
direction: every import needs an arrow, and every arrow needs an import.

## Next

- In your own repo, `la-arch-scaffold` writes a first model from the imports it measures, and
  `/la:arch-init` builds it out with you, principles included.
- [Living architecture, explained](../../docs/living-architecture-explained.md) covers the rest of the plugin.
