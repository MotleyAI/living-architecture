## Context

See proposal.md for the motivation. Today `LiteralRename.prepare` makes every Python project source a candidate;
`RenameMap.compute` opens them all in la's language server, and `LiteralRename.rules` pulls every candidate's
diagnostics before the probe (`before`), then runs three rounds: typed (member set to the sentinel, `reveal_type`
wraps; pulls the files holding an equal string), verify (member and typed sites set to the sentinel; pulls every
candidate) and others (each remaining equal string set to the sentinel; pulls their files).

Measured on SLayer DEV-1607 (`Literal["edit_model"]`, 1601 files, this machine): 89 s total; `before` 44 s, verify
26 s, the equal-string scan 8.4 s, typed 5 s, others 4 s. A prototype with the closure alone gave 75 s; with the
closure and the lazy `before` 52 s, byte-identical output, 4 `before` pulls.

Applicable principles (`architecture/system.arc42.md`): 1 (twins; `--timings` in both, the probe is Python-only since
the TypeScript twin uses the language service's rename locations), 2 (option, phase list and line template come from
`shared/`), 3 (the import closure lives in Python `lang`, the timers in each twin's `refactor`; the `refactor -> lang`
arrow exists in both twins, so the model is unchanged), 4 (unaffected). No arc42 edit. The spec delta modifies the
existing `refactor` spec, owned by element `refactor`.

## Goals / Non-Goals

**Goals:**
- The probe asks the checker only about files whose diagnostics it can change or whose strings it classifies, with
  output byte-identical to today on every input.
- `--timings` attributes a run's wall time to shared phases in both twins.

**Non-Goals:**
- No release or version bump in this change.
- No change to TypeScript `Literal` renames or to Python symbol-rename candidates.
- No exact checker-resolved import graph (see decision 9).

## Decisions

### Probe candidates (Python)

`candidates = closure(member file) ∪ equal-string files`, where the closure is every project file whose imports reach
the member's file, the member's file included. The equal-string scan still parses every project file (escaped
spellings and implicit concatenations are decoded by the parser; leftovers in any file are still listed). The typed
round substitutes and pulls every equal-string file, as today; the verify round pulls every candidate. Files outside
the candidates are neither opened nor pulled.

Constraint (not spec): the candidate set MUST be a conservative superset of the files whose diagnostics the probe can
change. Soundness argument: a file's types can depend on the member only through import statements the checker
resolves (directly or transitively) to the member's module, or through `__builtins__.pyi`, which the checker injects
into every file. The closure follows every `import`/`from … import` statement wherever it sits (module level, under
`TYPE_CHECKING`, conditional, inside functions or classes), read by the parser and, for a file that does not parse,
lexically. It resolves a dotted name by suffix against every project file at any directory depth, so it includes
every file any search root (source roots, `extraPaths`, execution environments, `stubPath`), namespace package or
shadowing order could resolve the name to; both a source and its stub are included. A `<name>-stubs` directory
resolves as `<name>`. Import hooks and `importlib` calls are invisible to the checker as well, so they carry no type.

### Import resolution in `lang/edges.py`

Resolution becomes extension-aware: `.py` and `.pyi` files are graph nodes; both `__init__.py` and `__init__.pyi`
are package initializers; `in_dir` and relative imports find `name.py`, `name.pyi`, `name/__init__.py` and
`name/__init__.pyi`; a directory named `<name>-stubs` contributes suffixes as `<name>`. `from pkg import *` also
reaches every direct submodule of `pkg` (an `__all__` may name one the initializer never imports). A new
`lang` function returns the reverse closure of a file over a given file set, taking each file's already-parsed tree
(or text when it does not parse) so the scan's parse is reused. The graph's node set for the probe is every `.py` and
`.pyi` file under the project outside `excluded_dirs`; only `.py` files can be candidates (the probe never pulls a
stub). `la-affected-tests` passes only `.py` paths, so its output is unchanged.

### Lazy `before`

A file's pre-probe error keys `(code, start, end)` over severities 1 and 2 are pulled on first need and cached. The
rule per pulled file and round: when the round's diagnostics for that file hold any severity-1 or -2 diagnostic,
after the round has reverted every substitution, pull and cache that file's complete original key set, then
classify the round's saved diagnostics against it. A file whose round shows no such diagnostic needs no `before`: a
new error is a diagnostic of the round absent before, and there is none. Reveal results (severity 3) never consult
`before`. Each file is compared only with its own `before`. Every classification (typed, blind spot, unrelated,
leftover) is the same as with an eager `before`, so output is unchanged.

### `--timings`

- A top-level `dr-refactor` option beside `--apply`, so it covers every subcommand; defined in `shared/cli.yaml`
  with the ordered phase list (`timing_phases`); the line is `findings.yaml` template `refactor.timing`:
  `timing: {phase} {seconds}s`.
