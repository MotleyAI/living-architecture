## Context

See proposal.md (Why). Every command builds its parser from `shared/cli.yaml`. The Python twin has one console-script
wrapper per command (`cli/__init__.py`) with no shared dispatcher; the npm twin has a central dispatcher that forwards
native-mismatch commands and runs script shims before handler dispatch. Only some commands load the config
(`la-arch-check` late, `la-arch-diagrams` and `la-arch-scaffold` never). `la-arch-migrate` lives in `c4` and writes new
files exclusively.

## Goals / Non-Goals

**Goals:** one declared repo format; one check before any handler in both twins; format detection only inside
`la-arch-migrate`, frozen at today's single detected step; a verified, all-or-nothing stamp.

**Non-Goals:** reading any format other than the current one; replacing an existing `format` value (unreachable
until the first version-keyed step exists, DEV-2139); separate versions for `architecture/` and the config; a
`--format` printing flag; format code in `la-arch-scaffold`.

## Decisions

1. **One repo-wide key `format` in `living-architecture.yaml`**, over a key in `index.yaml` or one per file: the
   user chose one number; the first action on any older repo is a deterministic migration.
2. **The value is the `la` version that introduced the format**, over an integer counter: only then can an older
   `la` name "upgrade la to >= X" without a table it cannot have. It moves only in releases that change the format;
   a test pins current format <= each package version and the plugin version.
3. **Only the current format is read.** A missing key is older by definition (the key is part of the format), so
   readers carry no heuristics; detection lives only in `la-arch-migrate` for unversioned repos.
4. **The check runs in CLI dispatch, declared by the manifest**, over a check inside `load_config` (which would leave
   commands that never load the config ungated). Order in both twins: parse (help, usage) → resolve the root →
   format check → handler, forwarding or script. Python gains one dispatch helper every wrapper calls. The check
   lives in `config`; `cli -> config` already exists. Exempt: `la-arch-migrate` (the cure), `la-doctor` (reports it)
   and the review shims (they read GitHub; `la-pr-reviewers` reads config only through the gated `la-config`).
5. **Lenient read before the schema.** The check reads the committed file with the shared YAML profile and decides on
   `format` alone, so an older `la` refuses a newer config before its unknown keys produce a schema error. Unreadable,
   invalid-YAML or non-mapping files pass through to each command's existing handling (unchanged goldens and codes).
6. **Comparison without floats.** Components match `0|[1-9][0-9]*`; compare by digit count, then lexically — the same
   in both twins, never via JavaScript `Number`.
7. **One refusal code, 2**, stated once in the manifest header and in each exit map, over per-command codes.
8. **No committed file → no check.** Not-onboarded repos keep working on defaults; `la-doctor --require-config` already
   routes them to `la:init`. `format` is not a local-file key.
9. **`la-arch-migrate` owns the stamp; `c4 -> config` is added to the model** (approved), over orchestrating in `cli`
   (which would split one all-or-nothing transaction across nodes). `config` provides the declared-format read and the
   stamp (text → stamped text, verified by re-parsing to the original mapping plus `format`). Insertion only: after
   leading comments, blanks, `%` directives and a `---` marker, with the file's line break; anything that fails
   verification is refused (`format` must be added by hand).
10. **Write protocol.** Stage every output; create new files exclusively; delete legacy files; replace the config last
    with a temp file in the same directory and an atomic rename. On an OSError undo in reverse: remove created files,
    restore deleted files, the model directory and the config bytes. A restore failure is collected, not suppressed:
    the error names each path left changed.
11. **Readers stop suggesting the migration.** `classify` keeps its `legacy` state for `la-arch-migrate`; the readers'
    message always ends with the merge-by-hand tail and `c4-layout.migrate` is removed.
12. **`la:init` stamps through `la-arch-migrate`** (single writer of `format`); approved skill wording in tasks.md.
13. **Fixtures use `format: <FORMAT>`**, substituted by the runner with the bundled current format in root
    `living-architecture.yaml` overlays and `write:` steps only. Goldens that echo the config use the existing
    `{pattern, replace}` normalization with a version-agnostic pattern, never a blanket format replacement (the
    package version is also `0.4.0`).
14. **Ordering: this change is 0.4.0; DEV-2139 follows as format 0.5.0** with a step keyed on a declared `0.4.0`, so
    the `arc42` key never needs detection.

## Risks / Trade-offs

- [Every adopter repo is refused until migrated] → one `la-arch-migrate` run stamps it; skills surface the hint
  through the `la-doctor` preflight.
- [A config the stamp cannot edit textually] → refused with "add `format` by hand"; verification makes a wrong edit
  impossible.
- [A partial rollback] → reported with the paths left changed.
- [Format bumps churn fixtures] → `<FORMAT>` keeps the value in `shared/` only.

## Migration Plan

Adopters upgrade to 0.4.0 and run `la-arch-migrate` once. This repo and `acceptance/node-only/repo` are stamped in
this change. Rollback: install 0.3.x and delete the `format` line.
