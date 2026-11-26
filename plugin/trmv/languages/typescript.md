# TypeScript idioms

The skills stay language-neutral; this is what they mean for a TS/JS repo. Concrete facts (globs, suppression
syntax, waiver, baseline file) come from `trmv-config get lang.typescript.<key>`.

## Environment

Tools resolve against the repo's `node_modules` (`npm ci` first); `trmv-doctor` requires `node` and `npx`. The
type checker is `tsc --noEmit` (`commands.typecheck.typescript`); a project whose tsconfig is not at the root
sets e.g. `tsc --noEmit -p web/tsconfig.json`, and a checker that is not tsc-compatible sets `null`.
`architecture/index.yaml`'s `typescript.tsconfig` names the tsconfig the tools load (default: the nearest
`tsconfig.json`); every project it references is loaded with its own options.

## Refactoring

`trmv-refactor` drives the bundled TypeScript language service, one per project of the tsconfig's reference
graph: `rename` renames every reference the service finds (overrides and implementations included, plus the member string of `vi.spyOn` / `jest.spyOn`, `Reflect.*` and
`Object.defineProperty` / `getOwnPropertyDescriptor` on a typed object; comments and other strings only with
`--docs`), `move-symbol` is the "Move to file" refactor into an existing file (re-exports
included), `move-module` moves a file or directory and rewrites its importers. `--no-in-hierarchy` and
`--unsure include` are refused. Run the repo's formatter (prettier, eslint `--fix`) afterwards — moved code
comes out in TypeScript's default formatting.

A member rename refuses while a receiver of the old name is `any` (`--allow-blindspots` overrides) or a class,
interface or type literal outside the hierarchy declares the old name (`--with` / `--without`). A rename of a
string-literal type member (`--symbol Kind['value']`) rewrites every string whose contextual type is that union,
and the literal of a `const` or once-assigned `let` the checker needs it at; it refuses (`literal-unresolved`) where the
edited program would no longer check.
`--apply` keeps `.tsc-baseline.json` aligned: an entry whose message names a renamed symbol follows it.

String-only references no static tool sees: dynamic `import()` of a computed path, `require()` of a computed
path, `vi.mock('path')` / `jest.mock('path')` strings, property access by a key the rename cannot follow to one literal (`obj[name]` with `name` a parameter), an
object literal outside any declared type holding the old key, JSON and config files, and package `exports` maps.

## Compliance fixes (`trmv-compliance`)

- `tsconfig` → enable `strict`, keep `noImplicitAny` on, and set `noImplicitOverride`.
- `explicit-any` → a real type, or `unknown` narrowed where it is used.
- `untyped-def` → annotate the parameter (callbacks typed by context are fine).
- `attr-blindspot` → type the receiver so `x.NAME` resolves.
- `string-blindspot` → type the receiver so `x['NAME']` or `Reflect.get(x, 'NAME')` resolves.
- `mock` → type the double: `vi.fn<typeof real>()` (or give it an implementation), `vi.mock(import('./m'), …)`
  for Vitest or `jest.mock<typeof import('./m')>('./m', …)` for Jest, and build typed test doubles instead of
  `as unknown as T`.
- Overrides carry the `override` modifier (`noImplicitOverride`), so a renamed base method orphans them visibly.

## Imports

`import type` and type-only specifiers never count as architecture edges. Test files, `*.d.ts` and
`node_modules` are invisible to `la-arch-check`.

## Suppressions

A per-line suppression with a reason, `// @ts-expect-error — <reason>`, solves a new type error only when the
checker is wrong or the wrongness is deliberate. The baseline is `.tsc-baseline.json`.
