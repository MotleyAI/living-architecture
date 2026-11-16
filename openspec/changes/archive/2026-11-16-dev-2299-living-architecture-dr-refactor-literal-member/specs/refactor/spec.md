## MODIFIED Requirements

### Requirement: Literal members are renamed where the checker types them
A rename located at a member of a string-literal type (`--symbol Q['value']`, or a locator on that string inside
the type) SHALL take the new value from `--new-name`: any text without a quote character (`'`, `"` or a backtick), a
backslash, `${`, a NUL character or a line break (U+2028 and U+2029 included) (else exit 2 with `refactor.literal-value`); the identifier rule SHALL NOT apply, and each rewritten string SHALL
keep its quote style.

- TypeScript: the rewritten strings SHALL be the language service's rename locations for that string.
- Python: the rename SHALL probe the checker in la's language server, in memory, with the member replaced by a
  sentinel. A string literal exactly OLD SHALL be rewritten when, under the probe, a new diagnostic's range is that
  literal or a list, tuple, set or dict display holding it as an element or key, or when the type the checker gives
  its comparison operand (`==`, `!=`, `is`, `is not`), `in` container or `match` subject contains the sentinel. With the
  member and every such literal set to the sentinel, each diagnostic absent before the probe SHALL be a blind spot,
  `refactor.literal-unresolved`, joining the blind-spot refusal (`--keep` and `--allow-blindspots` apply). Both SHALL
  hold whatever import route carries the member's type to a file.

Every other string literal whose whole value is OLD SHALL be unchanged and listed as a `leftover` with `{where}`
`string`, with or without `--docs`, except one at a position where the checker accepts no other string (TypeScript:
a sentinel string is not assignable to its contextual type; Python: a sentinel in its place draws a diagnostic on it
that was absent before), which is typed by a literal type the rename leaves unchanged and SHALL NOT be listed.

#### Scenario: Python contexts
- **WHEN** `DriftKind = Literal["edit_model", "drop"]` is renamed at `DriftKind['edit_model']` to `edit_master`, and
  the project holds a call `f("edit_model")` with `f(kind: DriftKind)`, `k: DriftKind = "edit_model"`, a return
  of `"edit_model"` from a function returning `DriftKind`, a default `kind: DriftKind = "edit_model"`, `xs:
  list[DriftKind] = ["edit_model"]`, `kind == "edit_model"`, `kind in ("edit_model",)` and `case "edit_model":`
  on a `DriftKind` subject
- **THEN** every one of those strings becomes `"edit_master"`, with its quote style kept

#### Scenario: Unrelated equal strings untouched
- **WHEN** the project also holds `Other = Literal["edit_model", "zzz"]` with `g("edit_model")` for `g(o: Other)`,
  `s: str = "edit_model"` and `choices=["edit_model"]`
- **THEN** none of them changes, the `str` and `choices` strings are listed as `leftover` with and without
  `--docs`, and the `Other` argument is not listed

#### Scenario: Position that accepts any string is listed
- **WHEN** the project also holds `h("edit_model")` for `h(o: Other | str)`, and `g("edit_model")` on a line whose
  argument already has a checker error
- **THEN** both are unchanged and listed as `leftover`

#### Scenario: Exhaustive match does not refuse
- **WHEN** a `match` on a `DriftKind` subject handles every value and ends with `assert_never(kind)`
- **THEN** its `case "edit_model":` is rewritten and no blind spot is reported

#### Scenario: Narrowed local refuses
- **WHEN** a function holds `k = "edit_model"` and later `f(k)`
- **THEN** the call site is a `refactor.literal-unresolved` blind spot and the rename refuses with exit 1

#### Scenario: Derived alias
- **WHEN** `Ext = Literal[DriftKind, "x"]` types an argument `h("edit_model")`
- **THEN** that string is rewritten

