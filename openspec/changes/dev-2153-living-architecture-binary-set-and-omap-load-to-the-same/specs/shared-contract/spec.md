## MODIFIED Requirements

### Requirement: YAML is read with one fixed profile
Every YAML input SHALL be read as YAML 1.1 as PyYAML's safe loader reads it, within a closed tag set:
`yes`/`no`/`on`/`off` are booleans, and a duplicate mapping key takes the last value. A scalar the safe loader cannot
construct (an impossible date such as `2024-13-01`, or `!!int`/`!!float` content that is not a number) SHALL be a YAML
error, reported like any other invalid YAML, never a crash.

The tag set SHALL be `!!str`, `!!int`, `!!float`, `!!bool`, `!!null`, `!!timestamp`, `!!seq`, `!!map` and
`!!merge`, in any spelling (shorthand, verbatim or through a `%TAG` handle); a non-specific `!` on any node SHALL
resolve as if the node were untagged, and on a scalar as if the scalar were plain whatever its style. Any other tag
(`!!binary`, `!!set`, `!!omap`, `!!pairs`, the `!!value` a plain `=` resolves to, a local or unknown tag) SHALL be a YAML error, as SHALL a merge key (a plain `<<` or a `!!merge`
node) anywhere but a mapping key, and a mapping key that is a sequence or mapping, directly or through an alias. An
anchor or alias name SHALL consist of ASCII letters, digits, `-` and `_`, and end at whitespace or one of
``?:,]}%@` ``; any other character there SHALL be a YAML error. Both twins SHALL load every input to the same value or both SHALL report it as a YAML error.

#### Scenario: YAML 1.1 boolean
- **WHEN** the config sets `reviewers: {codex: no}`
- **THEN** the resolved `reviewers.codex` is `false`

#### Scenario: Duplicate key
- **WHEN** a mapping in the config repeats a key
- **THEN** the last occurrence wins and no error is raised

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
