## ADDED Requirements

### Requirement: Renames keep every reference's binding
A `rename`, and every `new_name` entry of a `rename-map`, SHALL be refused when the edits it would write change which
declaration a name resolves to. The check SHALL cover every identifier spelled with the old or the new name, in every
source file of the project, that the language resolves by scope: in TypeScript bare references, declaration names,
import and export specifiers' names (the imported and re-exported names included), shorthand property values and
type references, each resolved with the meaning (value, type or namespace) its position requires; in Python every name read and every binding (`def`,
`class`, parameters, import aliases, `global` and `nonlocal`, `except`, `match`, `for`, `with`, comprehension and
walrus targets, type parameters), names bound by a star import of a project module (its `__all__` when that is a
literal list or tuple, else its module-level names not starting with `_`), and the forward-reference strings the
rename rewrites, each read in its enclosing scope. Edits in comments, docstrings, prose files, string members,
`Literal` values, dictionary keys and call keywords SHALL NOT take part. After the edits:
- every rewritten occurrence SHALL resolve to the declaration it resolved to before, under its new name;
- every other occurrence SHALL resolve to the declaration it resolved to before, a language builtin or global
  included;
- no renamed declaration SHALL share, under its new name, a scope and a meaning with another declaration;
- an occurrence left by `--keep` MAY resolve to nothing, and SHALL NOT resolve to a declaration other than its own.

A refused rename SHALL print the `refactor.name-conflict` finding with the new name and the first site, in the
original code, by project-relative path and then character offset, among: an existing declaration of the new name
that a rewritten occurrence or a renamed declaration would meet; an existing occurrence whose declaration would
change; the declaration a kept occurrence would resolve to; and, when renamed declarations of two entries would meet,
the earlier entry's first declaration. It SHALL write nothing and exit 1. Name conflicts SHALL be checked after
`--keep` is applied and before the blind-spot and stand-in refusal. A rename to the old name SHALL succeed as a rename
with no edits.

#### Scenario: Reference captured by an inner binding
- **WHEN** `old` is renamed to `next` in a module holding `old = 1` (TypeScript `export const old = 1`) and a function
  that binds a local `next` and returns `old + next`
- **THEN** stderr is the `refactor.name-conflict` finding naming `next` and the line of the local `next`, the exit
  code is 1 and no file changes

#### Scenario: Name the declaring scope already binds
- **WHEN** a module-level `old` is renamed to `f` and the module defines a function `f`
- **THEN** the rename is refused naming the line of `f`

#### Scenario: Outer reference shadowed by the renamed declaration
- **WHEN** a module binds `nxt = 5` and a function binds a local `old2` and returns `old2 + nxt`, and `old2` is
  renamed to `nxt`
- **THEN** the rename is refused naming the line of the function's read of `nxt`

#### Scenario: Builtin shadowed
- **WHEN** a module-level `old` is renamed to `len` (TypeScript `parseInt`) and a function of the module calls `len`
  (`parseInt`)
- **THEN** the rename is refused naming the line of that call

#### Scenario: Importer already binds the new name
- **WHEN** `old` in `m` is renamed to `next` and another module imports `old` from `m` directly and binds its own
  `next`
- **THEN** the rename is refused naming the line of the importer's `next`

#### Scenario: Re-export boundary in TypeScript
- **WHEN** `src/index.ts` re-exports `old` from `./m`, `src/use.ts` imports `old` from `./index` and binds its own
  `next`, and `old` in `src/m.ts` is renamed to `next` in a project where nothing else captures it
- **THEN** the re-export becomes `export { next as old }`, `src/use.ts` is unchanged and the exit code is 0

#### Scenario: Aliased import in TypeScript
- **WHEN** `src/m.ts` re-exports `./other` (which exports `next`) with `export *` and declares `old`, `src/use.ts`
  imports `next as n` from `./m`, and `old` is renamed to `next`
- **THEN** the rename is refused naming the line of `src/use.ts`'s import

