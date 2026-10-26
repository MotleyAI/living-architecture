## Context

See proposal.md - Why. The Python twin reads YAML with `yaml.safe_load`; its constructors for `binary`, `set`,
`omap` and `pairs` produce bytes, sets and tuples, outside the normalized types (`render.normalize` maps them through
its `str(value)` catch-all, which `render_template` also needs for call-site values such as paths, so it stays). The
npm twin parses with the `yaml` library (`failsafe` schema plus the profile's scalar tags); the library builds its
own values for the YAML 1.1 collection tags, accepts collection keys, treats `!` as `!!str`, lets `!!str <<` merge,
and lexes anchor names as YAML 1.2 does (`:` allowed).

Probe results (current state) that this change makes agree, all pinned by vectors:

| Input | Python | npm |
|---|---|---|
| `!!binary aGk=` / `!!set {a, b}` / `!!omap [{a: 1}]` / `!!pairs [{a: 1}, {a: 2}]` | bytes / set / tuples | mapping / `{}` / mapping / list of mappings |
| verbatim `!<tag:yaml.org,2002:set>`, `%TAG` `!y!omap` | constructed | `{}` / mapping |
| `!!binary aGk`, `!!binary [1]`, `!!set [a]`, `!!timestamp [1]` | error | accepted |
| `x: =` | error | `'='` |
| `x: !!merge a` | error | crash (`symbol`) |
| `x: <<`, `x: [<<]` | error | `'<<'` |
| `{!!str <<: {p: 1}}` | key `'<<'` | merges |
| `! 12` | `12` | `'12'` |
| `{[1]: a}`, `{{a: 1}: b}`, `{? [1]}`, block `? [1]`, alias of a collection as a key | error | accepted |
| `{*k: a}` | `{'s': 'a'}` | error |
| `&a.b`, `&a/b`, `&é`, `&k: s` | error | accepted |
| `a: b\x85c: d`, `x: {a: &k\x85s, b: *k}` | line break | ordinary character / error |

## Goals / Non-Goals

**Goals:**
- One closed tag set and the YAML 1.1 anchor-name lexing, stated once in `shared/README.md`, enforced in both twins.
- Every loaded value is a normalized value (or a timestamp, which normalizes to ISO text).

**Non-Goals:**
- YAML library error wording stays outside the contract (shared-contract: runtime-supplied error detail).
- No other YAML 1.1 vs 1.2 lexing difference is chased beyond what the probes found (the anchor names and the three
  non-ASCII line breaks).

## Decisions

- **Closed tag set, not faithful constructors.** Every refused tag is unused in any config; giving them shared
  values would invent meanings (bytes, unordered sets) or add npm constructors for syntax nobody writes. Refusing
  them makes the class impossible with one rule. Alternative rejected: a pairs-list for `!!omap`/`!!pairs` and a
  representation for sets.
- **`!` follows PyYAML** (resolved as if untagged on every node kind, a scalar as if plain whatever its style), not the YAML spec's "string", because the
  profile is PyYAML's.
- **Vector marker `error: refused`.** An input raw PyYAML constructs but the profile refuses. The Python test that pins
  vectors against raw `yaml.safe_load` asserts it *succeeds* on these, so a refusal cannot be mislabelled; both
  twins' profile tests treat `refused` as a YAML error. `error: true` keeps its meaning.
- **Python: refuse in the constructor table.** `load_yaml` reads through a `SafeLoader` subclass whose `binary`,
  `set`, `omap` and `pairs` constructors raise the undefined-tag error; every other rule already holds in PyYAML.
- **npm: one validation pass in `loadYaml`.** Before `toJS`, one walk over the parsed document rejects a resolved tag
  outside the set, a plain `=`, a merge key outside a key position, and a collection key (dereferencing aliases);
  it resolves `!` as untagged and keeps `!!str <<` a plain key. Anchor names are checked where the library lexes
  them; the exact hook (a lexer-token check or a source check of anchor/alias tokens) is settled in implementation.
  If it needs a parser fork, stop and ask the user.
- **Refuse the non-ASCII line breaks.** PyYAML breaks lines on NEL, U+2028 and U+2029 (NEL becomes `\n`; the other
  two stay in scalar content), while the npm library reads them as content. Matching that would need a lexer-level
  port for characters no config contains, so both twins refuse the raw characters before parsing. Alternative
  rejected: rewriting them in the npm pre-pass, which cannot keep U+2028/U+2029 in scalar content.
- **The vectors are the differential probe.** Every probed input is a vector, and both twins run every vector
  against one expectation, so agreement on every probed input is the vector suite passing in both twins (the
  issue's acceptance). No separate cross-twin harness.

## Risks / Trade-offs

- [The `yaml` library's tag resolution for `!` or merge differs from what the walk assumes] → vectors for each node
  kind and merge spelling fail first; settle the hook against them.
- [A real config uses a refused tag] → it now fails in both twins with invalid YAML; no known config does, and the
  Python twin already failed on a set's type.
