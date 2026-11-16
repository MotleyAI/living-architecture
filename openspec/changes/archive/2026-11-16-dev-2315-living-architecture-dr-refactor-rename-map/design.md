## Context

See proposal.md for the motivation. Measurements behind this design, all on a `git archive` copy of SLayer's
DEV-1607 branch (made a git repository in a temp directory, its `.venv` symlinked), 2026-11-16. They were taken
before DEV-2307 was merged into this branch, so without its follow guard (the export stops following a definition
at a third-party or typeshed file); task 6.1 re-measures on the merged branch as the "before":

| Measurement | Result |
|---|---|
| Plain `basedpyright` check of the project | 135 s, 3.9 GB |
| Export phase, cold, before this change | 474 s |
| Export command inside the server | 107 s (34 s walking 72,694 occurrences of 69 names, 71 s answering 43,964 position queries; 112,516 definition lookups take 95 s) |
| Export answer | 103 MB of JSON, 12,688 followed facts |
| Export phase with ambient analysis off, read loop unchanged | 420 s |
| Export phase with ambient analysis off and a linear read loop | 111 s |
| 11 `measures` entries: single-position fallback request behind ambient analysis | about 80 s |
| 11 `measures` entries: server shutdown behind ambient analysis | 291 s |
| 11 `measures` entries: `keyed.scan` | about 8 s per entry |
| 11 `measures` entries: conflict checks | 78 s: 2,390 re-parses 52 s, `MemberCheck._descendants` 18 s |

Architecture: principles 1 (twins) and 2 (shared contract) of `system.arc42.md` govern the `conflicts` phase;
principle 3 holds, as all Python-only work stays in `python.refactor` and `python.lang`. No model, arc42 or import
change. No new capability: the delta is on the `refactor` spec, owned by `python.refactor`.

## Goals / Non-Goals

**Goals:**

- A cold DEV-1607 run of an expected 4–6 minutes in one process (the issue's target is about 10), with stdout,
  refusals and exit codes byte-identical.
- An export that can be sharded later without redesign.

**Non-Goals:**

- Export sharding across processes, and entries in parallel (decisions 2 and 3).
- Replacing basedpyright or rope (decision 1); moving the member hierarchy off rope (DEV-2310).
- Reducing the export command's own 111 s.
- Delivering the export answer by file (decision 5).
- CI time and the export's follow guard: DEV-2307.

## Decisions

1. **basedpyright stays the source of truth.** Options: ty, pyrefly, zuban, keep. Kept: about 70% of the run was
   la's own code, none of the three has a batch export, and a resolver that is not the gate's checker weakens the
   guarantee where the gate cannot see (string members, keyed keys, `--docs`). (user)
2. **No export sharding in this change; the export stays shardable.** Reason: about 4 GB per shard. The seam is
   pinned by a test: exporting a request's files in two requests and merging gives the same `RunIndex` state as one
   request. (user)
3. **No parallel entries in this change.** Options: now, or after the re-timed run. Taken: after; each worker would
   hold its own copy of the index. The re-timed phase split is recorded on the issue for that decision. (user)
4. **Conflict checks report as a `conflicts` phase: one phase line and its own timing, no per-entry lines.**
   Options: phase only, or phase plus a line per entry. Taken: phase only; each entry's check should take
   milliseconds. (user)
5. **The export answer stays on the pipe.** Measured 111.39 s by file against 111.16 s by pipe once the read loop is
   linear. (default)
6. **Ambient analysis is switched off by one more anchor in the export preload**, setting `enableAmbientAnalysis` to
   false where the bundle assigns it from the server's file tracking, which always overwrites the class default. The
   server exposes no setting for it. A bundle where the anchor does not match
   exactly once is refused as `mismatch`, like the existing anchors; the verified version list is unchanged. (default)
7. **Only attribute-name and call-keyword-name edits skip the re-parse.** Options: also treat plain strings and
   comments as inert. Taken: the conservative pair; `__all__` entries and string annotations do bind. Every other
   edit kind re-parses as today. (default)
8. **The member hierarchy stays on rope**, with the classes declaring a member name found once per name per run.
   (default)
9. **Conflict-check time leaves `resolve`.** Follows from decision 4. (default)
10. **The export's follow guard is DEV-2307's, not this change's.** Planned here first, then found already shipped
    there when its branch was merged in; only decision 17's test remains. (user)
11. **A run that moves files keeps the full conflict check.** A moved module changes which file a module name
    resolves to, so untouched importers can change meaning. (codex)
12. **A file's analysed after-state and its offset mapping are built from the same binding-relevant edits and cached
    together**, keyed by those edits. Inert edits are not applied to the text that is analysed, so offsets in an
    analysed file map back through binding-relevant edits only. (codex)
13. **The judged set is the re-parsed files plus every file that star-imports one, transitively** (importers of the
    changed module, then their importers). An edited `__all__` is a binding-relevant edit. (codex)
14. **`conflicts` covers every check over the computed edits**: map conflicts, the binding check, the member
    namespace check and the keyed conflicts, in both twins; the phase starts before the first of them. The
    standalone module-rename path's check moves into it. (codex)
15. **The sharding-seam test compares merged index state**, not raw answers: a split export may repeat followed
    facts. (codex)
16. **Per-name cached sink candidates are neutral**: syntax spans and kinds only. Each entry classifies them with
    its own class and facts. (codex)
17. **Cold and warm runs agree when a skipped library follow is fetched on demand**; a test pins it. (codex)
18. **No version bump in this change.** Versions move at release; the release check requires a minor raise because
    tool inputs changed. (default)
19. **A rename map lists no leftover at a site another entry rewrites.** Each entry's rules still judge only its own
    symbol; the final report drops a leftover sitting on any entry's edit. (user)

## Risks / Trade-offs

- [Narrowing hides a conflict] → every existing name-conflict case stays green; new unit tests pin a class-body
  declaration, a star-import chain, an edited `__all__`, a retarget's added import, mixed edits in one file and a
  length-changing inert edit before a binding edit; the DEV-1607 run's refusal report is compared byte for byte.
- [DEV-2307's follow guard costs on-demand requests] → each miss is one request to a server that is now idle
  between requests; the SLayer run records the follow count and export time.
- [Golden churn] → the regenerated diff is reviewed to be exactly the `[conflicts]` line; `golden: manual` cases
  are edited by hand.
- [The estimate is extrapolated] → only the 111 s export is measured on the full map; rules and conflict checks are
  extrapolated from 11 entries. The re-timed run decides whether parallel entries or sharding come next.