#### Scenario: Re-export and star-import chains
- **WHEN** `old` in `a` reaches a module through two re-exports (Python: two star imports) and that module binds
  `next` and reads `old`
- **THEN** the rename to `next` is refused naming the first site the chain's last module would change

#### Scenario: Type and value meanings in TypeScript
- **WHEN** a constant `old` is renamed to `next` in a module declaring `type next = string`, and the module uses
  `next` only as a type and `old` only as a value
- **THEN** the rename proceeds and exits 0

#### Scenario: Declaration merging in TypeScript
- **WHEN** an interface `Old` is renamed to `Next` in a module declaring a class `Next`
- **THEN** the rename is refused naming the line of the class

#### Scenario: Overloads renamed as one
- **WHEN** a TypeScript function with two overload signatures and its implementation, or a Python function with an
  `@overload` group, is renamed to a free name
- **THEN** every declaration of the group is renamed and the exit code is 0

#### Scenario: Python scope rules
- **WHEN** a method binds a local named like a class-body attribute, a comprehension's first iterable reads an outer
  name, a walrus in a comprehension binds in the enclosing function, and functions declare `global` and `nonlocal`
  names, and renames to and from those names run
- **THEN** each rename is refused exactly when a name read by the code would resolve to another declaration, as
  Python itself resolves it

#### Scenario: Python class body reads before binding
- **WHEN** a class body reads `old` and binds `next` only after the read, and the module-level `old` is renamed to
  `next`
- **THEN** the rename proceeds and exits 0; it is refused when a binding of `next` may run before the read (earlier
  in the body, conditionally or not, or in a loop holding the read)

#### Scenario: Forward-reference string captured
- **WHEN** class `Old` is renamed to `Next` and a function that binds a local `Next` annotates a local with `"Old"`
- **THEN** the rename is refused naming the line of the local `Next`

#### Scenario: Kept site rebinding
- **WHEN** `--keep` leaves a reference to the inner `old` of a function, and an outer `old` exists
- **THEN** the rename is refused naming the line of the outer `old`

#### Scenario: Kept site dangling
- **WHEN** `--keep` leaves a reference to `old` and no other `old` is in reach
- **THEN** the rename proceeds, that reference is unchanged and the exit code is 0

#### Scenario: Kept declaration
- **WHEN** `--keep` leaves the declaration of `old` while its references are rewritten
- **THEN** the rename is refused naming the first rewritten reference

#### Scenario: No false conflict
- **WHEN** the new name is used only as an attribute (`o.next`), as a call keyword, in a comment, or as a local of an
  unrelated function, and a nested function binds its own `next` without reading `old`
- **THEN** the rename proceeds and exits 0

#### Scenario: Docs and literal members keep their own rules
- **WHEN** a rename with `--docs` rewrites a comment mentioning `old` beside a local `next`, and a `Literal` member
  rename writes a value equal to a local's name
- **THEN** neither edit counts as a conflict

### Requirement: Member renames refuse a name the member's namespace holds
A rename of a member (a method, property, field, accessor, enum member, class-body attribute, and in Python an
attribute assigned through `self` in a method of the class) SHALL be refused when a member of the new name that the
rename does not itself rename (its hierarchy, overload group and `--with` stand-ins) is declared on the same side by
a type holding a renamed declaration (a class, interface, type literal, enum or object literal), by any of its
ancestors (in the project or a library, the implicit root included) or by any of its descendants in the project. In
TypeScript the instance and static sides SHALL be separate and the root SHALL be `Object`'s apparent members; in
Python a class SHALL have one namespace, ancestors SHALL be its whole MRO and the root's members SHALL be those
`shared/languages.yaml` lists. Members added from outside the class or by `setattr` SHALL NOT count. The finding
SHALL be `refactor.name-conflict` naming the existing member's site, or the renamed declaration's own site when that
member is declared outside the project; it SHALL write nothing and exit 1.

