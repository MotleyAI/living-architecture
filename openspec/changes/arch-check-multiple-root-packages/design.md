# Design: multiple root packages

## Decision

Add `root_packages: [<path>, ...]` to each language section of `architecture/index.yaml`. Keep scalar
`root_package` as the legacy single-root form. A section MUST set exactly one of these keys. `root_packages` MUST
be a non-empty list of unique canonical relative paths. Every path resolves below the language's `source_root`,
must be a directory, and roots must be disjoint (neither root may contain another). Existing `source_root`
semantics stay unchanged.

Each entry uses the current `root_package` notation: slash-separated path from `source_root`, and for Python that
path maps to the same dotted module prefix. Architecture metadata continues to name units relative to
`source_root` (`src/api` for TypeScript, `pkg.api` for Python). This keeps unit IDs globally unique and lets
existing model metadata govern units across roots.

## Runtime behavior

- Resolve and validate every configured root before scanning.
- Enumerate visible source files and top-level units from the union of roots, deduplicated and sorted by the
  existing module/unit ordering.
- A declared or derived unit continues to resolve against `source_root`; the disjoint-root invariant prevents
  duplicate ownership and makes the existing unit notation unambiguous.
- Attribute resolved and lexical TypeScript import targets only when their real/lexical path is inside at least
  one configured root. Python sources are enumerated under every root; imports outside mapped units remain
  unattributed as today.
- `la-arch-check --top-level` reports the combined top-level units and edges across roots.
- Preserve scalar `root_package` behavior byte-for-byte for existing valid configurations.

## Twin and contract

The shared index schema and finding templates are canonical. Both Python and TypeScript twins resolve the same
configuration, produce the same findings, and are covered by mirrored conformance fixtures. Package versions do
not change in this feature branch; release versioning remains a separate release operation.

## Risks

Nested roots would duplicate source discovery and blur package ownership, so they are rejected. Same-named module
paths under different roots cannot occur because IDs are source-root-relative and roots are disjoint. TypeScript
project selection remains based on the existing `tsconfig` rules; only the source set and internal-root predicate
change.