#### Scenario: Every import route carries the type
- **WHEN** a Python file reaches the module declaring `DriftKind` only through one of: a chain of re-exports,
  `from m import *`, a relative import, an import under `if TYPE_CHECKING:`, an import inside a function, a `.pyi`
  stub, an `__init__.pyi`, a `<name>-stubs` directory, a namespace package, or a project `__builtins__.pyi`; and
  the file passes `"edit_model"` to a parameter typed `DriftKind`
- **THEN** that string is rewritten in each such file

#### Scenario: Blind spot in a file without the string
- **WHEN** a module holds `DEFAULT: Final = "edit_model"`, and another file that holds no string `"edit_model"`
  and reaches `DriftKind` through any route above passes `DEFAULT` to a parameter typed `DriftKind`
- **THEN** that call site is a `refactor.literal-unresolved` blind spot and the rename refuses with exit 1

#### Scenario: Equal string in a file outside the member's reach
- **WHEN** a file whose imports never reach the module declaring `DriftKind` holds `s: str = "edit_model"`
- **THEN** that string is unchanged and listed as `leftover`

#### Scenario: TypeScript contexts
- **WHEN** `type Kind = 'edit_model' | 'drop'` is renamed at `Kind['edit_model']`, and the project holds a typed
  variable, an argument, `x === 'edit_model'`, a `case`, a typed array element, an equal string in another union,
  a `string` variable and an imported use of `Kind`
- **THEN** the typed variable, argument, comparison, case, array element and imported use change, and the other
  union's string and the `string` variable do not

#### Scenario: Value with a quote refused
- **WHEN** `--new-name` is `it's`
- **THEN** stderr is `refactor.literal-value` and the exit code is 2

## ADDED Requirements

### Requirement: dr-refactor --timings prints each phase's wall time
`dr-refactor --timings` SHALL, for every subcommand and after all other output, print on stderr one
`refactor.timing` line per phase whose work ran at least once, in the order of the shared phase list (`load`,
`resolve`, `references`, `rules`, `blindspot-scan`, `literal-scan`, `literal-probe`, `baseline`, `write`), then one
for `total`. A phase's time SHALL exclude the phases nested in it, and its repeated runs SHALL add up. The seconds
SHALL be the elapsed time floored to whole centiseconds, never negative, written as whole seconds, a dot and two
digits. The lines SHALL be printed on every exit once the arguments parse: success, a refusal or an error. A run
handed to the other language's twin SHALL print only that twin's lines; a run that exits before any phase ran (a
routing or map error, or the other twin missing) SHALL print only `total`. Without `--timings`, stdout, stderr and
the exit code SHALL be unchanged.

#### Scenario: Line format
- **WHEN** a phase took 1.239 seconds and another 0.004 seconds
- **THEN** their lines read `timing: <phase> 1.23s` and `timing: <phase> 0.00s`

#### Scenario: Python Literal rename
- **WHEN** `dr-refactor --timings rename --file m.py --symbol "Kind['a']" --new-name b` runs
- **THEN** stdout is unchanged, and stderr ends with timing lines in list order that include `literal-scan` and
  `literal-probe`, then `total`

#### Scenario: TypeScript rename
- **WHEN** `dr-refactor --timings rename --file src/a.ts --symbol foo --new-name bar` runs
- **THEN** stdout is unchanged, and stderr ends with timing lines in list order, none of them a `literal-` phase,
  then `total`

#### Scenario: Refusal still timed
- **WHEN** a member rename with `--timings` refuses on a blind spot
- **THEN** the exit code is 1, and the timing lines follow the refusal on stderr

#### Scenario: Forwarded run
- **WHEN** the npm twin runs `dr-refactor --timings rename --file m.py --symbol f --new-name g`
- **THEN** stderr holds the Python twin's timing lines once, and no line from the npm twin

#### Scenario: Exit before any phase
- **WHEN** `dr-refactor --timings rename-map map.yaml` runs on a map mixing `.py` and `.ts` entries
- **THEN** the map error is printed, then only the `total` timing line, and the exit code is 2

#### Scenario: Option absent
- **WHEN** any `dr-refactor` case of the corpus runs without `--timings`
- **THEN** its output equals its golden