#### Scenario: The class already declares the new name
- **WHEN** method `C.old` is renamed to `next` and `C` declares a method `next`
- **THEN** stderr is the `refactor.name-conflict` finding naming the line of `C.next`, the exit code is 1 and no
  file changes

#### Scenario: An ancestor or a descendant declares the new name
- **WHEN** `C.old` is renamed to `next` and, in one project, a base of `C` declares `next`, and in another a subclass
  of `C` does
- **THEN** each rename is refused naming that member's line

#### Scenario: A library base declares the new name
- **WHEN** `C.old` of `class C(dict)` (TypeScript `class C extends Array<number>`) is renamed to `keys` (`map`)
- **THEN** the rename is refused naming the line of `C.old`

#### Scenario: The implicit root declares the new name
- **WHEN** `C.old` is renamed to `__repr__` (TypeScript `toString`)
- **THEN** the rename is refused naming the line of `C.old`

#### Scenario: Static and instance sides in TypeScript
- **WHEN** instance method `C.old` is renamed to the name of a static method of `C`
- **THEN** the rename proceeds and exits 0

#### Scenario: One Python class namespace
- **WHEN** `C.old` is renamed to `next` and `C` assigns `self.next` in `__init__`, and in another project `C` declares
  a `classmethod` `next`
- **THEN** each rename is refused naming that member's line

#### Scenario: The renamed hierarchy is no conflict
- **WHEN** `Base.old` is renamed to `next`, `Sub(Base)` overrides `old`, an interface method `I.old` is renamed with
  its implementation `C.old`, and a class inherits `old` from two bases that both declare it
- **THEN** each rename proceeds and exits 0

#### Scenario: Two map entries meeting on one member name
- **WHEN** a map renames TypeScript parameter property `C.a` and field `C.b` both to `x`
- **THEN** the map is refused naming the line of `C.a`

## MODIFIED Requirements

### Requirement: Rename maps apply many renames as one
`dr-refactor rename-map MAP` SHALL read MAP (a path relative to the working directory) as a YAML list of entries
valid against the shared rename-map schema: `file` relative to `--project`, exactly one locator (`symbol`, `line`
with an optional `col`, or `offset`), and exactly one of `new_name` or `retarget` (a `symbol` in the same file). An
invalid map SHALL exit 2 with `refactor.map-invalid` naming the entry index. It SHALL take `rename`'s options other
than the locator and `--new-name`, applying to every entry. All entries SHALL be of one language, else exit 2 with
`refactor.map-mixed-languages`; the map runs in that language's twin.

Every locator SHALL be resolved against the code before any entry is computed, so entries name old names. Two
entries resolving to one symbol with the same intent SHALL merge; with different intents they SHALL exit 2 with
`refactor.map-duplicate` naming both entry indexes. Every entry SHALL then be computed on one snapshot of the
project, every rename rule running once over the union of the entries' symbols, with one blind-spot scan for every
member entry's old name and one combined refusal report, sorted as a single rename sorts it. Identical edits SHALL
merge; two entries rewriting one span differently SHALL exit 1 with `refactor.map-conflict` naming the site and
both entries, writing nothing. Name conflicts SHALL be checked first for each `new_name` entry alone against the code
before the map, in map order, so a swap or a chain of names inside one scope is refused, and then for all entries'
edits together, so entries that meet on one name or capture each other's references are refused. A retarget entry's
rewritten references SHALL resolve to its target, which another entry may rename. A retarget entry whose target
another entry renames SHALL write the target's new name.

`rename` SHALL behave as a one-entry map with a `new_name`, and `retarget` as a one-entry map with a `retarget`;
their output SHALL equal that map's byte for byte.

#### Scenario: Related renames in one pass
- **WHEN** a map renames `StorageBackend.get_model`, `StorageBackend.get_model_sync` and
  `StorageBackend.get_model(model_name)` and runs with `--apply`
