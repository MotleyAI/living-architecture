## 1. Contract

- [x] 1.1 `--plugin` in `shared/cli.yaml`; `doctor.plugin-not-found` and `doctor.plugin-invalid` in `shared/findings.yaml`; `scripts/sync-shared`

## 2. Twins

- [x] 2.1 `la-doctor --plugin` in `python/src/living_architecture/doctor/` and `node/src/doctor/`

## 3. Conformance

- [x] 3.1 Placeholders substituted in `write` step texts (runner and `conformance/README.md`)
- [x] 3.2 `doctor-plugin-*` cases and `doctor-usage-plugin-without-value`, listed in `conformance/INVENTORY.md`

## 4. Skills and docs

- [x] 4.1 Every skill's preflight becomes `la-doctor --plugin <this skill's base directory>`; `test_skills.py` requires it and forbids `--expect` pins
- [x] 4.2 `README.md` (synced) and `AGENTS.md`

## 5. Verify

- [x] 5.1 Both twins' suites, lint and typecheck; `scripts/conformance-cross`; `la-arch-check`; plugin validate
