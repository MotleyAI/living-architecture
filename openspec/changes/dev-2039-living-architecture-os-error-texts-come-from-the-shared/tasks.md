## 1. Conformance (pr-tests)

- [x] 1.1 `arch-check-index-missing`: keep exit 2; `stderr: {contains: ['arch_check: ', '<ROOT>/repo/architecture/index.yaml']}`; delete its `stderr` golden; note "OS error wording is not part of the contract"
- [x] 1.2 `arch-diagrams-doc-missing`: keep exit 1; `stderr: {contains: ['la-arch-diagrams: ', '<ROOT>/repo/architecture/gone.arc42.md']}`; delete its `stderr` golden; same note
- [x] 1.3 `conventions-unreadable-directory`: keep exit 1; `stdout: {contains: ['src/pkg.py:1: [unreadable] ', 'gate: RED']}`; delete its `stdout` golden; same note (stderr golden stays byte-exact)
- [x] 1.4 New neutral case `arch-diagrams-doc-is-directory` (fixture `arch-diagrams`, index maps `architecture/gone.arc42.md` → `[system]`, `repo/architecture/gone.arc42.md/.keep` makes it a directory): exit 1, `stderr: {contains: ['la-arch-diagrams: ']}` (Node's EISDIR message has no path); list it in `conformance/INVENTORY.md` next to `arch-diagrams-doc-missing`
- [x] 1.5 npm unit test: a missing-file `la-arch-diagrams` / `la-arch-check` setup error never contains `[Errno` (fails until 2.1)

## 2. npm twin (pr-implement)

- [ ] 2.1 Delete `osErrorText` from `node/src/c4/diagrams.ts` and its export in `node/src/c4/index.ts`; `run()` prints `(error as Error).message`
- [ ] 2.2 `node/src/archcheck/index.ts` `setupErrorText`: return `error.message` for errors with an `E…` code; drop the `osErrorText` import
- [ ] 2.3 Python twin: no code change (already `str(OSError)`)

## 3. Gate

- [ ] 3.1 `python/`: `uv run pytest -q`, `ruff check`, `basedpyright`
- [ ] 3.2 `node/`: `npm run lint && npm run typecheck`, `npm test`, `npm run build && npm run conformance`
- [ ] 3.3 `scripts/conformance-cross`, `scripts/sync-shared --check`, `la-arch-check`