- **THEN** stdout has one header line per entry in map order, one diff per changed file and the applied footer, and
  every reference of the three symbols is renamed

#### Scenario: Entries name old names
- **WHEN** a map renames method `A.old` to `new` and, in a later entry, parameter `A.old(x)` to `y`
- **THEN** both renames apply and the method is `new(self, y)`

#### Scenario: One combined refusal
- **WHEN** two member entries each meet one untyped receiver
- **THEN** stderr lists both blind spots in path, line and column order, followed by one `refactor.blindspots`
  line, the exit code is 1 and nothing changes

#### Scenario: Duplicate entries
- **WHEN** two entries locate the same method with new names `a` and `b`
- **THEN** stderr is `refactor.map-duplicate` naming both entry indexes and the exit code is 2

#### Scenario: Conflicting edits
- **WHEN** one entry renames `Base.save` to `store` and another renames `Sub.save`, its override, to `keep`
- **THEN** stderr is `refactor.map-conflict` naming a shared site and both entries, the exit code is 1 and nothing
  changes

#### Scenario: Swap in one scope refused
- **WHEN** a map renames parameter `f(x)` to `y` and `f(y)` to `x`
- **THEN** the rename refuses with the existing name-conflict finding and nothing changes

#### Scenario: Two entries converging on one name
- **WHEN** a map renames parameter `f(x)` to `z` and `f(y)` to `z`
- **THEN** the rename refuses with the existing name-conflict finding and nothing changes

#### Scenario: Two catch variables taking one name
- **WHEN** a TypeScript map renames the variables of two separate `catch` clauses to `err`
- **THEN** both renames apply and the exit code is 0

#### Scenario: Entries capturing each other's references
- **WHEN** one entry renames a module-level `a` to `z`, another renames a function's local `b` to `z`, and that
  function reads `a`, so that each entry alone is clean
- **THEN** the map is refused with the name-conflict finding and nothing changes

#### Scenario: Retarget beside a rename
- **WHEN** a map retargets alias `old_alias` to `target` and renames `target` to `renamed`, and a function reading
  `old_alias` binds no `renamed`
- **THEN** both entries apply and the function reads `renamed`

#### Scenario: Mixed languages
- **WHEN** a map holds a `.py` and a `.ts` entry
- **THEN** stderr is `refactor.map-mixed-languages` and the exit code is 2

#### Scenario: Invalid map
- **WHEN** entry 2 carries both `new_name` and `retarget`
- **THEN** stderr is `refactor.map-invalid` naming entry 2 and the exit code is 2

#### Scenario: Single rename equals its map
- **WHEN** `rename --file F --symbol Q --new-name N` and a map holding that one entry run on the same project
- **THEN** their stdout, stderr and exit codes are identical, through either invoking twin

### Requirement: Python parameter renames refuse a name the function already uses
A parameter rename SHALL be refused, as the requirement that renames keep every reference's binding defines, when a
name in the signature or the body of a function of any renamed declaration would resolve to another declaration: a
parameter or local of the new name, a read of a global or enclosing name of the new name, or a nested scope reading
the renamed parameter while binding the new name. `dr-refactor` SHALL then print the `refactor.name-conflict` finding
naming the first such site by project-relative path and then by character offset, with its file and line, write
nothing and exit 1. Attribute names (`x.new`), keywords of calls to other functions and a nested scope that binds the
new name without reading the renamed parameter SHALL NOT count. A rename to the old name SHALL succeed as a rename
with no edits.

#### Scenario: Duplicate parameter
- **WHEN** `def g(*, model_name: str, dataset_name: str) -> str` has `model_name` renamed to `dataset_name`
- **THEN** stderr is the `refactor.name-conflict` finding naming `dataset_name`, the file and the line of `g`'s
  `dataset_name` parameter, the exit code is 1 and no file changes

#### Scenario: Body reads a global of the new name
- **WHEN** the module defines `dataset_name = "d"`, and `def h(*, model_name: str) -> str: return dataset_name +
  model_name` has `model_name` renamed to `dataset_name`
