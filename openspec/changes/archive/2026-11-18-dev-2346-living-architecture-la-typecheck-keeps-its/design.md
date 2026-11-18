## Context

See proposal.md for the motivation and the repro.

- A basedpyright baseline entry is `{code, range: {startColumn, endColumn, lineCount}}` under a `./path` key: no
  line number. Entries of a file are in position order, and basedpyright matches them in order.
- `refactor/baseline_align.py` already carries entries through a refactor: it learns which diagnostics the baseline
  hides from two checker runs (empty baseline, copy of the baseline), pairs them with entries in order, and maps
  each range forward through the refactor's edits (`text_edits`, `map_range`, UTF-16 conversion on both sides).
- `typecheck` may import `lang`, `config`, `contract` and `twin`; `refactor` may import `typecheck`, `lang` and
  `changes`. `changes` already has `file_at` and `base_paths` (git's rename list since a ref), in both twins.
- Principles that apply (`architecture/system.arc42.md`): 1 twins, 2 shared contract only, 3 language-specific code
  only in `lang` and `refactor`, 4 only a configured command runs. None is contradicted.

## Goals / Non-Goals

**Goals:**

- One mapping rule for `dr-refactor` and `--realign-from`, in one place.
- No checker run on the tree at `REF`.

**Non-Goals:**

- Automatic realignment on a plain check.
- Tolerant matching in `la-typecheck`.
- Following a rename whose destination git does not track, or code moved between files by hand.
- Any change to `dr-refactor`'s behaviour or to the TypeScript baseline.
- Skill text changes: the hint and `docs/commands.md` carry discovery.

## Decisions

1. **Realign the baseline file; no tolerant matching** (default). Options: realign through a diff, or match
   loosely (file and rule count). Loose matching needs a second matcher in `la-typecheck` that disagrees with plain
   basedpyright in an editor or CI, and passes a fixed error plus a new one of the same rule.
2. **Explicit `--realign-from <ref>`; nothing automatic** (user). Options: explicit flag, automatic against HEAD on
   every check, or both. The caller names the commit where the baseline matched, so committed edits work, and a
   plain check still changes the baseline only by shrinking.
3. **Follow the renames git reports since `REF`** (user). An extension beyond the issue's outcome, approved:
   without it a hand-moved file's baselined errors all come back as new.
4. **Map backward from the current diagnostics** (default). Options: run the checker on a checkout of `REF` and
   map forward, or map each current unmatched diagnostic back through the diff from the current text to the text at
   `REF`. A checkout of `REF` lacks the repo's environment and gives different diagnostics.
5. **Same range rule as `dr-refactor`; the pure pieces move to `lang`** (default). `typecheck` cannot import
   `refactor`, and two copies would have to agree by hand. Moved: the entry match and the ordered pairing, the
   baselined-diagnostic count, the report reader, `text_edits`, and `position_map` (`Edit`, `map_range`).
   `refactor/baseline_align.py` keeps the refactor-specific part and imports the rest.
6. **`typecheck` orchestrates and reads git through `changes`** (user, approved edit). Verbatim: add the line
   `typecheck -> changes` after `typecheck -> twin` in the `python` root and in the `typescript` root of
   `architecture/model.c4`, and regenerate the `system` and `npm` diagrams in `architecture/system.arc42.md` (one
   new line `typecheck --> changes` each).
7. **Validate `REF` up front in the invoking twin** (default). Options: up front in both twins, or only inside the
   Python section. Up front gives one error before any header and never ignores a bad ref in a TypeScript-only repo.
8. **The realigned baseline is written before the check and stands whatever the check returns** (default;
   rejected (codex) the proposal to write only after a passing check). A realigned entry is true independently of
   other errors, and writing it lets later plain checks show only the really new errors. The spec states that
   realignment never changes the number of entries, so the shrink rule is untouched (codex: make this explicit).
9. **An entry is taken only in list order** (codex). "First unused entry of equal shape" could baseline a new error
   on another line. An unmatched diagnostic takes an unmatched entry only if the entry lies after every entry of a
   diagnostic earlier at `REF` and before every entry of a later one.
10. **UTF-16 conversion on both sides of the mapping** (codex). Diagnostics are UTF-16, the diff is in code points.
11. **A rename onto a key that holds entries merges in position order** (codex).
12. **The flag does nothing for TypeScript** (default): its key has no position.
13. **Hint after a failing Python check with a baseline** (user, part of the chosen option).
14. **No dry-run for the flag** (default): the baseline is a committed file, so `git diff` shows the change.
15. **Approved wording** (user, approved wording):
    - `--realign-from REF` help: `move each Python baseline entry to where its error is now, given a commit where
      the baseline matched, then check`
    - `typecheck.bad-ref`: `la-typecheck: {ref} is not a commit`
    - `typecheck.realign`: `la-typecheck: {language}: {count} entr(ies) of {baseline} realigned from {ref}`
    - `typecheck.realign-hint`: `la-typecheck: {language}: if an edit moved errors that {baseline} held, run
      la-typecheck --realign-from <commit where it matched>` (one line in `findings.yaml`)

## Risks / Trade-offs

- [A fixed error and a new same-shaped error of the same rule between the same matched neighbours cannot be told
  apart, because entries have no line] → The baseline format's own limit: plain basedpyright already matches such a
  pair on unedited lines. Order consistency (decision 9) removes every case order can decide.
- [A `REF` where the baseline did not match gives a meaningless mapping] → The caller states it; an entry is still
  taken only on equal rule, columns and line count, so a wrong `REF` mostly realigns nothing.
- [Git's rename detection is a similarity heuristic] → A file moved and heavily rewritten is not followed; its
  errors stay new, the safe side.
- [Three checker runs under the flag] → The two realignment runs cover only the changed baseline-listed files.
- [Existing goldens gain the hint line] → Updated with that stated reason; reviewed as a golden diff.
