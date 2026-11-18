## Context

Both twins check name conflicts in N+1 passes: each `new_name` entry alone against the code before the map, then all
entries together (Python `RenameMap.check_names`, npm `nameConflicts`). The alone passes refuse a chain by
construction, and they run only in the last phase. Refusals are plain texts built where they are found: an entry's
error loses its entry, and a group's refusals are collected for its `[rules]` line and again for the final report,
which also carries the exit code. `Site.parse` takes an optional base, and its callers pass the working directory for
`--keep` and the project for `--with` / `--without`. The npm twin gives a `--with` stand-in the first entry's new name.

The reproductions (projects, maps, commands, observed output) are in the agent notes of DEV-2344.

## Goals / Non-Goals

**Goals:**

- One name-conflict check, on the code after the whole map, in both twins.
- The collisions the map alone decides reported in `checks`.
- One place that turns an entry's error or conflict into a refusal naming the entry and its locator.
- One rule for where a refusal is printed; the exit code independent of where.
- One base for every site flag.
- The twins agree on a stand-in two entries reach.

**Non-Goals:**

- Chains or swaps of module names: module entries keep the check against the code before the map.
- A per-site new name for a stand-in, stand-in defaults, a per-site pick for a docstring two entries reach (DEV-2340's
  map-authoring sub-issue, DEV-2343).
- New capture rules (DEV-2297): what counts as a capture on the post-map code is unchanged.
- Moving the new-name validity check (`refactor.cannot-rename` for a keyword) out of the computing phases.

## Decisions

1. **One post-map name-conflict check replaces the per-entry passes.** Options: an exception for freed names inside
   the per-entry pass; one check over all entries' edits. Taken: one check. The map is written all or nothing, so the
   code after the whole map is the only state that exists; one path instead of N+1 also removes N passes from a long
   run. Whatever the alone pass refused and the together pass allows is a name another entry frees. (default)
2. **Swaps apply like chains.** A swap is a two-entry chain; refusing it would need a rule of its own. The scenario
   "Swap of symbol names applies" is new; the scenario
   "Swap in one scope refused" keeps its name (OpenSpec lets a modified requirement drop no scenario) and now pins the
   swap that is still refused, of two module names. (default)
3. **Module entries do not chain in this change.** Options: symbols only; modules too (move ordering, temporary paths
   for a swap, their rollback, `--stub` on a path another module moves onto, Python only); modules in an issue of their
   own. Taken: symbols only, no new issue. (user)
4. **A group's refusal is printed only under its `[rules]` line; the final report holds what no line printed.**
   Options: keep the streamed copy; keep only the final report with a per-line entry prefix. Taken: the streamed copy,
   so a long run shows a refusal when its group finishes, under the line naming its entries. (user)
5. **The early own-scope check covers every symbol kind**, not members only. (user)
6. **Entry attribution is one wrapper template, `refactor.entry-refusal`, with the locator.** Group findings are
   attributed by their `[rules]` line and keep their `path:line: kind:` shape. Findings naming their entries and
   run-level findings are unchanged. (default)
7. **`rename` and `retarget` print `entry 1 (...)`**, keeping them byte-equal to their one-entry map. (default)
8. **A name conflict belongs to the entry whose new name it names; where two or more entries' renamed declarations
   meet, to the latest, naming the earliest's first declaration.** Name conflicts are listed by entry index. (default)
9. **With a `refactor.map-conflict`, no name-conflict check runs.** Options: let the earlier entry's edit stand
   (order-dependent findings about a program that will not exist); check only the entries outside every map conflict
   (an excluded entry may be the one freeing a name); skip. Taken: skip. (user)
10. **Site flags resolve against `--project` only**, as the issue states; `Site.parse` takes the project root and no
    other base. (default)
11. **The early check refuses only when certain**: not under a `--keep` on either declaration's line, not when the
    resolved entries do not decide whether the name is freed. (default)
12. **Exit status and printing are separate**: the run's exit code is the highest of all its refusals, the final
    report prints the unprinted ones. (codex)
13. **The spec's "listed again" and `--fail-fast` clauses are rewritten**, with a `--fail-fast` case. (codex)
14. **The early check reuses the tables of the full check**: Python's per-scope binding sites and member
    declarations (`self.x`, class attributes, properties), the TypeScript compiler's symbols with their meanings and
    legal merges. It is no second scan. (codex)
15. **A conflict carries its entry and the declaration it meets from where it is found**, in both twins; attribution is
    defined for more than two entries, merged duplicate indexes, retargets and entries with several declarations.
    (codex)
16. **The TypeScript stand-in fix writes a full edit set per distinct new name**, references included, and leaves the
    refusal to the map-conflict merge. (codex)
17. **Every `Site.parse` caller moves to the project base**: the site checks, the line-keep check, `Keeps`, stand-in
    classification. (codex)
18. **Chains, swaps and converging names are covered per symbol kind and in both entry orders**; the existing
    converging, capture, merged-interface and catch-scope cases stay. (codex)
19. **`refactor.entry-refusal: '{entries} ({locator}): {text}'`** (user, approved wording)
20. **`shared/cli.yaml` help, in `rename`, `rename-map` and `retarget`** (user, approved wording):
    - `--keep`: `leave every edit on this line, in this file or under this directory; PATH relative to --project (repeatable)`
    - `--with`: `rename the stand-ins declared on this line too, with their hierarchies; PATH relative to --project (repeatable)`
      (`retarget`: `rewrite the stand-ins declared on this line too, with their hierarchies; PATH relative to --project (repeatable)`)
    - `--without`: `leave the stand-ins declared on this line, with their hierarchies; PATH relative to --project (repeatable)`
21. **`plugin/skills/deterministic-refactor/SKILL.md`, Commands paragraph** (user, approved wording):
    - `resolves every entry before renaming any, and writes all or nothing` becomes
      `resolves every entry before renaming any (so entries may chain or swap names), and writes all or nothing`
    - `` `--keep PATH[:LINE]`, `` becomes `` `--keep PATH[:LINE]` (site paths relative to `--project`), ``

## Risks / Trade-offs

- [The early check refuses something the full check allows] → it reads the full check's own tables and refuses only
  when certain; paired cases pin the non-refusals (TypeScript merges, disjoint meanings, static and instance sides,
  block scopes; Python nested scopes, comprehensions, `global` / `nonlocal`).
- [A refusal that the alone pass caught and the post-map check misses] → the existing capture, converging-names,
  merged-interface and catch-scope cases stay, and chains, swaps and converging names run per kind in both orders.
- [A printed refusal no longer counted in the exit code] → status and printing are separate collections; a
  rules-only refusal is tested with and without `--fail-fast`.
- [A late name conflict behind a map conflict costs another run] → accepted (decision 9); the early check reports
  the map-decidable ones first.
- [`--keep` relative to a working directory other than the project breaks] → intended; the finding is
  `refactor.site-missing`, and absolute paths work as before.
- [Many goldens change shape] → each is regenerated with the reason in its commit message and its diff reviewed;
  none is regenerated to absorb an unexplained difference.
