## Context

The node map has two shapes: `Node` (mapping + `arc42`/`specs` pointers) and `Derived` (a nested element and its unit).
arc42-exists and spec-mapping iterate `nodes`, so nested elements and roots are invisible to them. Docs are named twice
(the `arc42` pointer and the filename convention); orphan detection and enforced-tags each glob
`architecture/*.arc42.md` independently. Views reject non-top-level names and match predicates by top-level ancestor.
Touched nodes: `archcheck`, `c4`, `contract` (`shared/`) in both twins; no node arc42 files exist. Grounding:
`system.arc42.md` principles 1 (twins identical, conformance decides), 2 (texts/schemas only from `shared/`) and 3
(nothing here is language-specific). The existing arrows `archcheck -> c4` and `c4 -> contract` suffice; no model edit.

## Goals / Non-Goals

**Goals:** one canonical element representation so no id-taking check can be node-only; one nomenclature for arc42
docs (the element id); nested selections in views; a deterministic migration of the retired format.

**Non-Goals:** LikeC4-faithful rendering (`include X` as X alone, `.*`/`.**`, drawing the scope element); views
scoped to non-roots; fully qualified names in views or relations; a format version field; rewriting prose links to
moved docs; enforcing that any element has a doc.

## Decisions

1. **Canonical element list.** One record per model element in declaration order (id, parent, language, `specs`,
   and for mapped elements the node/unit data); roots included. Nodes keep `package`/`claims`/`packages`. Every
   ownership/id check reads this list: spec ownership in declaration order, then `cross_cutting_specs` in file order
   (pins `mapped-twice` first/second); `touches` resolves against all element ids. Alternative (keep `Node`/`Derived`
   and add a nested-specs field + a separate id set) rejected: it keeps the two-shape split that caused the bug.
2. **Metadata schema by variety.** `$defs/precise` `{package*, claims, specs}`, `$defs/virtual` `{packages, specs}`,
   new `$defs/element` `{specs}` for roots and nested elements. Per element: syntax problems alone; else
   `arc42-key-retired` first if `arc42` is present, then schema errors of the remaining keys (validated with `arc42`
   removed). `metadata-on-root`/`metadata-on-nested` templates removed. Alternative (spec mapping in `index.yaml`)
   rejected: `index.yaml` carries only repo-wide settings.
3. **arc42 doc named by element id**, `architecture/<id>.arc42.md`, optional; `arc42` key retired. Alternative (keep
   the pointer, flat only) rejected by the user: two nomenclatures for one thing. `system.arc42.md` stays required in
   every repo (a root may also have its own doc); requiring it only with several roots would force a migration and a
   root-count branch everywhere.
4. **Flat docs.** All arc42 docs sit directly in `architecture/` (dotted names give arbitrary depth). Subfolder docs
   are found with the layout check's walk rules and reported; enforced-tags and orphan keep the single top-level glob,
   which is now complete. Findings, not setup errors, like the rest of arc42-exists.
5. **Views, depth relative to the selection.** A selection X (include or predicate anchor) reaches level
   `level(X) + view_depth - 1`; a predicate cuts both endpoints of a matched relation at the anchor's reach. The user
   chose this over an absolute cutoff: the selected element is the visual root. One predicate "X is E or an ancestor
   of E" serves base membership and anchor matching; representatives stay "nearest shown ancestor-or-self". For
   top-level selections this equals today's behaviour, so existing diagrams are unchanged. Names stay root-relative
   only (a strict subset of LikeC4, whose resolution agrees on every accepted name), matching relation endpoints and
   keeping cross-root references inexpressible.
6. **Migration as one more step of the format migration.** The retired key ships in format 0.4.0, the format
   `la-arch-migrate` stamps (DEV-2147, unreleased with this change), so for a repo declaring no `format` the arc42
   conversion runs after the layout conversion and before the stamp; a repo declaring 0.4.0 has nothing to migrate,
   and the retired-key error does not name `la-arch-migrate` (the format check already sends an unversioned repo
   there). Both steps work over one staged result: build
   the full source→target plan (element docs, cross-cutting docs, `diagrams` keys), refuse duplicates/collisions,
   verify the staged result (model parse equal modulo removed keys/blocks, views equal, index equal modulo renames,
   moved docs byte-identical), then commit through the format migration's journal (temp files and renames, modes
   kept, the config replaced last). `model.c4` and `index.yaml` are edited textually (line removal, scalar rename) so every other byte stays;
   verification proves the YAML/model equivalence. Lives in `c4` (it already owns migration, model parsing and index
   reading).
