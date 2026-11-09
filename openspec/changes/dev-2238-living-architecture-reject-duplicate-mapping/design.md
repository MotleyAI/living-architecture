## Context

The shared YAML profile (`contract/yaml_profile.py` over PyYAML's safe loader; `contract/yaml.ts` over the `yaml`
library with `uniqueKeys: false`) is the only loader of la-owned YAML: both config files, `architecture/index.yaml`
and the vendored `shared/` snapshot. Its readers surface YAML errors in four different ways:

- the config loaders print `<path>: invalid YAML: <detail>`;
- `la-arch-check` prints `arch_check: <detail>`, with no file name;
- the c4 index reader (`la-arch-diagrams`, `la-arch-scaffold`, `diagrams-fresh`) collapses every YAML error to
  `index.yaml is not valid YAML`;
- the npm TypeScript refactor workspace swallows the error (bare `catch`), and `la-arch-migrate` migrates past an
  unusable index.

Probing found two existing twin divergences on this boundary: `{1: a, true: b}` and `{1: a, 1.0: b}` collapse in
Python (dict equality) but keep two entries in the npm twin's `Map`, and two `<<` merge keys in one mapping merge
the last in Python but the first in npm.

Principles that apply (`architecture/system.arc42.md`): 1 (twins identical; the corpus and the shared vectors pin
it), 2 (texts only from the shared contract: two new `findings.yaml` templates), 3 (language-specific code only in
`lang`/`refactor`: the TS workspace change lives in `refactor`). No model or arc42 edit: every import the change
needs already has its arrow (`refactor`/`c4`/`archcheck` -> `contract`). No new capability, so no new spec mapping;
`shared-contract` is cross-cutting, `refactor` and `c4-layout` are owned by their nodes.

## Goals / Non-Goals

**Goals:**
- The bug class (silent last-wins data loss) is impossible in every la-owned file, through one code path per twin.
- Every reader of the config files and the index fails loudly on a duplicate, naming the file, the key and both
  lines.
- The two twin divergences above disappear by construction.

**Non-Goals:**
- The version bump: the contract change makes the next release a minor bump, done by the release PR.
- A format change: a file without duplicates loads exactly as before.
- A dedicated `la-doctor` or `la-arch-check` duplicate finding beside the loader error.
- Making the wording of other YAML errors contract.

## Decisions

The decisions log of the planning interview, each entry tagged with who took it.

1. **Scope: the profile itself.** Every profile caller reads an la-owned file, so "the whole profile" and "only
   la-owned files" coincide; one code path covers the bug class. (default)
2. **Surface: the loader error everywhere**, not a dedicated doctor/arch-check finding: a separate finding would
   leave the data loss in place for every other command, or never fire because the load fails first. The readers
   that hide or misplace YAML detail are fixed so the error reaches the user. (default)
3. **Key identity: the loaded mapping cannot hold both keys.** Keys compare by their normalized loaded value under
   Python equality (`a`≡`"a"`, `0x1`≡`1`≡`1.0`≡`true`, a timestamp ≡ its ISO string), and a second merge key in one
   mapping is a duplicate. Weighed against comparing string keys only, which leaves both twin divergences and
   Python's silent `{1: a, true: b}` collapse in place. (user)
4. **Two `.nan` keys are not duplicates; with three or more occurrences the first repeat in the document is
   reported**, paired with that key's first occurrence (fail fast, one error). (default)
5. **Wording** (user, approved wording):
   - `yaml.duplicate-key: 'duplicate key {key!r} at lines {first} and {second}'`
   - `c4.index-duplicate-key: 'index.yaml is not valid YAML: {error}'`
6. **`la-arch-check` prefixes `architecture/index.yaml: ` to every index YAML error**; other parser wording stays
   non-contract. (default)
