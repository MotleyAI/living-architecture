## 1. Shared contract

- [x] 1.1 Add `yaml.duplicate-key` and `c4.index-duplicate-key` to `shared/findings.yaml` with the approved wording
  (design decision 5); verify both render through each twin's `message()`.
- [x] 1.2 Rewrite the YAML-profile paragraph of `shared/README.md`: duplicate keys are a YAML error, the key-identity
  rules (decision 13), the reported key and lines; drop "a duplicate mapping key takes the last value"; verify the
  text matches the shared-contract delta.
- [x] 1.3 In `shared/vectors/yaml.yaml`: add the `error: duplicate` + `message:` kind to the header; flip
  `duplicate key keeps the last value`, `duplicate nested key`, `duplicate keys at depth` and `duplicate mapping value
  replaced, not merged` to it; add the matrix of decisions 3, 4, 12 and 15 (equal keys, differing keys, repeated
  `<<`, merge override and merge-sequence collision still loading, alias key first and second, anchored map, one-line
  flow mapping, several repeats, nested-before-outer order); verify every case is accepted by PyYAML's `safe_load`.
- [x] 1.4 Run `scripts/sync-shared`; verify `scripts/sync-shared --check` and the drift test pass.

## 2. Vector runners

- [x] 2.1 Teach `python/tests/test_vectors.py` and the Python profile vector test the `duplicate` kind (PyYAML loads
  it; the profile raises the duplicate error with exactly `message`), keeping the one-expectation check; verify the
  new vectors fail before the profile change.
- [x] 2.2 Same in `node/test/vectors.test.ts`; verify the new vectors fail before the profile change.

## 3. YAML profile, both twins

- [x] 3.1 Python `contract/yaml_profile.py`: a `DuplicateKeyError(YAMLError)` carrying the normalized key and both
  lines; key start marks recorded while composing (decision 12); a document-order duplicate check over the composed
  tree with the decision-13 comparator; header docstring updated; verify the yaml vectors pass.
- [x] 3.2 npm `contract/yaml.ts`: the same `DuplicateKeyError`, the same comparator (not `Map` membership), lines
  from the source ranges (alias token for an alias key); header comment updated; verify the yaml vectors pass and
  both twins agree on every vector.
- [x] 3.3 Unit tests in both twins for the comparator's edge classes and the error's key and lines; verify they pass.

## 4. Readers

- [x] 4.1 `la-arch-check` (both twins' `archcheck` index load): prefix `architecture/index.yaml: ` to every YAML
  error; verify `arch-check-index-invalid-yaml` (updated) and `arch-check-index-duplicate-key` pass.
- [x] 4.2 `c4`: one strict index primitive returning text + mapping or a structured failure (decision 11); the
  lenient reader renders a `DuplicateKeyError` with `c4.index-duplicate-key`; verify the diagrams and scaffold
  duplicate cases pass and the existing invalid-YAML goldens are unchanged.
- [x] 4.3 `la-arch-migrate` (both twins): use the strict primitive, refuse an unusable index (decision 10), drop the
  private lenient reader; verify the four migrate index cases and the existing migrate goldens pass.
- [x] 4.4 npm `refactor/workspace.ts`: an existing index that is not UTF-8 or not valid YAML is a `RefactorError`
  (duplicate -> `c4.index-duplicate-key`, else `c4.index-invalid-yaml`); missing index or no `tsconfig` key keeps
  the fallback; verify the four TS index cases pass.
- [x] 4.5 Config loaders: confirm the existing `<path>: invalid YAML: <detail>` carries the duplicate message for
  both files and `la-doctor`; verify the config and doctor duplicate cases pass.

## 5. Conformance corpus

- [x] 5.1 Flip `config-show-duplicate-key` to the error (exit 1, stderr contains the file and the duplicate message).
- [x] 5.2 Add `config-local-duplicate-key`, `doctor-config-duplicate-key`, `arch-check-index-duplicate-key`,
  `arch-diagrams-index-duplicate-key`, `arch-scaffold-index-duplicate-key` (same kind as
  `arch-scaffold-index-invalid`), `arch-migrate-index-duplicate-key`, `arch-migrate-index-invalid-yaml`,
  `arch-migrate-index-not-mapping`, and the TypeScript adapters `refactor-ts-index-duplicate-key`,
  `compliance-ts-index-duplicate-key`, `mock-lint-ts-index-duplicate-key`, `refactor-ts-index-invalid-yaml`.
- [x] 5.3 Align `arch-migrate-index-not-utf8` (exit 2, `la-arch-migrate: index.yaml is not valid YAML`, repo
  unchanged, note updated) and `arch-check-index-invalid-yaml` (contains `arch_check: architecture/index.yaml: `).
- [x] 5.4 List every new case in `conformance/INVENTORY.md`; verify both new templates are produced by a golden.

## 6. Finish

- [x] 6.1 Run the full Python suite, ruff and basedpyright in `python/`; the npm lint, typecheck, tests, build and
  conformance in `node/`; `scripts/conformance-cross`; fix until green.
- [x] 6.2 Run the enforcement bundle (`la-arch-check`, LikeC4 validation, `la-typecheck`); verify green.
