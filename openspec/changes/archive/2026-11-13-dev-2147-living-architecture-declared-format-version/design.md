## Context

See proposal.md (Why). The first round is archived as
`2026-10-24-dev-2147-living-architecture-declared-format-version-for-architecture`. Today `c4/migrate` in each twin
runs one plan → verify → write pass for an unversioned repo; `_write`/`write` owns a fresh journal of undo closures
(one path each, temp files included) and catches only filesystem errors, and the config is swapped in last through a
temp file whose original bytes are not journalled. `shared/config.yaml` carries a scalar `format`, read by
`config_format`/`configFormat` and by the conformance runner's `<FORMAT>` substitution. `scripts/release_rule.py`'s
`bump_problem` is applied by `scripts/release-check` (plain `python3`, no YAML library) and by the pre-tag test in
`python/tests/test_versions.py`.

Symptom: a declared released older format is refused even by `la-arch-migrate`. Structural cause: migration is one
hard-coded pass with no per-format step slot, and nothing ties a format-changing release to a conversion. The fix
makes the released formats one list in `shared/` (system principle 2), keys the steps on it, and checks the pairing in
both twins' tests and in the release rule.

Principles that apply (`architecture/system.arc42.md`): 1 (twins identical; the corpus decides), 2 (the formats list
and every text come from `shared/`), 3 (`migrate` stays language-neutral), 4 (no target-repo code runs). No model,
views or arc42 edit: `c4 -> config` exists and `scripts/` is not modelled. The modified specs keep their attachments
(`c4-layout` on `python.c4`; `repo-config` and `shared-contract` cross-cutting, `touches` unchanged).

## Goals / Non-Goals

**Goals:** a declared released older format migrates step by step; one transaction and one rollback across the chain;
a net-effect report the `la:pr` preflight can commit verbatim; replacement stamping; mechanical enforcement that
every released older format has a step and that a release appends exactly its own version.

**Non-Goals:** a real older-format conformance case (it arrives with the first format bump, together with its step);
a step that edits `living-architecture.yaml`; a clean-working-tree check; separate versions for `architecture/` and
the config.

## Decisions

1. **Steps run one after another on disk inside one transaction (user).** Each step plans and verifies against the
   repo as earlier steps left it, then applies into the shared journal. Over in-memory staging, which would need a
   virtual file layer under `classify`, `load_index`, `parse_views`, `sources` and `parse_model_files` (shared with
   `la-arch-check`) in both twins. A git clean-tree precondition was weighed and not added: the journal already gives
   all-or-nothing ("keep it simple").
2. **An outer transaction owns the journal across plan → verify → apply of every step (codex).** It catches migration
   refusals as well as filesystem errors; after a successful restore it re-raises the original failure, after a
   failed one `arch-migrate.rollback-failed` names the paths left changed.
3. **The transaction records logical changes apart from undo operations (codex).** Each write, move, delete and
   directory removal is recorded with the path's state at first touch (existence, bytes, mode); undo closures stay
   low-level. Temp files and directory housekeeping never enter the logical record or the first-touch order.
4. **Net-effect report (default; codex for the delete rule).** The `la:pr` preflight commits exactly the printed
   paths, so a `wrote x` followed by `deleted x` would break its `git add`. Composition rules are in the c4-layout
   delta; a composed move's source is never also reported deleted. One step prints exactly today's lines.
5. **The config replacement uses the journalled replace (codex)**, so a rollback restores its bytes and mode.
6. **`formats` replaces `format` in `shared/config.yaml` (default)**: one source, the current format is the last entry;
   a single-line flow list so `scripts/` can read it without YAML.
7. **The stamp is decided before any step writes, and steps never write the config (default)**, so an unstampable
   config still refuses with nothing written and the refusal order of today's goldens holds.
8. **Replacement stamp grammar (codex).** Exactly one top-level line with the unquoted key `format` directly followed
   by `:`, then spaces or tabs, one single-line plain, single- or double-quoted scalar, optional whitespace and
   comment. Anything else is `null` (`stamp-mismatch`). Verified by re-parsing to the original mapping with `format`
   set to the current format.
9. **Each step declares `{source, target}` (codex)**; the twin tests check the unversioned step targets `formats[0]`
   and each other step's source is a released older format whose next entry is its target, with exactly one step per
   such source. A list edit that silently retargets a step fails.
10. **The formats rule sits in the `bump_problem` path (default; codex)**, so both `scripts/release-check` and the
    pre-tag test apply it.
11. **The previous release's list (default; codex for failing closed):** `formats`, else `[format]`, else `[]` when
    the file is absent at that tag (`git cat-file -e`). An existing file declaring neither recognisably, or another
    `git` failure, is a problem. A suite test checks the regex read of HEAD's file equals the YAML read.
12. **An older declared format no release used stays refused (issue comment)**, reworded.
13. **No new conformance case (rejected codex finding).** The reworded refusal is pinned by
    `arch-migrate-format-unknown-older`; single-step move reporting by the `arch-migrate-arc42-*` and
    `arch-migrate-cross-cutting-*` goldens; replacement stamping and chains are unreachable through the CLI while
    `formats` is `[0.4.0]` (a declared `0.3.0` is refused before stamping). Twin parity of the stamp comes from the
    shared `stamp` vectors; the chain is covered by mirrored unit tests with a fake registry and format list.

Approved wordings:

- `arch-migrate.unknown-format`: "`cannot migrate from format {declared}, which no la release used; this la reads
  format {current}`" (user, approved wording)
- `arch-migrate.stamp-mismatch`: "`cannot write the format into living-architecture.yaml; set format: {current} by
  hand`" (user, approved wording)
- `la-arch-migrate` help: "Convert the repo to the current format (`format` in living-architecture.yaml) one released
  format at a time, starting from the declared one. A repo that predates the key first gets its legacy
  architecture/model/*.c4 model merged into architecture/model.c4 (creating an empty architecture/views.c4 when
  absent) and the retired arc42 metadata key converted (each element's doc moved to architecture/<element
  id>.arc42.md, the key dropped, cross_cutting_arc42 docs flattened into architecture/ and their diagrams keys
  renamed). Then the current format is stamped. Verified; writes everything or nothing and prints each changed path
  once, by its final state." (user, approved wording)
- `plugin/skills/pr/SKILL.md` preflight: "if it reports the missing-format finding (the one naming
  `la-arch-migrate`)" → "if it reports a format finding naming `la-arch-migrate` (a missing or older format)" (user,
  approved wording)
- `docs/development.md`: "…also appends its own version to `formats` in `shared/config.yaml` and adds, in both
  twins, the `la-arch-migrate` step from the previous format; the tests check that every older format has a step, and
  `scripts/release-check` that the release appended exactly its own version." (user)
- `shared/config.yaml` comment: "Every released repo format (`format` in living-architecture.yaml), oldest first: the
  la version that introduced it. The last is the format this la reads and writes; la-arch-migrate converts from each
  earlier one." (user)

## Risks / Trade-offs

- [A later step's refusal comes after earlier writes] → the whole journal rolls back; a failed restore names the
  paths, and git covers the rest.
- [Chain behaviour is not observable through the CLI until a second format exists] → mirrored twin unit tests with a
  fake registry; the first format bump adds the real conformance case.
- [The regex reader of `shared/config.yaml` drifts from the YAML] → a suite test compares both reads; an
  unrecognised old file fails closed.

## Migration Plan

No adopter action: `0.4.0` repos are unaffected. Rollback: revert the change.
