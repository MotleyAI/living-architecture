## MODIFIED Requirements

### Requirement: YAML is read with one fixed profile
Every YAML input SHALL be read as YAML 1.1 as PyYAML's safe loader reads it, within a closed tag set:
`yes`/`no`/`on`/`off` are booleans. A scalar the safe loader cannot construct (an impossible date such as
`2024-13-01`, or `!!int`/`!!float` content that is not a number) SHALL be a YAML error, reported like any other
invalid YAML, never a crash.

A mapping that repeats a key SHALL be a YAML error, at any depth, including inside an anchored mapping. Two keys
of one mapping are the same key when their loaded values, normalized (a timestamp to its ISO string), are equal
under these rules: two strings are equal when their code points are; `null` equals only `null`; booleans, integers
and floats compare as exact numbers, `false` and `true` counting as `0` and `1` and `-0.0` as `0`; `.inf` and
`-.inf` equal only themselves; a NaN equals nothing; a string never equals a number or `null`. An alias key counts
as the value it resolves to. A second merge key (a plain `<<` or a `!!merge` node) in one mapping SHALL be a
repeated key too. A key that a merge brings in SHALL NOT count: an explicit key overriding a merged one, and keys
shared by the mappings of one merge, stay as PyYAML merges them. The error SHALL be worded by the shared
`yaml.duplicate-key` template, naming the key (the first occurrence's normalized value, as its canonical repr) and
the 1-based lines where the two occurrences start (an alias key where the alias stands). With several repeats, the
error SHALL name the repeat that comes first in the document, paired with the first occurrence of that key.

The tag set SHALL be `!!str`, `!!int`, `!!float`, `!!bool`, `!!null`, `!!timestamp`, `!!seq`, `!!map` and
`!!merge`, in any spelling (shorthand, verbatim or through a `%TAG` handle); a non-specific `!` on any node SHALL
resolve as if the node were untagged, and on a scalar as if the scalar were plain whatever its style. Any other tag
(`!!binary`, `!!set`, `!!omap`, `!!pairs`, the `!!value` a plain `=` resolves to, a local or unknown tag) SHALL be a YAML error, as SHALL a merge key (a plain `<<` or a `!!merge`
node) anywhere but a mapping key, and a mapping key that is a sequence or mapping, directly or through an alias. An
anchor or alias name SHALL consist of ASCII letters, digits, `-` and `_`, and end at whitespace or one of
``?:,]}%@` ``; any other character there SHALL be a YAML error. A raw NEL (U+0085), U+2028 or U+2029 anywhere in
the input SHALL be a YAML error; the `\N`, `\L` and `\P` escapes in a double-quoted scalar SHALL NOT. Both twins SHALL load every input to the same value or both SHALL report it as a YAML error.

#### Scenario: YAML 1.1 boolean
- **WHEN** the config sets `reviewers: {codex: no}`
- **THEN** the resolved `reviewers.codex` is `false`

#### Scenario: Duplicate key
- **WHEN** a mapping in the config repeats a key
- **THEN** every command that reads it, through either twin, reports invalid YAML in the config naming the key and
  both lines, and exits as for any other YAML error

#### Scenario: Duplicate key at depth
- **WHEN** a YAML input holds `r: {s: {t: 1, t: 2}}`, or an anchored mapping that repeats a key
- **THEN** both twins report the duplicate key `'t'` (or the anchored mapping's key) with both lines

#### Scenario: Keys equal by loaded value
- **WHEN** a mapping holds the keys `a` and `"a"`, `0x1` and `1`, `1` and `1.0`, `1` and `true`, `false` and `0`,
  `~` and `null`, `-0.0` and `0`, `1:30` and `90`, `9007199254740992` and `9007199254740992.0`, `!!int "1"` and
  `1`, or a timestamp and the quoted string of its ISO form
- **THEN** both twins report a duplicate key

#### Scenario: Keys that differ
- **WHEN** a mapping holds the keys `!!str 1` and `1`, two `.nan` keys, `9007199254740993` and
  `9007199254740992.0`, or `.inf` and a large integer
- **THEN** both twins load every key

#### Scenario: Repeated merge key
- **WHEN** a mapping holds two `<<` merge keys
- **THEN** both twins report the duplicate key `'<<'` with both lines

#### Scenario: Merge override is not a duplicate
- **WHEN** a mapping merges `*base` holding `y: 2` and sets `y: 3` itself, or merges two mappings that both hold `x`
- **THEN** both twins load the mapping as PyYAML merges it

#### Scenario: Alias key
- **WHEN** a mapping holds the key `*k`, where `&k s` anchors the scalar `s`, and the key `s`, in either order
- **THEN** both twins report the duplicate key `'s'` with the line of the alias and the line of the other key

#### Scenario: Several repeats
- **WHEN** a mapping holds `a` on lines 1, 2 and 3
- **THEN** both twins report the duplicate key `'a'` at lines 1 and 2

#### Scenario: Unconstructible scalar
- **WHEN** the config holds `2024-13-01` as a plain scalar
- **THEN** every command that reads it reports invalid YAML in the config and exits as for any other YAML error

#### Scenario: Tag outside the closed set
- **WHEN** the config sets `reviewers: !!set {codex}`, or any value tagged `!!binary`, `!!omap` or `!!pairs`
- **THEN** every command that reads it, through either twin, reports invalid YAML in the config and exits as for any
  other YAML error

#### Scenario: Merge key outside a mapping key
- **WHEN** a YAML input holds `<<` as a plain value or sequence item, or a `!!merge` node as a value
- **THEN** both twins report a YAML error

#### Scenario: Quoted or string-tagged merge spelling is a plain key
- **WHEN** a mapping has the key `'<<'` or `!!str <<` with a mapping value
- **THEN** both twins load it as the literal key `<<` and merge nothing

#### Scenario: Collection as a mapping key
- **WHEN** a mapping key is a sequence or mapping, written inline or as an alias of an anchored collection
- **THEN** both twins report a YAML error

#### Scenario: Non-specific tag
- **WHEN** a YAML input holds `! 12`, `! '12'`, `! [1]` or `! {a: 1}`
- **THEN** both twins load the integer `12` (twice), the list `[1]` and the mapping `{a: 1}`

#### Scenario: YAML 1.1 anchor names
- **WHEN** an anchored scalar `&k s` is aliased as a flow mapping key directly followed by a colon (`{*k: a}`)
- **THEN** both twins load the mapping `{s: a}`, and an anchor named `a.b` is a YAML error in both

#### Scenario: Non-ASCII line breaks
- **WHEN** a YAML input contains a raw NEL, U+2028 or U+2029 (as a line break, after an anchor name, or inside a scalar)
- **THEN** both twins report a YAML error, and `"\N\L\P"` loads to those three characters in both

## ADDED Requirements

### Requirement: A duplicate key is reported naming the file, the key and both lines
Every command that reads `living-architecture.yaml`, `living-architecture.local.yaml` or `architecture/index.yaml`
SHALL fail on a duplicate key in it, through either twin, with a message naming the file and carrying the
`yaml.duplicate-key` wording, and SHALL never fall back to defaults or ignore the file:
- a config file SHALL be a config error naming the file, as for any other invalid YAML in it;
- `la-arch-check` SHALL report every YAML error in `architecture/index.yaml` as a setup error naming
  `architecture/index.yaml`, and exit 2;
- `la-arch-diagrams`, `la-arch-scaffold` and the `diagrams-fresh` check SHALL report a duplicate key in
  `index.yaml` with the `c4.index-duplicate-key` wording, and any other YAML error in it as before.

#### Scenario: Duplicate key in the config
- **WHEN** `living-architecture.yaml` sets `conventions:` on two lines and `la-config show` runs
- **THEN** it exits 1, printing a config error naming `living-architecture.yaml`, the key `'conventions'` and both lines

#### Scenario: Duplicate key in the local config
- **WHEN** `living-architecture.local.yaml` repeats a key and `la-config show` runs
- **THEN** it exits 1, printing a config error naming `living-architecture.local.yaml`, the key and both lines

#### Scenario: Duplicate key reported by la-doctor
- **WHEN** `living-architecture.yaml` repeats a key and `la-doctor` runs
- **THEN** its failure line names the file, the key and both lines, and it exits 1

#### Scenario: Duplicate key in the index under la-arch-check
- **WHEN** `architecture/index.yaml` sets `cross_cutting_specs:` on two lines and `la-arch-check` runs
- **THEN** it exits 2, printing `arch_check: architecture/index.yaml: ` followed by the duplicate-key message

#### Scenario: Other invalid YAML in the index under la-arch-check
- **WHEN** `architecture/index.yaml` is not valid YAML and `la-arch-check` runs
- **THEN** it exits 2, printing `arch_check: architecture/index.yaml: ` followed by the parser's wording

#### Scenario: Duplicate key in the index under la-arch-diagrams
- **WHEN** `architecture/index.yaml` repeats a key and `la-arch-diagrams` runs
- **THEN** it exits 1, printing `la-arch-diagrams: index.yaml is not valid YAML: ` followed by the duplicate-key
  message, and rewrites no doc

#### Scenario: Duplicate key in the index under la-arch-scaffold
- **WHEN** `architecture/index.yaml` repeats a key and `la-arch-scaffold` runs
- **THEN** it exits 2 with the duplicate-key message for `index.yaml` and writes nothing
