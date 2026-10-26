## 1. Tests (pr-tests stage; failing until implemented)

- [x] 1.1 `shared/vectors/yaml.yaml`: header comment documents `error: refused` (raw PyYAML's safe loader constructs
  it, the profile refuses it) next to `error: true`. Add `refused` vectors: `!!binary aGk=`, `!!set {a, b}`,
  `!!omap [{a: 1}]`, `!!pairs [{a: 1}]`, `!!pairs [{a: 1}, {a: 2}]`, verbatim `!<tag:yaml.org,2002:set> {a}`,
  `%TAG !y! tag:yaml.org,2002:` + `!y!omap [{a: 1}]`. Verify each by raw `yaml.safe_load` succeeding.
- [x] 1.2 `error: true` vectors: `!!binary aGk`, `!!binary [1]`, `!!set [a]`, `x: =`, `x: !!merge a`, `x: <<`,
  `x: [<<]`, `x: !!timestamp [1]`, `{[1]: a}`, `{{a: 1}: b}`, `{? [1]}`, block `? [1]\n: a`, an alias of an
  anchored sequence and of an anchored mapping as a key (flow `{*k : a}` and block `*k : a`), anchors `&a.b`,
  `&a/b`, `&é`, `a: &k: s`. Verify each by raw `yaml.safe_load` raising.
- [x] 1.3 Value vectors: `! 12` → 12, `! [1]`, `! {a: 1}`, `x: !!str <<` → `'<<'`, `{!!str <<: {p: 1}}` and
  `{'<<': {p: 1}}` → literal key `<<`, `!!merge y: *a` merges, `%TAG` `!y!str 12` → `'12'`, verbatim
  `!<tag:yaml.org,2002:str> 12` → `'12'`, `{*k: a}` → `{s: a}`, block `*k : a` with a scalar anchor, `&k-1_x`.
  Verify against raw `yaml.safe_load`.
- [x] 1.4 `python/tests/test_vectors.py`: the raw-PyYAML test asserts `safe_load` succeeds for `refused`; the
  one-expectation test accepts `error` in (`true`, `refused`). `python/tests/test_contract.py::test_yaml_profile`
  and `node/test/vectors.test.ts` treat `refused` as a YAML error. Verify the new vectors fail in the twin(s) that
  diverge today and every pre-existing vector still passes.
- [x] 1.5 Neutral conformance case `config-error-refused-tag`: `living-architecture.yaml` with `format: <FORMAT>` and
  `reviewers: !!set {codex}`; `la-config show` exits 1, stdout empty, stderr contains `living-architecture.yaml`
  (wording not contract, as `config-error-impossible-date`). List it in `conformance/INVENTORY.md` with the invalid
  config cases. Verify it fails through the npm twin today.
- [x] 1.6 Codex review of the tests against this change (pr-tests Step 2); resolve findings with the user.

## 2. shared/

- [x] 2.1 `shared/README.md` § YAML profile, replacing the paragraph:
  "YAML 1.1 as PyYAML's safe loader reads it, within a closed tag set: `yes`/`no`/`on`/`off` are booleans,
  sexagesimal and `0`-prefixed octal integers are numbers, merge keys apply, a duplicate mapping key takes the last
  value, and a scalar the safe loader cannot construct is a YAML error. The tag set is `!!str`, `!!int`, `!!float`,
  `!!bool`, `!!null`, `!!timestamp`, `!!seq`, `!!map` and `!!merge`, in any spelling; a non-specific `!` resolves a
  node as if it were untagged, and a scalar as if it were plain whatever its style (`! '12'` is `12`). Any other tag
  (`!!binary`, `!!set`, `!!omap`, `!!pairs`, the `!!value` a plain `=` resolves to, a local or unknown tag) is a
  YAML error, as is a merge key (`<<` or `!!merge`) anywhere but a mapping key, and a
  mapping key that is a sequence or mapping. Anchor and alias names are ASCII letters, digits, `-` and `_`. Pinned
  by `vectors/yaml.yaml`."
- [x] 2.2 Run `scripts/sync-shared`; verify `scripts/sync-shared --check` passes and both snapshots' `CONTRACT_HASH`
  match.
- [x] 2.3 Check the repo `README.md`, `docs/` and `plugin/` for a claim that the profile is "exactly" PyYAML's and
  align it (verify with `rg -n -i "exactly as PyYAML|yaml profile"`).

## 3. Python twin

- [x] 3.1 `contract/yaml_profile.py`: `load_yaml` reads through a `SafeLoader` subclass whose `binary`, `set`, `omap`
  and `pairs` constructors raise the undefined-tag error. Verify the vector tests pass.

## 4. npm twin

- [x] 4.1 `contract/yaml.ts`: one validation pass over the parsed document before `toJS`: resolved tag outside the
  set, plain `=`, merge key outside a key position, collection key (aliases dereferenced, cycle-safe) are YAML
  errors; `!` resolves as untagged on every node kind; `!!str <<` is a plain key. Verify the vector tests pass.
- [x] 4.2 Anchor and alias names lexed as YAML 1.1 (design.md: hook settled here; a parser fork means stop and ask).
  Verify the anchor vectors pass.

## 5. Verify

- [x] 5.1 Python: `uv run pytest -q`, `ruff check src tests`, `basedpyright src tests` green.
- [x] 5.2 npm: `npm run lint && npm run typecheck`, `npm test`, `npm run build && npm run conformance` green.
- [x] 5.3 `scripts/conformance-cross` green; `la-arch-check` green.

## 6. Non-ASCII line breaks (found in review)

- [x] 6.1 `shared/vectors/yaml.yaml`: `error: refused` vectors `x: {a: &k\x85s, b: *k}`, `a: b\x85c: d`,
  `a: "x y"`, block literal `a: |` with `x   y`; `error: true` vector `a: x\x85y`; value vector
  `a: "\N\L\P"` → the three characters. Verify each against raw `yaml.safe_load`.
- [x] 6.2 `shared/README.md` § YAML profile: append "Line breaks are `\n`, `\r` and `\r\n`: a raw NEL (U+0085),
  U+2028 or U+2029 anywhere in the text is a YAML error (the `\N`, `\L` and `\P` escapes in a double-quoted scalar
  are not)." Run `scripts/sync-shared`.
- [x] 6.3 Python `load_yaml` and npm `loadYaml` refuse the three raw characters before parsing. Verify the vector
  tests pass in both twins.
- [ ] 6.4 Re-run 5.1–5.3.