- **THEN** the rename is refused with `refactor.name-conflict` naming the line of the read

#### Scenario: Body assigns a local of the new name
- **WHEN** `def k(*, model_name: str) -> str` assigns `dataset_name = model_name.upper()` and returns it, and
  `model_name` is renamed to `dataset_name`
- **THEN** the rename is refused with `refactor.name-conflict` naming the line of the assignment

#### Scenario: Conflict in an override
- **WHEN** `A.run(self, *, model_name: str)` is clean and its override `B.run` reads a global `dataset_name`, and
  `A.run`'s `model_name` is renamed to `dataset_name`
- **THEN** the rename is refused with `refactor.name-conflict` naming `B.run`'s file and the line of the read

#### Scenario: First conflict is reported
- **WHEN** the base method's body and its override's body in another module each read `dataset_name`, the override's
  body twice, and the rename to `dataset_name` runs
- **THEN** the finding names the conflict in the file whose project-relative path sorts first, and within it the
  earliest by character offset

#### Scenario: Attributes and other calls' keywords are not conflicts
- **WHEN** `def m(*, model_name: str, o: O) -> str` reads `o.dataset_name` and calls `other(dataset_name=1)`, and
  `model_name` is renamed to `dataset_name`
- **THEN** the rename proceeds and those two sites are unchanged

#### Scenario: Nested binding that captures nothing
- **WHEN** `def g(*, model_name: int) -> int` holds a nested `def inner[dataset_name]() -> None: ...` that does not
  read `model_name`, and `model_name` is renamed to `dataset_name`
- **THEN** the rename proceeds and exits 0

#### Scenario: Rename to the same name
- **WHEN** a keyword-only parameter of a method with an override and of a function with an overload group is renamed
  to its own name
- **THEN** each rename exits 0 and no file changes

### Requirement: Python renames include every reference basedpyright resolves
For a Python `rename` of a symbol other than a module, `dr-refactor` SHALL add to rope's edits every reference
basedpyright resolves to each declaration the rename renames: every declaration of the renamed hierarchy by default,
only the located one with `--no-in-hierarchy`. These references SHALL include forward-reference strings (`"X"`,
`Optional["X"]`, `list["X"]`, `"X | None"`), keyword arguments of dataclass and Pydantic fields at calls whose callee
is the owning class, a subclass or a `type[...]` of either, receivers typed by a parameter annotation, an attribute
annotation (`self.x: T` or a class-body `x: T`), a return annotation or inference, `isinstance`-narrowed receivers,
and `super().name(...)` calls. Every added edit SHALL replace exactly the old name, located by source character in
the file's text as read; positions SHALL be correct after non-ASCII and astral characters and with CRLF line endings.
Edits SHALL NOT overlap unless identical; identical edits SHALL be merged. When a file changes between its read and
the write, `dr-refactor` SHALL print the `refactor.file-changed` finding naming that file on stderr, write nothing and
exit 1. A module rename SHALL keep rope's edits, and SHALL be refused with the `refactor.name-conflict` finding when
its package already binds the new name (a module of that name, naming it at line 1; a package of that name, naming its
`__init__.py`, else its first Python file by path, at line 1; or a binding in the package's `__init__.py`, naming its
line) or when rope's edits would change a binding as the requirement that renames keep every reference's binding
defines, writing nothing and exiting 1.

basedpyright SHALL be the version the PyPI twin ships, started from la's own environment, run with la's
pyright#11919 patch, reading the project's own configuration and finding the project's interpreter as basedpyright
does. It SHALL run with its working directory outside the project, without the user site, without bytecode
writing and with neither the working directory nor an inherited `PYTHONPATH` on the interpreter's path, so
no target-repo code runs. A language server
that cannot start, is not patched, fails or exits during the refactor SHALL make `dr-refactor` print the
`refactor.pyright-failed` finding on stderr, write nothing and exit 1; no checker or library message text SHALL be
printed. With or without `--apply`, the language server SHALL create no file in the project.

