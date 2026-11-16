## REMOVED Requirements

### Requirement: Retarget rewrites references to an alias
**Reason**: Replaced by "Retarget rewrites references to an alias and keeps every name bound": a target the alias's module imports is accepted, and a shim's own uses and its importers are rewritten with the target imported instead of kept.
**Migration**: Run the same `retarget` or map entry; references a shim's re-export bound now name the target, imported from its home. Use `--keep PATH[:LINE]` for a reference that must keep the alias.

## ADDED Requirements

### Requirement: Retarget rewrites references to an alias and keeps every name bound
`dr-refactor retarget --file F --symbol ALIAS --target TARGET` (and a map entry with `retarget`) SHALL rewrite every
reference the rename of ALIAS to TARGET's name would rewrite, every rename rule included, except the edits at
ALIAS's own declarations and at re-export sites; ALIAS SHALL stay declared and unchanged. Checks that the new name is
already used SHALL NOT apply.

TARGET SHALL be a binding in the class body or module scope that declares ALIAS, where an import counts as a binding
(Python `from M import T` or `from M import X as T`; TypeScript `import { T } from 'M'` or `import { X as T } from
'M'`). Where ALIAS is itself declared by a re-export of an imported name (Python `from M import T as ALIAS`;
TypeScript `export { T as ALIAS } from 'M'`, or `import { T as ALIAS } from 'M'` exported as ALIAS), TARGET SHALL
name that imported name `T`. A member ALIAS SHALL have TARGET declared in its own class. Otherwise the retarget SHALL
exit 2 with `refactor.retarget-scope`. TARGET's home SHALL be the module ALIAS's module imports TARGET from, under the
name that module exports it by, or ALIAS's module where TARGET is declared there; the home SHALL NOT be followed
further along a re-export chain. TARGET's identity (its declarations, and the declarations an import of it resolves to
through any re-export chain) SHALL decide whether a name is bound to TARGET.

After the retarget, every rewritten reference SHALL name a binding of TARGET, in the meaning the reference needs (a
TypeScript type or value), on every path that reached ALIAS's binding:
- A bare name SHALL be rewritten to the local name of a binding of TARGET that dominates the statement binding ALIAS
  there; where none exists, the retarget SHALL import TARGET from its home at that statement. A bare name at which
  TARGET's written name is bound to something else SHALL refuse with `refactor.retarget-shadowed`, exit 1.
