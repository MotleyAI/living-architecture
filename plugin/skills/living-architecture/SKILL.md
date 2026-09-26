---
name: living-architecture
description: Use to set up or maintain the living-architecture layer (LikeC4 structure model + arc42 principles + model-truth import enforcement + cross-check) in a repo that uses the /la:spec + OpenSpec flow. Sibling of /la:spec — OpenSpec owns per-capability behaviour; this owns cross-cutting structure. Dispatches to init (scaffold) or maintenance; carving a boundary is the arch-slice skill.
---

**Preflight:** run `la-doctor --expect 0.1.1` once per session before using any `la-*` or `dr-*` command; if it fails, stop and show the user its output.

# Living architecture

Four layers, one node id everywhere. Behaviour lives in OpenSpec; everything
cross-cutting lives here:

| Layer | Question | Artifact | Property |
|---|---|---|---|
| Behaviour | what does it do, now? | `openspec/specs/<id>/spec.md` | living, merged by OpenSpec |
| Structure | how is it arranged, now? | LikeC4 model + views | living; ONE model, diagrams are projected views |
| Rationale | why is it this way, and what must all code here obey? | arc42 file per node | living, edited in place |
| Enforcement | is the code actually like this? | `arch_check` model-truth (the one import law) + LikeC4 model validation, run in the flow gates | executable, blocking |

**History is NOT a layer here.** The openspec archive (per-change design +
deltas, dated, immutable) plus git history IS the decision trail. Never create
ADR files or append-only decision logs (they are merge hell). "Why it is like
this now" belongs in the node's arc42, present tense; "how we got here" is the
archive.

## Alignment rules

- **arc42 = LikeC4 = module structure align perfectly.** A *precise* node's id
  is its LikeC4 element id, its arc42 filename, and its package name — the same
  string.
- **OpenSpec is looser.** A spec either belongs to one node (listed in that
  node's `specs:` — the node is then a behaviour *leaf*) or is
  **cross-cutting** (listed once at top level with the nodes it touches).
  Never duplicate a spec across nodes; `arch_check` enforces exactly-once.
- **Model depth is a dial, not an obligation.** Model precisely where you are
  actively enforcing boundaries; sweep the rest into a few *virtual bucket
  nodes* (tagged `#virtual`, claiming several packages, no alignment claim,
  governed only at bucket granularity — no children, no child-level arrows).
  Deepen a bucket into precise nodes the first time real
  work touches it. Never model deeper than you're willing to keep true.

## File layout — the tree is virtual

Each tool keeps its native layout; shared node ids + `index.yaml` join them.

```
repo/
  openspec/specs/<spec-id>/spec.md
  architecture/
    model/<subsystem>.c4             # ONE LikeC4 model, split across files
    views.c4                         # one view per precise internal node
    index.yaml                       # the cross-walk (below)
    system.arc42.md                  # root narrative + global principles
    <node>.arc42.md                  # only where a node earns prose
  living-architecture.yaml           # repo config for the la-* tools (optional)
```

The checker is `la-arch-check` (the one import law + cross-check, run by the
gates); it needs no per-repo code. `la-arch-diagrams` regenerates the embedded
view diagrams.

`index.yaml`:

```yaml
root_package: mypkg                   # required: the top-level package the nodes claim
nodes:
  sql:                                # precise node
    package: mypkg.sql
    children: [render, dialects]      # the import law then applies child-level here
    arc42: architecture/sql.arc42.md  # optional
    specs: [sql-dialects]             # specs owned by THIS node alone
  surfaces:                           # virtual bucket
    virtual: true
    packages: [mypkg.api, mypkg.mcp, mypkg.cli]

legacy_arrows: {baseline: 8}          # exact count of #legacy arrows in the model (ratchet)

cross_cutting_specs:
  queries: {touches: [core, ir, engine, sql]}
  models:  {touches: [core, storage, engine]}
```

## arc42 node file — required shape

arc42-lite, per node, always present tense, updated in place:

1. **Purpose & context** — 3–10 lines.
2. **Building blocks** — pointer to the node's LikeC4 view. Never a duplicate
   drawing, never a prose restatement of the model.
3. **Principles** — numbered rules that ALL code in this node, old and new,
   MUST obey. Each tagged `[enforced: <check|test id>]` or
   `[review]`. Prefer enforced; every `[review]` principle is a standing
   candidate for a new fitness function. Keep them normative and minimal: when
   work strains a principle, first make the code comply; edit one only when it
   genuinely forbids something needed, in the smallest general wording — never
   descriptive text or implementation detail (function names, mechanisms).
4. **Rationale** — why the current shape is right. Where it derives from a
   specific change, link the archived openspec change id — do not restate
   history.

## Enforcement wiring — the one import law

There is no separate import-linter config: the entire import law lives in the
LikeC4 model and is checked by `la-arch-check` (**model-truth**). The
model's relations must exactly match the AST-measured runtime import edges, at
every granularity the model declares:
- a module attributes to its finest declared child, else its node;
- every edge is licensed by its most-specific covering arrow — a declared
  arrow is the only thing that permits an import, and silence is a ban;
- a measured edge with no covering arrow, a declared arrow with no measured
  edge, and an undeclared edge between two declared children are all findings.

TYPE_CHECKING-only imports are excluded. Grandfathered crossings are dashed
`#legacy` arrows in the model itself (one arrow per real edge, no wildcards);
"layer direction" is just *no upward arrow declared*, and a child boundary is
just *no arrow declared between those children* — so one law subsumes what used
to be separate `layers` / `forbidden` / boundary contracts.

(Other languages: same idea, different tool — dependency-cruiser/Nx for TS,
deptrac for PHP, ArchUnit for JVM — kept honest by a model-truth cross-check.)

**The enforcement bundle** = `la-arch-check` + LikeC4 model validation
(`npx likec4 validate`; if the installed CLI version lacks it, use the lightest
command that parses the model, e.g. `npx likec4 build`) + the repo's type-check
baseline. It runs, blocking, in:
- the **spec-review** gate (that stage runs it in repos with `architecture/`),
- the **arch-slice** move gate,
- CI — `arch_check` is cheap and deterministic, so wire it there once the setup
  has settled (not at init), pinned to a release:
  `uvx --no-build --from living-architecture==<version> la-arch-check` (after
  `astral-sh/setup-uv`, pinned by commit SHA).

**Ratchet rules (hard):**
- `#legacy` arrows may only ever be REMOVED, never added. Wanting to add one
  means the architecture is changing — change the model and arc42 deliberately
  instead, with the user's explicit OK.
- `legacy_arrows.baseline` in `index.yaml` is the exact `#legacy` count;
  `arch_check` fails if the model's count differs, and the baseline is lowered
  as arrows are retired. Progress is monotonic and machine-checked.

**`la-arch-check` verifies, from `index.yaml`:**
- every precise node's `package` (and every bucket's `packages`) exists on
  disk; every declared `child` resolves under its node's package and does not
  collide with another node's package/claim; every `arc42` path exists;
