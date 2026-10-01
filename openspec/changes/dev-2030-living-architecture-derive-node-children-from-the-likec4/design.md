## Context

See proposal.md (Why). Today `archcheck` reads `index["nodes"]` in four places (`node_claims`/`check_claims`,
`check_children`, `check_arc42`/`check_spec_mapping`, `unit_to_element` for model-truth and `license()`), and
`check_model_identity` cross-checks those ids against the parsed model. The `c4` parser knows elements, kinds
(`#virtual`) and relations but rejects any other line in an element body. Normative harnesses:
`architecture/system.arc42.md` principles 1 (twins; the corpus decides), 2 (all parameters and texts from
`shared/`), 3 (language-specific code only in `lang`/`refactor`), 4; import law `archcheck → c4, lang, config,
contract`, `c4 → contract`. No arc42 edit is needed.

## Goals / Non-Goals

**Goals:**
- One canonical node/unit map, built once from the parsed model plus `index.yaml`, consumed by every check
  and by `license()`.
- Element nesting and unit nesting are congruent by construction.

**Non-Goals:**
- The multi-language mapping form (DEV-2025). Constraint recorded now: LikeC4 metadata values are strings or
  string arrays, so per-language mappings must be flat string-valued keys (e.g. `package_typescript`); the
  roadmap's `package: {python: …, typescript: …}` shape cannot exist and DEV-2025 decides the replacement.
- Translating validator-library wording into registry templates (see D5).
- Supporting LikeC4 element properties other than `metadata` (description, technology, link, style).
- A migration command.

## Decisions

### D1 — Metadata is parsed by `c4`, interpreted by `archcheck`
`c4` reads a `metadata { }` block into `Element.metadata: dict[str, str | list[str]]` with no knowledge of keys;
`archcheck` validates and interprets it. The parser treats `metadata {` inside an element body as an explicit
state that consumes through its matching `}`, so metadata never touches the parent stack and its lines never
produce `c4.unrecognized-model-line`. Malformed metadata (a line outside the subset, an unclosed array, a
repeated key, a second block) becomes one `c4.malformed-metadata` per problem, kept apart from the other
parse findings (`ModelParse.metadata_findings`) so `archcheck` can escalate only those. Alternative —
interpreting keys in `c4` — would put arch-check semantics into the diagram node.

### D2 — Two node schemas chosen by kind
`shared/schema/node.schema.json` holds `$defs/precise` (`package` required, `claims`, `arc42`, `specs`) and
`$defs/virtual` (`packages`, `arc42`, `specs`), both `additionalProperties: false`, string / string-array
types. The builder validates a node's metadata against the def selected by `Element.virtual`; virtual-ness is
never a metadata key. `arc42` is a string only: the old `arc42: null` equals omitting the key.

### D3 — The canonical map
`archcheck` builds, from model + index, the node list (id, virtual, declared units in model order, arc42, specs)
and the derived elements (FQN, unit) for every element under a precise node. Declared units: `package` then
`claims`, or `packages`. Derived unit of `<node>.a.b` = `<package>.a.b`. The unit → element map takes declared
units first-wins in model order (a duplicate is already `claimed-twice`; today the last silently wins), then
derived units. Elements under a virtual node get no unit. `license()` caches this map per repo root as today.

### D4 — Collision candidates
For a derived unit, candidates are the declared units of all nodes except its own node's `package`; derived
units are never candidates (a descendant nests in its ancestor by construction, and a clash with another node's
descendant implies a clash with that node's declared unit). Candidates are scanned in sorted order; the first
overlap (equal, contains, or nested in) is reported — this replaces today's set iteration, which made the
reported unit order-dependent.

### D5 — Setup-error texts
Every metadata problem, collected in model order and joined by `; `, raises `ArchCheckError`. Parse problems
use the `c4.malformed-metadata` text; schema problems use `arch-check.metadata-invalid`
(`'model element {element}: {error}'`) with the validator's message; metadata on a nested element uses
`arch-check.metadata-on-nested`. Validator-library wording is not translated: conformance pins element and key
with `contains`, as config validation already is (user decision: keep it simple). The `nodes:` rejection is
the ordinary index-schema error.

### D6 — Conformance migration preserves goldens
Fixtures and cases move `nodes:` into model metadata mechanically; a case whose `index.yaml` overlay varied a
node gets a model overlay instead. Every golden outside the deliberately changed list in tasks.md must stay
byte-identical — that is the regression proof for the migration.

## Risks / Trade-offs

- [The metadata subset rejects valid LikeC4 (double quotes, escapes, trailing comma)] → a setup error names the
  element; the subset is documented in the skill.
- [Our subset might not be valid LikeC4] → run `npx likec4 validate` once at implement time on this repo's model
  and on the migrated `arch-ok` fixture (manual; needs network).
- [Raw validator wording differs between twins] → pinned only with `contains` (element + key), accepted.
- [Target repos break on upgrade] → exit 2 names `nodes`; the skill's migration procedure plus `la-arch-check`
  as oracle; only a couple of repos use it.

## Migration Plan

Per target repo: move each `nodes.<id>` entry into a `metadata { }` block on element `<id>` (`package`,
`claims`, `packages`, `arc42`, `specs`); drop `children:` and `virtual:` (the model already says both); delete
`nodes:`; run `la-arch-check` until clean.