- An import of ALIAS from a module M (`from M import ALIAS [as Z]`, `import { ALIAS [as Z] } from 'M'`) SHALL become
  an import of TARGET from M, keeping `as Z`, where M exports TARGET (Python: declares it, lists it in `__all__`, or
  imports it `as` its own name; TypeScript: M's exports hold it); otherwise ALIAS SHALL leave that import and TARGET
  SHALL be imported from its home.
- A module attribute `MOD.ALIAS` (Python `import pkg.mod` or `from pkg import mod`; a TypeScript namespace import)
  SHALL be rewritten where MOD binds TARGET's name to TARGET at module level; otherwise it SHALL refuse with
  `refactor.retarget-unbound`, exit 1.

An added import of TARGET SHALL sit in the block of the statement binding ALIAS, joining that block's import from the
home when it precedes that statement, else replacing ALIAS's import in place when ALIAS was its only name, else as a
new statement right after it. Its module SHALL be spelled as the import it replaces or follows spells its own:
absolute or relative (Python), and in the same extension style (TypeScript), a package's module name for a Python
package; a TypeScript import of only type uses SHALL be type-only. One block SHALL get at most one import from one home,
however many entries of a map need it. An import of ALIAS SHALL stay while a reference it binds keeps ALIAS. Where
the rewrite would make an import of TARGET a duplicate of another import of TARGET in its block, the later of the two
SHALL be removed, so the module keeps its first import's place. A retarget whose TARGET another map entry renames SHALL
write and import TARGET's new name.

A re-export site SHALL stay unchanged: the `__all__` string naming ALIAS (`__all__` set by a plain, annotated or
augmented assignment, or by `.append` or `.extend`) and the module's import of ALIAS it re-exports; a TypeScript
`export { ALIAS }`, `export type { ALIAS }` or `export { ALIAS } from`, and the import it exports. Every other
reference in a re-exporting module, and every reference in a module importing ALIAS through it, SHALL follow the rules
above.

A member ALIAS SHALL refuse, exit 1 with one `refactor.retarget-override` line per site, while a class of its
hierarchy other than ALIAS's own declares ALIAS's name. A `refactor.retarget-shadowed` or `refactor.retarget-unbound`
refusal on a line `--keep` covers SHALL NOT block the retarget, and an import of TARGET serving only kept references
SHALL NOT be added.

#### Scenario: Method twin
- **WHEN** `class Engine` declares `save_model` and a deprecated `def save(self, m: Model) -> None: return
  self.save_model(m)`, code calls `engine.save(m)` with `engine: Engine`, and `retarget --symbol Engine.save
  --target Engine.save_model` runs
- **THEN** the call becomes `engine.save_model(m)` and `Engine.save` is unchanged

#### Scenario: Class twin and its imports
- **WHEN** `models.py` declares `AcmeModel = Model` and a module holds `from pkg.models import Model,
  AcmeModel` and uses `AcmeModel()`
- **THEN** after retargeting `AcmeModel` to `Model` the import is `from pkg.models import Model` and the use is
  `Model()`

#### Scenario: Imported target
- **WHEN** `compat.py` holds `from pkg.core import Model` and `AcmeModel = Model` with `__all__ = ["AcmeModel"]`,
  `use.py` holds `from pkg.compat import CONST, AcmeModel` and uses `AcmeModel()`, and `AcmeModel` is retargeted to
  `Model`
- **THEN** `compat.py` is unchanged, `use.py` holds `from pkg.compat import CONST` and `from pkg.core import Model` on
  the next line, and the use is `Model()`, in both languages

#### Scenario: Several aliases share one home import
- **WHEN** a map retargets `FlightCatalog` to `FacadeCatalog` and `FlightSchema` to `FacadeSchema`, both imported by
  the alias module from `pkg.facade`, and a module imports both aliases in one statement
- **THEN** that module gains one import from `pkg.facade` naming both targets

#### Scenario: Re-export form
- **WHEN** `compat.py` holds `from pkg.core import Model as AcmeModel` and `__all__ = ["AcmeModel"]`, and
  `retarget --symbol AcmeModel --target Model` runs
- **THEN** every module importing `AcmeModel` from `pkg.compat` imports `Model` from `pkg.core` instead, and
  `compat.py` is unchanged

#### Scenario: Other scope refused
- **WHEN** `class Engine` declares a deprecated `save` and `retarget --symbol Engine.save --target Store.save_model`
  runs
- **THEN** stderr is `refactor.retarget-scope` and the exit code is 2

#### Scenario: Overridden alias refused
- **WHEN** a subclass of `Engine` overrides `save`
- **THEN** stderr names that override with `refactor.retarget-override`, the exit code is 1 and nothing changes

#### Scenario: Shadowed target refused
- **WHEN** a function binds a local `Model` and uses `AcmeModel()` in its body
- **THEN** stderr names that use with `refactor.retarget-shadowed` and the exit code is 1

#### Scenario: Kept refusal does not block
- **WHEN** the shadowed use is on a line `--keep` names
- **THEN** that line is unchanged, every other reference is rewritten and the exit code is 0

#### Scenario: Re-export shim kept
- **WHEN** `compat.py` holds `from pkg.models import Model, AcmeModel` and `__all__ = ["Model", "AcmeModel"]`, and
  `AcmeModel` is retargeted to `Model`
- **THEN** `compat.py` is unchanged and a module's `from pkg.compat import AcmeModel` becomes `from pkg.compat import
  Model`, its uses `Model`

#### Scenario: Single-name shim and its importers rewritten
- **WHEN** `compat.py` holds `from pkg.models import AcmeModel`, `__all__ = ["AcmeModel"]` and `def make(): return
  AcmeModel()`, `use.py` imports `AcmeModel` from `pkg.compat`, and `AcmeModel` is retargeted to `Model`
- **THEN** `compat.py` keeps its import of `AcmeModel` and its `__all__`, imports `Model` from `pkg.models` and
  returns `Model()`, and `use.py` imports `Model` from `pkg.models` and uses `Model`

#### Scenario: Star import
- **WHEN** a module holds `from pkg.compat import *` from a single-name shim and uses `AcmeModel()` (TypeScript: it
  imports `AcmeModel` through an `export *` barrel)
- **THEN** the use becomes `Model()` and the module imports `Model` from `pkg.models` right after the star import

#### Scenario: Conditional and type-checking imports
- **WHEN** a module imports `AcmeModel` inside `if TYPE_CHECKING:`, inside `try:`, or inside a function, and uses it
  where that import binds it
- **THEN** `Model` is imported in that same block, and an import of `Model` in another block does not count as
  binding it

#### Scenario: Unbound module attribute refused
- **WHEN** a module holds `import pkg.compat` and uses `pkg.compat.AcmeModel()`, where `pkg.compat` does not bind
  `Model`
- **THEN** stderr names that use with `refactor.retarget-unbound` and the exit code is 1; with `--keep` on its line
  the retarget proceeds and the line is unchanged

#### Scenario: Bound module attribute rewritten
- **WHEN** a module uses `pkg.compat.AcmeModel()` where `pkg.compat` imports `Model`
- **THEN** the use becomes `pkg.compat.Model()`

#### Scenario: TypeScript merged alias
- **WHEN** a TypeScript class declares `/** @deprecated */ get old(): number { return this.value; }` and `value`,
  and `retarget --symbol C.old --target C.value` runs
- **THEN** every `c.old` read becomes `c.value` and the accessor is unchanged

#### Scenario: TypeScript type and value meanings
- **WHEN** `compat.ts` declares `export const Flight = Facade` and `export type Flight = Facade` of an imported
  `Facade`, and one importer uses `Flight` only as a type while another constructs `new Flight()`
- **THEN** the first imports `Facade` type-only and the second as a value, each from the home module