- Timer: a stack of phases. Entering a phase pauses the one below it; leaving resumes it. A phase's time is its own
  (exclusive) monotonic elapsed time, summed over its runs. `total` is the whole scope. Seconds are floored to whole
  centiseconds from integer nanoseconds (`ns // 10_000_000`), clamped at 0, formatted `S.CC`; both twins format from
  the same integer, so they cannot round differently.
- Scope: opened right after the arguments parse, closed in a top-level `finally` around routing, forwarding, native
  work and error translation, so success, refusals and errors all print. A forwarded run prints nothing of its own
  (the other twin gets the raw arguments, `--timings` included, and prints its lines). An exit before any phase ran
  prints only `total`.
- Phase attribution:
  - `load`: Python, the rope project and la's language server started with the candidates opened; TypeScript, the
    language services and the first build of each program (wherever it happens, exclusive time moves it here).
  - `resolve`: locating each entry (locators, `--symbol`, definitions, convergence).
  - `references`: Python, rope occurrences, change sets of moves, and checker references; TypeScript, rename
    locations and file-move edits.
  - `rules`: the other checker-backed rules (keyed fields, parameters, stand-ins, string members, patch targets,
    mentions, compound names, leftovers).
  - `blindspot-scan`: the member blind-spot scan.
  - `literal-scan`: the equal-string scan and the closure.
  - `literal-probe`: every probe round, lazy `before` pulls included.
  - `baseline`: realigning the type-check baseline (the configured checker runs).
  - `write`: verifying and writing on `--apply`.

### Decisions log

1. Phase list: shared, flat, exclusive times, list order, only phases that ran, then `total`. Options: A shared list;
   B per-twin names with a shared line format; C A plus the probe's rounds. Taken: A, it answers task 12.2 and keeps
   names in the contract. (user)
2. Probe candidates: the reverse import closure of the member's file plus the equal-string files. (default)
3. Lazy `before`: pulled only for a file a round shows an error; strictly better, identical output, 75 s → 52 s.
   (default)
4. Closure soundness extras: `.pyi` stubs, `__builtins__.pyi`, star-import submodules, lexical reading of a file that
   does not parse. (default)
5. The closure reuses the scan's parsed trees instead of re-reading files (about 3 s on SLayer). (default)
6. `--timings` is a top-level option like `--apply`, covering every subcommand. (default)
7. Timings print on every exit once the arguments parse, refusals and errors included. (default)
8. No release in this change; the issue does not ask for one. (default)
9. Rejected (codex): derive the closure from the checker's own resolved imports. The language server exposes no such
   request, so it needs patching basedpyright internals, brittle across versions; the dotted-suffix superset is
   sound by the argument above. The `-stubs` resolution and the soundness argument were folded in. (user)
10. Rejected (codex): an exclusive `checker` phase, or a `checker` overlay line. Checker time stays in the phase that
    asks for it, so `literal-probe` and `blindspot-scan` show where it goes; the twins stay symmetric. (user)
11. The typed round and verify use the whole candidate set (equal-string files outside the closure included), so no
    rewrite depends on the closure's soundness. (codex)
12. `lang/edges.py` resolution becomes extension-aware (`.pyi`, both initializers, relative imports into stubs). (codex)
13. The lazy-`before` rule is stated per file and round, with tests for a pre-existing error on the same span with
    the same and a different code, an error away from the literal, reveal-only results and diagnostics in a
    different file. (codex)
14. Conformance fixtures run the real checker over each import route. (codex)
15. The spec stays semantic: the narrowing and lazy fetch are a design constraint checked by a unit spy, the
    requirement gains only import-route scenarios. (codex)
16. Seconds floored to integer centiseconds from nanoseconds, clamped at 0; unit tests with injected durations in
    both twins, one normalized end-to-end case. (codex)
17. The timing scope wraps routing, forwarding, native work and error translation; forwarded runs print only the
    target twin's lines; tests for a routing refusal, a map error, a baseline checker failure and a missing twin.
    (codex)
18. Every existing `refactor-literal-*` case runs through `scripts/conformance-cross` byte-for-byte as an
    acceptance step. (codex)

## Risks / Trade-offs

- [The closure misses a route the checker follows] → the soundness argument above, the route fixtures under the real
  checker, and decision 11 (rewrites never depend on the closure; only a blind spot in a file with no equal string
  could be missed).
- [`.pyi` recognition changes `la-affected-tests`] → it passes only `.py` paths; its corpus runs unchanged.
- [Timing lines make stderr nondeterministic] → printed only with `--timings`; goldens normalize the numbers.
- [The TypeScript program builds lazily inside other phases] → exclusive time moves each build into `load`.
