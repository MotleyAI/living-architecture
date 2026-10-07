## Context

Both twins read the model by globbing `architecture/model/*.c4` and parse views from `architecture/views.c4`,
returning an empty parse when it is absent. The parsers skip blocks they do not own (`parse_model` ignores
`views` blocks; `parse_views` stops after the first `views` block). A model without roots is already a setup
error (`arch-check.root-missing`, exit 2). `la-arch-diagrams` maps every model/views problem to exit 1 ("cannot
regenerate"). See proposal.md for motivation; the behaviour is in the `c4-layout`, `arch-check` and
`arch-scaffold` deltas.

Principles that apply (`architecture/system.arc42.md`): 1 — both twins behave identically, pinned by the
conformance corpus; 2 — every message, the extension list and the new command surface come only from `shared/`.
No new import arrow is needed: the layout check and the migrator live in the `c4` node, which `archcheck` and
`cli` already import.

## Goals / Non-Goals

**Goals:** one place that defines "the model" and that every reader passes through; make a split model
unreadable rather than silently partial; a one-command, verified migration for existing repos.

**Non-Goals:** migrating SLayer / slayer-evals (they run `la-arch-migrate` after release); a version bump (separate
PR); constraining block order inside `model.c4`; new rules for invalid UTF-8 (keeps today's setup error).

## Decisions

1. **Layout violations are a precondition, not findings.** `la-arch-check` exits 2, `la-arch-diagrams` exits 1
   (its existing "cannot regenerate"; 2 means usage error there). Alternative — a `c4-layout` finding id with the
   other checks still running — rejected: elements in stray files would be dropped and flood `model-truth` /
   `claims-exactly-once` with misleading findings, and diagrams would render a partial model.
2. **One layout module in `c4`, called before parsing.** It discovers sources, scans blocks, classifies the
   layout (canonical / legacy / neither) and formats the single message. `parse_model` / `parse_views` read only
   the canonical paths. Only the migrator knows `architecture/model/`. Classification is separate from
   diagnostics: every discovered source is listed first, then whether automatic migration applies.
3. **A dedicated top-level block scanner**, not the parser's tolerant brace counting: it consumes the whole file
   (quote- and `//`-comment-aware, same lexical rules as the parser) and yields top-level blocks with their kind,
   byte span and interior span, plus violations for unexpected top-level text and unbalanced/unclosed braces.
   It is shared by the layout check and the migrator. It replaces `c4.no-views-block`.
4. **Discovery semantics fixed in the contract for twin parity:** case-sensitive extensions from one shared
   constant (`.c4`, `.likec4`); file symlinks count as files, directory symlinks are not followed; a canonical
   path that is not a regular file is "not a file"; ordering is by repo-relative POSIX path in code-point order
   via one comparator per twin (the npm twin must not rely on default UTF-16 sort). An unreadable directory
   surfaces as the existing `OSError` setup error. The scaffold's "first clash" uses the same ordering.
5. **Precedence:** `la-arch-check` validates `index.yaml` first (without it the repo is not set up), then the
   layout, then everything else. `--emit facts --top-level` stays model-free and skips the layout.
6. **Migration merges block interiors** (one `specification`, one `model`) rather than concatenating files, so
   migrated and scaffolded repos have the same shape. Interiors are copied verbatim in sorted-file then file
   order; a comment on a block's opening line travels with the interior; comments and blank lines outside blocks
   go, in order, to the top of `model.c4`; any other top-level text or block kind makes the layout
   non-migratable. Merging is semantics-preserving for our parser because each file's blocks are independent
   regions.
7. **Verify, then write.** The new layout is rendered in a staging directory and parsed; the full normalized
   `ModelParse` (elements with metadata/kinds/virtual/metadata problems and relations with legacy flags in order;
   `findings` and `metadata_findings` as multisets, since spec-block merging can reorder findings) and the
   `ViewsParse` must equal the legacy parse; a missing `views.c4` equals the created empty block.
8. **Transaction:** read and keep every legacy file's bytes; create new files exclusively (`x` mode); only then
   unlink the legacy files and `rmdir` an emptied `architecture/model/`; on any `OSError` rewrite each deleted
   file byte-for-byte, recreate the directory, and remove only the files this run created. A pre-existing
   `views.c4` is never opened for writing.
9. **New command `la-arch-migrate`** rather than auto-migration inside the checks: a check that rewrites the repo
   would migrate CI's throwaway checkout and stay green on an unmigrated repo. Exit codes `{0: migrated or
   nothing to migrate, 2: not migratable, verification mismatch, or filesystem error}`. It does not require
   `index.yaml` (the parses it compares do not).
10. **Corpus migration by intent:** fixtures where the layout is incidental are mechanically migrated (merged per
    decision 6, plus a minimal `views.c4` where their arch-check/diagrams outcome is pinned) with goldens
    unchanged; fixtures that test layout (`arch-check-identity-no-model-files`, `arch-scaffold-existing-*`,
    `arch-diagrams-no-views-file`, `arch-check-parse-views-no-views-block`, scaffold output cases) are rewritten
    deliberately with reviewed goldens.

## Risks / Trade-offs

- [Downstream repos break on upgrade] → the setup error names `la-arch-migrate`; migration is one command with
  a verified, all-or-nothing write.
- [Twin drift in discovery / ordering] → contract-fixed semantics (decision 4) and cross-twin cases for nested,
  symlinked, uppercase-extension and ordering scenarios.
- [Mechanical fixture migration silently changes a case's meaning] → classify by intent first; goldens of
  incidental fixtures must stay byte-identical, so any golden diff there is a bug.
- [Partial rollback on a crash (not an `OSError`)] → out of reach of an in-process transaction; the legacy bytes
  are only deleted after every new file is written, so the worst case is both layouts present, which the layout
  check reports by name.

## Migration Plan

Ship in the next release. Each downstream repo runs `la-arch-migrate` once and commits the result; until then
`la-arch-check` exits 2 with the migration hint. Rollback: `git checkout` the migrated paths.