- every top-level package of `root_package` is claimed by exactly one node —
  no orphan packages, no phantom nodes;
- every precise node and declared child is an element in `architecture/model/`;
- every directory under `openspec/specs/` appears exactly once: in exactly one
  node's `specs:` or in `cross_cutting_specs:`; every node named in a
  `touches:` list exists;
- model-truth holds at every declared granularity, the `#legacy` count equals
  `legacy_arrows.baseline`, and each mapped doc's embedded view diagram is
  byte-fresh;
- every principle item in an arc42 file carries a status tag —
  `[enforced: arch_check:<check-id>]`, `[enforced: test:<path>]`, `[review]`,
  or `[target: <issue key>]` (a future-state clause; keys must match the
  repo's `issue_key_pattern`).

## Dispatch

- `architecture/` absent or invalid → run **Init** below.
- Present → maintenance: keep the model, `index.yaml`, and arc42 in sync IN
  THE SAME PR as any structural change; deepen buckets / add views for new
  subsystems; tighten boundaries via the **la:arch-slice** skill.

## Init (one-time per repo)

1. Preconditions: `openspec/` healthy (else run `la:openspec-init` first). Wire a
   type checker against the project venv with a committed baseline if absent
   (basedpyright: `--writebaseline` → `.basedpyright/baseline.json`) — the
   arch-slice move gate needs it. That initial `--writebaseline` is the ONLY
   legitimate re-record: thereafter the baseline is a RATCHET — errors the
   gate surfaces are root-fixed, never re-baselined (per-line
   `pyright: ignore[rule] — <reason>` only for a genuine false positive or
   deliberate wrongness, e.g. an invalid-input test); fixes auto-shrink the
   baseline — commit the shrink, only ever downward.
2. **Measure the AS-IS import graph** between top-level packages (ast-based
   script; separate runtime edges from TYPE_CHECKING-only edges).
3. **Choose the wedge with the user**: which nodes are precise (usually the
   subsystem about to be worked on plus its neighbours), which are buckets.
4. **Model the AS-IS in LikeC4**: precise elements + bucket elements;
   relations = the measured runtime edges. Tag edges slated to die `#legacy`.
   Model truth, not aspiration — the model must be correct at every commit.
5. **The model IS the law** — no separate contracts: declared arrows are the
   allowed imports, silence a ban. Where you want the law enforced child-level,
   declare the node's `children:` in `index.yaml`; grandfather every current
   violation as an exact `#legacy` arrow (no wildcards), and record their count
   as `legacy_arrows.baseline`. The enforcement bundle must be green on the
   scaffold commit.
6. `index.yaml` (`legacy_arrows.baseline`, spec mapping incl.
   `cross_cutting_specs`, the `diagrams` view mapping) +
   `system.arc42.md` (global principles — promote the structural conventions
   already in CLAUDE.md) + node arc42 only for the 1–3 nodes that earn prose
   now.
7. Run `la-arch-check` until green. Do NOT touch CI at init — the spec-review
   and arch-slice gates carry enforcement until the user asks to wire CI.
8. If the repo has a legacy decisions/ADR file: fold its present-tense rules
   into the arc42 principles of the owning nodes, then delete the file
   (history stays in git + the openspec archive). Confirm with the user
   before deleting.

## Interaction with /la:spec

- At spec-plan time, read `architecture/index.yaml` plus the arc42 and view of
  every node the change touches. The plan must state which principles apply,
  and must not violate the model's import law — or must explicitly include the
  model + arc42 change as part of the same change.
- At spec-review time, the enforcement bundle is part of the convergence gate.
- New capability → decide with the user where its spec attaches (one node's
  `specs:`, or `cross_cutting_specs` with a `touches:` list) and record it in
  `index.yaml` in the same change.
- Pure structural refactors (moving code across boundaries) are their own
  changes via **la:arch-slice** — never smuggled into feature PRs.