7. **Findings.** `spec-mapping.unknown-node` → `spec-mapping.unknown-element` (id renamed); `unmapped` and `orphan`
   texts say element; removed: `arc42-exists.node-doc-missing`, `arch-check.metadata-on-root`,
   `arch-check.metadata-on-nested`, `c4.include-non-top-level`, `c4.view-includes-non-top-level`; added:
   `arch-check.arc42-key-retired`, `arc42-exists.nested-doc`, `arc42-exists.cross-cutting-not-flat`,
   `arc42-exists.cross-cutting-is-element`, and `arch-migrate` texts for moves and each refusal.
8. **Version 0.4.0** in `python/pyproject.toml`, `node/package.json`, `plugin/.claude-plugin/plugin.json` (breaking:
   the `arc42` key), and format 0.4.0 in `shared/config.yaml`, shared with the declared-format change.

## Finding texts and migrate output (exact)

- `arc42-exists.cross-cutting-not-flat`: `arc42-exists: cross_cutting_arc42 names {doc}, which must sit directly in architecture/`
- `arc42-exists.cross-cutting-is-element`: `arc42-exists: cross_cutting_arc42 names {doc}, the doc of model element {element}`
- `arch-migrate.moved`: `moved {source} to {target}`
- `arch-migrate.source-missing`: `{source} does not exist; nothing written`
- `arch-migrate.source-moved-twice`: `{source} would move to both {first} and {second}; nothing written`
- `arch-migrate.shared-target`: `{first} and {second} would both move to {target}; nothing written`
- `arch-migrate.target-taken`: `{source} cannot move to {target}, which already exists; nothing written`
- `arch-migrate.diagrams-key-taken`: `{source} cannot move to {target}: architecture/index.yaml already has the diagrams key {target}; nothing written`

Refusals print through `arch-migrate.error`. Only the first one is reported. Moves are checked in plan order: element
docs in model order, then `cross_cutting_arc42` entries in file order. For each move the checks run in this order:
source missing, moved twice, shared target, target taken, diagrams key taken.

On success the lines print as:
1. `wrote`, for `architecture/model.c4`, `architecture/views.c4` and `architecture/index.yaml`, each only when written,
   then `living-architecture.yaml`;
2. `moved`, in plan order;
3. `deleted`, in today's order.

A directory that a cross-cutting move leaves empty is kept.

## Approved skill wording (exact; apply verbatim)

**plugin/skills/living-architecture/SKILL.md**
- L10 "Four layers, one node id everywhere." → "Four layers, one element id everywhere."
- L17 "arc42 file per node" → "arc42 file per element that earns prose"
- L23 "belongs in the node's arc42" → "belongs in the element's arc42"
- L28–30 → "- **arc42 = LikeC4 = module structure align perfectly.** An element's fully qualified id is its LikeC4 id
  and names its arc42 file, `architecture/<id>.arc42.md`; a precise element's package is its node's `package` plus
  its path below the node."
- L31–34 → "- **OpenSpec is looser.** A spec either belongs to one element at any depth (listed in that element's
  metadata `specs` — the element is then a behaviour *leaf*) or is **cross-cutting** (listed once in `index.yaml`
  with the fully qualified elements it touches, at any depth). Never duplicate a spec across elements; `arch_check`
  enforces exactly-once."
- Layout tree: `<node>.arc42.md                  # only where a node earns prose` →
  `<element id>.arc42.md            # e.g. python.sql.arc42.md; only where an element earns prose`; after the tree
  add: "Every arc42 file sits directly in `architecture/`, never in a subfolder."
- L69–75: "it carries no metadata" → "it carries no mapping metadata"; "A node declares its mapping in one
  `metadata { }` block:" → "Any element — root, node or nested — MAY list the `specs` it owns in one `metadata { }`
  block; a node also declares its mapping there:"
