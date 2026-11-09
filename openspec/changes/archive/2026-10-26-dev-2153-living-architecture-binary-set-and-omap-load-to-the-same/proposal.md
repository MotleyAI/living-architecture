## Why

The shared YAML profile promises "YAML 1.1 exactly as PyYAML's safe loader reads it", but the twins only agree
where they were matched by hand. A differential probe of both loaders finds the npm twin diverging on `!!binary`,
`!!set`, `!!omap`, `!!pairs`, a plain `=`, the non-specific `!`, merge keys outside a key position, scalar tags on
collections, collection keys (direct or through an alias), anchor names and the non-ASCII line breaks NEL, U+2028
and U+2029; the Python twin also renders a set in a
run-dependent order. Nobody writes these in a config, but under the twin rule any such input is an observable
difference (`reviewers: !!set {codex}` passes in npm and fails in Python).

## What Changes

- The profile gets a closed tag set: `!!str`, `!!int`, `!!float`, `!!bool`, `!!null`, `!!timestamp`, `!!seq`,
  `!!map` and `!!merge`, in any spelling; a non-specific `!` resolves a node as if it were untagged, and a scalar as if
  it were plain whatever its style (`! '12'` is `12`). Every other tag (`!!binary`,
  `!!set`, `!!omap`, `!!pairs`, the `!!value` a plain `=` resolves to, a local or unknown tag) is a YAML error,
  as is a merge key anywhere but a mapping key and a mapping key that is a sequence or mapping.
- Anchor and alias names are YAML 1.1's: ASCII letters, digits, `-` and `_`.
- A raw NEL, U+2028 or U+2029 in the input is a YAML error: PyYAML reads them as line breaks, the npm twin's library
  as ordinary characters.
- `shared/README.md`'s YAML profile section states both rules and no longer says "exactly".
- `shared/vectors/yaml.yaml` pins every probed input; a new `error: refused` marker records an input PyYAML's safe
  loader constructs but the profile refuses.
- Python twin: `load_yaml` refuses the four non-core collection/binary tags. npm twin: `loadYaml` enforces the tag
  set, the key rule, `!`, the merge-key position and the anchor-name lexing.
- **BREAKING** (in principle only): a YAML input using one of the refused tags, previously accepted by one or both
  twins, is now a YAML error in both.

## Capabilities

### New Capabilities

### Modified Capabilities
- `shared-contract`: "YAML is read with one fixed profile" gains the closed tag set, the scalar-key rule, the
  YAML 1.1 anchor names and the line-break rule.

## Impact

- `shared/`: `README.md` (YAML profile), `vectors/yaml.yaml`; re-vendored into both twins (new contract hash).
- Python twin `python/src/living_architecture/contract/yaml_profile.py`; npm twin `node/src/contract/yaml.ts`.
- Vector tests in both twins (`python/tests/test_vectors.py`, `python/tests/test_contract.py`,
  `node/test/vectors.test.ts`).
- One new neutral conformance case, listed in `conformance/INVENTORY.md`.
- No config key, schema, finding, CLI surface or version change.
