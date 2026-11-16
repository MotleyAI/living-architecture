## Context

Both twins raise each refusal where it is detected, so the first one ends the run: `Keeps.check` (`sites.py`) and
`_check_sites` after `compute` (`rename_map.py`), `WalkerGap` from inside rope's occurrence search, `NameConflict`
from parameter seeding, `MapConflict` from `merged`, locator errors from `resolve`, and the early return on retarget
refusals in `refusal()` (Python) and `runEntries` (TypeScript). Checks that need no references sit after the
expensive work, and nothing reports progress. Python computes in loops over all entries (prepare = rope occurrences,
then one language server: seed, rules, finish + retarget); TypeScript runs one language-service rename per target,
then the rules per old-name group (`NameGroup`). `BaselineFailed` and `LanguageServerError` drop their cause
(`from None`; the language server's stderr goes to `DEVNULL`). Map loaders in both twins stop at the first invalid
entry, and both routing front ends load the map to pick its language.

**Symptom → structural cause → fix.** The late `--keep` is one instance of "a check raises at its point of detection,
interleaved with the computation". The fix removes the class: one refusal collector per run that every check appends
to (exceptions only for conditions the run cannot continue past), a fixed phase sequence that puts every check that
needs no references before the first reference search, and one progress reporter. Grounding in
`architecture/system.arc42.md`: principle 1 (twins: the phases, the progress lines, the collection and the early
checks are one contract, pinned by conformance), principle 2 (every new text in `shared/findings.yaml`, the new option
in `shared/cli.yaml`), principle 3 (walker and checker probes are Python-only code inside `refactor` and `lang`),
principle 4 (the probe runs only the configured command). No model or arc42 change: no new cross-node import, and the
work stays in the `refactor` spec owned by `python.refactor`.

## Goals / Non-Goals

**Goals:**
- No refusal a run can find without a reference search waits for one; each such refusal is listed in one report.
- Every refusal of a run is reported in one run.
- A long run shows its phase, the entry it is searching, and each group's result as soon as it is known.
- A failed checker says why.

**Non-Goals:**
- Speeding up the reference search or the rules (DEV-2301, DEV-2299); per-phase timings (DEV-2299).
- Normalizing a checker's stderr (rejected Codex finding 9).
- Per-entry progress for `move-symbol`, `move-module` and a module rename (they have no entries).

## Decisions

1. Progress is always on, on stderr, every subcommand; every `dr-refactor` golden's stderr is re-blessed. Options: always
   on / opt-in `--progress`. Opt-in brings the silent run back whenever the flag is forgotten. **(user)**
2. Every refusal is collected by default; `--fail-fast` (on `rename`, `retarget`, `rename-map`) stops at the first one
   after `checks`. Options: fail fast by default with `--keep-going` (the issue's wording) / collect by default. Fail
   fast by default costs one run per refused entry, the loop DEV-2301 complains about; live progress already lets a
   watcher stop early. **(user)**
3. A group's progress line is followed by its refusal lines, and the final combined report is printed unchanged at the
   end. Options: count only / details in both / details only per group. Only "both" keeps what an early stop found
   and the final report's pinned shape. **(user)**
4. The Python checker probe starts the language server (handshake, then reused for the run) and runs the configured
   command once with `--outputjson` on one source of the refactor (the first entry's file, `--file`, or `--module`'s
   first source) against an empty temporary baseline, only when the baseline phase will run. Options: start-only
   probe / one real run. **(user)** The probe proves the command runs and its report parses; it does not prove the
   alignment over the affected files succeeds, which still refuses at alignment with its cause. **(codex)**
5. Both `refactor.baseline-failed` and `refactor.pyright-failed` carry the cause (exit code and stderr, start error, or
   error answer); the Output format requirement gains the carve-out "except a failed checker's cause after its
   finding". **(user)**
6. Progress wording **(user, approved wording)**:
   `refactor.progress-phase: '[{phase}]'`,
   `refactor.progress-item: '[{phase} {n}/{count}] {entries}: {old} -> {new}'`,
   `refactor.progress-clean: '[{phase} {n}/{count}] {entries}: {old} -> {new}: clean'`,
   `refactor.progress-refused: '[{phase} {n}/{count}] {entries}: {old} -> {new}: {refusals} refusal(s)'`,
   `refactor.progress-entry: 'entry {index}'`,
   `refactor.progress-entries: 'entries {indexes}'`.
   Phases `resolve`, `checks`, `references`, `rules`, `baseline`, `write`. `[references n/count]` per merged entry
   when its search starts; `[rules n/count]` per old-name group when it is done, in order of each group's first
   entry; `{new}` a group's distinct new names in map order, `, `-joined; `{indexes}` `, `-joined.
7. `[rules]` lines are per old-name group, not per entry: TypeScript's rules and both twins' deduplicated findings are
   owned by the group, so a per-entry line would credit a group's refusals to unrelated same-named symbols. Python's
   rules and finish loops run group by group (the result does not depend on loop order: edits merge, findings sort).
   **(codex)**
8. A group's line counts its own refusals after its kept sites are dropped (keep filtering runs per group as it
   finishes; matched keeps accumulate). Refusals between entries (map conflicts, name conflicts over the merged edits,
   unmatched keeps) appear only in the final report. **(codex)**
9. Resolution never searches references. Python starts at most one language server per run, lazily, shared by the
   resolve fallback, the probe and the computation; a server that cannot start stops the run at once with its cause.
   **(codex)**
10. Duplicate findings are computed among the resolved entries only (converging names are a name-conflict check
    over the edits since DEV-2297, so they join the final report); any resolution or check finding refuses before
    anything is built, so no retarget uses a target that did not resolve. **(codex)**
11. A merged target is labelled with every map index it stands for; the Output format requirement's "one header per
    entry" is corrected to "entries merged as duplicates counting once", today's behaviour in both twins. **(codex)**
12. `[baseline]` is printed when the language's baseline file exists (and, for Python, its command is set), whether
    or not anything is then realigned. **(codex)**
13. Each `--keep`/`--with`/`--without` argument occurrence gets at most one finding; a `checks` failure replaces its
    later exact check. **(codex)**
14. One map loader per twin returns every invalid entry's index; the invoking twin reports them all (exit 2) before
    routing, as the map's language cannot be decided. An unreadable or non-list document names entry 1. **(codex)**
15. The keep text check matches every entry's old name and every retarget entry's target name (a retarget can edit a
    line holding only the target, e.g. a duplicate import it removes). **(codex)**
16. Structural fix (collector, phases, reporter) over moving the keep check alone. **(default)** The late keep is one
    instance of first-error-wins-anywhere.
17. `resolve` precedes `checks`: the keep text check and the walker candidates need the old names. **(default)**
18. `--with`/`--without` get an existence check only. **(default)** A text check is unsound for a TypeScript
    computed-name stand-in (`[KEY]()` does not spell the name), and the issue asks only for existence.
19. The keep text check is an over-approximation that never refuses a keep the exact check accepts: escapes decoded,
    NFKC for Python, string-literal values starting on the line (escaped spellings, implicit concatenation), only
    files the run can edit (prose files only with `--docs`), a moved file counting; skipped when an unresolved entry
    spells no name. **(default)**
20. New `refactor.site-missing: '{option} {site} names no file, directory or line in the project'` (exit 2);
    `keep-unmatched` and `not-stand-in` keep their texts. **(default)**
21. A combined report's exit code is the highest of its findings' (2: map, locator, site, duplicate; 1: the rest),
    as the routing rule combines exit codes. **(default)**
22. Every invalid map entry, name conflict and map conflict is collected: the issue's "every refusal of a run". The
    name-conflict checks after the rules (keyed collisions per entry; bindings and member namespaces for each
    `new_name` entry alone, then all together) each report their first site, each distinct finding once, in the
    final report only.
    **(default)**
23. Immediate stops stay only for a changed file, a failed write or rollback, a checker failing mid-run, and an
    unreadable map document. **(default)**
24. `--fail-fast` skips the exact keep check, which is wrong on a partial computation. Help text: `'stop at the first
    entry with a refusal (default: compute every entry and report every refusal)'`. **(default)**
25. Cause lines: `refactor.checker-exit: '  the checker exited with code {code}; its stderr:'` then the stderr lines
    indented two spaces; `refactor.checker-not-started: '  the checker could not start: {error}'`;
    `refactor.checker-error: '  the checker answered: {error}'` then any captured stderr. An unreadable baseline file
    keeps `refactor.baseline-failed` with no cause. **(default)**
26. Report orders: `resolve`/`checks` report — resolution findings by entry index, site findings in command-line
    order, walker gaps by path, checker findings; final report — retarget refusals, blind spots, stand-ins, name
    conflicts, map conflicts (each position-sorted), site findings in command-line order, the `refactor.blindspots`
    line. Today's blind spots → stand-ins → closing order is kept. **(default)**
27. No architecture model, arc42 or skill edit; `docs/deterministic-refactoring.md` documents phases, progress, the
    combined report and `--fail-fast`. **(default)**
28. Make fail fast the default — rejected (codex, finding 4): the user chose collect-by-default (decision 2).
29. Normalize the checker's stderr (ANSI, paths, length) — rejected (codex, finding 9): the output is Python-only, so
    no twin parity is at stake; it is relayed verbatim as `la-typecheck` already relays it, and conformance uses fake
    executables with fixed stderr.

## Risks / Trade-offs

- [~321 stderr goldens re-blessed] → one commit with the reason stated; review the golden diff for lines other than
  progress lines.
- [A refused run prints each refusal twice] → accepted (decision 3).
- [The walker probe adds one rope walk of every candidate file] → far cheaper than the occurrence search that walks
  the same files; it reuses the `dr-compliance` walk.
- [The checker probe adds one checker run per eligible refactor] → one file, gated on the baseline phase running.
- [`[rules]` lines are per group, so a map of many same-named entries shows fewer result lines] → the line names every
  entry index of its group.