- Example: delete `arc42 'architecture/sql.arc42.md'    // optional`; after `specs ['sql-dialects']` add the
  comment `// arc42 doc, if any: architecture/python.sql.arc42.md`; replace `render = node 'Render'` with
  `render = node 'Render' { metadata { specs ['sql-render'] } }  // maps to mypkg.sql.render; nested elements may own specs`.
- L117–119 → "Nested elements, at any depth, carry no mapping keys: `<node>.a.b` maps to `<package>.a.b`, and the
  import law applies wherever the model nests. Malformed metadata is a setup error (exit 2) naming the element; a
  model still using the retired `arc42` key converts with `la-arch-migrate`."
- L140–141 → "`views.c4` scopes each view to a root, `view <id> of <root> { ... }`, with include names and predicate
  anchors relative to the root at any depth (`include api.handlers`, `api.handlers -> *`); the root itself is never
  drawn."
- L143 → "## arc42 element file — required shape"; L145 "per node" → "per element"; L150 "ALL code in this node" →
  "ALL code in this element and its descendants".
- L207 → "- every element's metadata matches the shared schema (else exit 2);"
- L211 "every `arc42` path exists;" → "every arc42 file sits directly in `architecture/` and is `system.arc42.md`,
  `<element id>.arc42.md` of a model element, or listed in `cross_cutting_arc42`;"
- L215–216 → "in exactly one element's `specs` or in `cross_cutting_specs:`; every element named in a `touches:` list
  exists;"
- L236–237 → "read `architecture/index.yaml` and the model plus the arc42 file and view of every element the change
  touches and of each of its ancestors."
- L241–242 → "(one element's metadata `specs`, at any depth, or `cross_cutting_specs` in `index.yaml` with a
  `touches:` list)"

**plugin/skills/pr/SKILL.md**
- L119 `architecture/**/*.arc42.md` → `architecture/*.arc42.md`
- L125–127 → "— the arc42 file of each touched element and of each of its ancestors (`architecture/<element
  id>.arc42.md`, where present) AND `system.arc42.md` (cross-cutting principles) — plus the LikeC4 view of every
  touched element"
- L129 "node principles" → "element principles"

**plugin/skills/pr-plan/SKILL.md**
- L21 "which node principles apply" → "which element principles apply"
- L23–25 → "the plan also records where its spec attaches: one element's metadata `specs` (at any depth), or
  `cross_cutting_specs` in `index.yaml` with a `touches:` list."
- L54 `architecture/**/*.arc42.md` → `architecture/*.arc42.md`

**plugin/skills/pr-review/SKILL.md L109, plugin/skills/pr-implement/SKILL.md L32:** `architecture/**/*.arc42.md` →
`architecture/*.arc42.md`

**plugin/skills/arch-init/SKILL.md**
- L54–55 → "Write an element arc42 file (`architecture/<element id>.arc42.md`) only for the 1–3 elements that earn
  prose now."
- L57 "the owning nodes' principles" → "the owning elements' principles"
- L62 "in one node's metadata `specs`" → "in one element's metadata `specs` (at any depth)"

**plugin/skills/arch-cleanup/SKILL.md**
- L24 → "2. **Read the touched elements' arc42 (and their ancestors') + LikeC4 view.**"
- L60–62 "a nested element maps to `<package>.<path>` by convention, with no `index.yaml` entry; views stay
  `of <root>`" → "a nested element maps to `<package>.<path>` by convention and may carry only `specs` metadata;
  views stay `of <root>`; an element whose id changed takes its arc42 file along as `architecture/<new id>.arc42.md`"

## Risks / Trade-offs

- [Textual edits of `model.c4`/`index.yaml` miss an exotic formatting] → verification re-parses and compares; any
  mismatch exits 2 writing nothing.
- [Nested include depth differs from an absolute reading of `view_depth`] → specified with scenarios; top-level views
  byte-identical (existing goldens unchanged).
- [Older `la` on a migrated model rejects nested metadata] → version bump to 0.4.0; skills check the version via
  `la-doctor --plugin`.

## Migration Plan

Adopters (today only this org's repos) run `la-arch-migrate` once after upgrading to 0.4.0; the format check refuses
every other command, naming the migration, until they do. This repo already declares format 0.4.0 and has no `arc42`
keys, nested arc42 docs or `cross_cutting_arc42` entries, so it is in the current format.