7. **The npm TS workspace fails loudly on an existing `index.yaml` that is not UTF-8 or not valid YAML** (duplicate
   -> `c4.index-duplicate-key`, otherwise `c4.index-invalid-yaml`), exiting as `refactor.ts-tsconfig-missing` does.
   Weighed against narrowing to duplicates only, or leaving it out of scope. (user: "They should fail loudly of
   course")
8. **Duplicate keys are invalid, period**: no carve-outs in any reader. (user)
9. **The vector format gains `error: duplicate` with a `message:`** (the rendered template), so key and lines are
   pinned in both twins' vector suites. (default)
10. **`la-arch-migrate` refuses an unusable `index.yaml`** (not UTF-8, not valid YAML, not a mapping) when it
    converts a model, instead of migrating past it: migrating past would move arc42 docs while leaving the index's
    `diagrams` keys stale. `arch-migrate-index-not-utf8` flips from exit 0 to exit 2 with the repo unchanged. (user)
11. **One strict index primitive in `c4`** returns the index text and mapping, or a structured failure; the lenient
    `read_index`/`readIndex` renders the failure, and migrate keeps the text it needs to rewrite `cross_cutting_arc42`
    entries and `diagrams` keys. Migrate's private lenient reader goes. (codex)
12. **Python records each mapping key's start mark while composing** (the mark of the key's first event, so the alias
    token for an alias key), because a composed alias is the anchored node itself and carries the anchor's mark.
    Vectors cover an alias as the first and as the second occurrence. (codex)
13. **Key identity is a contract-level comparator implemented by each twin**, never by `dict`/`Map` membership:
    strings (timestamps as their normalized ISO string) by code points; `null` only with `null`; booleans, integers
    and floats by exact numeric value (`false`/`true` as `0`/`1`, `-0.0` as `0`, an integral float equal to that
    exact integer, so `9007199254740993` ≠ `9007199254740992.0`); `±inf` only with themselves; NaN with nothing;
    merge keys only with each other. JS `Map` treats all NaNs as equal and compares wrapper objects by identity, so
    it cannot serve. (codex)
14. **Both vector runners learn `error: duplicate`**: PyYAML's `safe_load` loads the input, and the profile raises
    the duplicate error with exactly `message`. The one-expectation check stays. (codex)
15. **The vector matrix covers the drift-prone equality boundaries**: `false` vs `0`/`0.0`, `null` spellings, `-0.0`
    vs `0`, sexagesimal vs decimal, integers beyond 2^53 vs floats, explicit and non-specific tags (`!!str 1` ≠ `1`,
    `!!int "1"` ≡ `1`), a timestamp with a timezone vs its normalized ISO string. (codex)
16. **A structured `DuplicateKeyError`** (a subtype of each twin's profile `YAMLError`) carries the normalized key and
    both lines; readers pick `c4.index-duplicate-key` by type, never by parsing the message. (codex)
17. **`arch-migrate-index-not-mapping` is a conformance case** for the new not-a-mapping refusal. (codex)
18. **Keep `index.yaml` (not `architecture/index.yaml`) in `c4.index-duplicate-key`.** rejected (codex): every
    sibling c4 message names `index.yaml`, and there is one index file, so the name is unambiguous; renaming only
    this template breaks the family, renaming all churns their goldens for nothing. (user)

## Risks / Trade-offs

- [The npm `yaml` library's node ranges and PyYAML's marks disagree on where a key starts (anchors, tags, `?`
  explicit keys)] -> the line is defined as where the key's first token stands; vectors pin anchored, tagged and
  alias keys in both twins.
- [Detection order differs from construction order (PyYAML constructs mappings lazily)] -> the check walks the
  composed document in document order, independent of construction order; the "several repeats" and nested vectors
  pin which repeat is reported.
- [Repos with a duplicate key stop loading after the upgrade] -> intended; the message names the file, the key and
  both lines, so the fix is one edit.
- [Turning the TS workspace's silent fallback into an error also affects other invalid-YAML indexes] -> intended
  (decision 7); every other reader already fails on them.