#### Scenario: Forward-reference strings follow the class
- **WHEN** class `Rec` is renamed to `Recommendation` in a module holding `def make() -> "Rec":` and
  `def opt(a: Optional["Rec"], b: list["Rec"], c: "Rec | None") -> None: ...`
- **THEN** every `Rec` inside those strings becomes `Recommendation`, with the quotes and the rest of each string
  unchanged

#### Scenario: Field keyword arguments follow the field
- **WHEN** field `Model.columns` of a Pydantic model is renamed to `fields`, `Sub` subclasses `Model`, and other
  modules call `Model(columns=[])`, `Sub(columns=[], extra=1)` and `kind(columns=[])` with `kind: type[Model]`
- **THEN** each `columns=` becomes `fields=`

#### Scenario: Dataclass field keyword arguments
- **WHEN** field `D.size` of a standard-library dataclass is renamed and a module calls `D(size=1)`
- **THEN** the keyword becomes the new name

#### Scenario: Annotated and inferred receivers
- **WHEN** method `A.get_model` is renamed and the project calls it through a parameter `a: A`, an attribute
  `self.s: A`, a class-body attribute `store: A`, the return of `def make() -> A`, a local `x = A()` and an
  `isinstance(o, A)`-narrowed `o`
- **THEN** each of those calls is renamed

#### Scenario: super() call in an override
- **WHEN** `A.sync_model` is renamed and `class B(A)` overrides it with a body calling `super().sync_model(x)`
- **THEN** the override's name and the `super()` call are renamed

#### Scenario: Hierarchy follows the flag
- **WHEN** `A.run` is renamed, `B(A)` overrides `run`, and the project calls `a.run()` with `a: A` and `b.run()` with
  `b: B`
- **THEN** by default both declarations and both calls are renamed; with `--no-in-hierarchy` only `A.run`, `a.run()`
  and `super().run()` calls resolving to `A.run` are renamed, and `B.run` and `b.run()` are unchanged

#### Scenario: Positions after astral characters and CRLF
- **WHEN** a module with CRLF line endings and no final newline holds `s = "😀é"; r: "Rec" = make()` and `Rec` is
  renamed
- **THEN** only the name inside the string changes, and the line endings and the missing final newline are kept

#### Scenario: Language server failure
- **WHEN** the language server cannot start or exits during the rename, with or without `--apply`
- **THEN** stderr is the `refactor.pyright-failed` finding, the exit code is 1 and every file of the project is
  unchanged

#### Scenario: No target-repo code runs
- **WHEN** the project's root holds a `sitecustomize.py` that writes a marker file when imported, and a rename runs
- **THEN** the marker file does not exist afterwards

#### Scenario: Dry-run leaves the tree unchanged
- **WHEN** a rename that adds basedpyright references runs without `--apply`
- **THEN** every path under the project is byte-identical before and after, and no new path exists

#### Scenario: Module renamed onto an existing module
- **WHEN** module `pkg/a.py` is renamed to `b`, in one project where `pkg/b.py` exists, in another where a package
  `pkg/b/` exists, and in a third where `pkg/__init__.py` binds `b`
- **THEN** each rename is refused with the name-conflict finding naming `pkg/b.py` line 1, `pkg/b/__init__.py` line
  1 and the binding's line respectively, and nothing changes

#### Scenario: Module rename capturing an importer's name
- **WHEN** module `pkg/a.py` is renamed to `b`, no module `b` exists, and `pkg/use.py` holds `from pkg import a` and
  binds its own `b`
- **THEN** the rename is refused naming the line of `pkg/use.py`'s `b`

#### Scenario: Relative import of a renamed module
- **WHEN** module `pkg/a.py` is renamed to `b` and `pkg/use.py` holds `from . import a` with no `b` of its own
- **THEN** the import becomes `from . import b` and the exit code is 0
