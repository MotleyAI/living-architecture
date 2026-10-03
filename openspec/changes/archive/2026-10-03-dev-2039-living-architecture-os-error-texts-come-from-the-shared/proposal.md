## Why

The npm twin hard-codes CPython's `OSError` wording (`[Errno 2] No such file or directory: '…'`, Linux errno
numbers included) so its output matches goldens that pin Python's runtime text. That breaks principle 2
(user-facing texts come only from the shared contract), silently diverges for any other error code, and
couples goldens to Linux errno numbers. OS error wording is runtime detail, like YAML parser wording, which the
corpus already treats as outside the contract.

## What Changes

- The npm twin stops imitating CPython: `osErrorText` is deleted and each twin passes its runtime's own OS
  error message through the existing contract prefixes (`arch_check: {error}`, `la-arch-diagrams: {error}`).
- Goldens pinning OS error wording (`arch-check-index-missing`, `arch-diagrams-doc-missing`,
  `conventions-unreadable-directory`) assert the exit code, the contract prefix and the offending path instead
  of the full text; no errno numbers remain in goldens.
- A new neutral case pins a non-not-found OS error (a mapped arc42 doc that is a directory) in both twins.
- The conformance contract states that runtime-supplied error detail is excluded from byte comparison and
  that a twin never imitates another runtime's wording.

## Capabilities

### New Capabilities

### Modified Capabilities
- `shared-contract`: "Observable outputs reproduce the conformance goldens" excludes runtime-supplied error
  detail (OS errors, YAML library messages) from byte comparison.

## Impact

- `node/src/c4/diagrams.ts`, `node/src/c4/index.ts`, `node/src/archcheck/index.ts`.
- `conformance/cases/{arch-check-index-missing,arch-diagrams-doc-missing,conventions-unreadable-directory}`,
  new `conformance/cases/arch-diagrams-doc-is-directory`, `conformance/INVENTORY.md`.
- No `shared/` change: no `sync-shared`, no contract-hash change. Python twin code unchanged.
