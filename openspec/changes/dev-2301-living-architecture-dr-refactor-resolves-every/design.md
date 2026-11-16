## Context

See proposal.md (Why). Today (`python/src/living_architecture`):

- `lang/language_server.py` runs one patched basedpyright language server (stdio, isolated environment, working
  directory outside the project) and converts LSP UTF-16 positions against the text each file was opened with.
  `lang/pyright_patch.cjs` is a `--require` preload that rewrites basedpyright's bundles as Node compiles them
  (pyright#11919), verified against `shared/languages.yaml` `checker_patch_versions` (`1.40.2`).
- `refactor/rename_map.py` resolves entries with rope (falling back to a short-lived language server's `definition`
  in `_renamer`), then per entry: `prepare` (rope's occurrence search over the candidate files; seeds = rope
  occurrences that are declarations; hierarchy and `--with`/`--without` classification through rope finders),
  `seed` (parameter and overload seeds, keyed class chains via `TypeFacts`), `rules` (a `references` request per
  seed, `keyed.scan`, `MemberScan` string members through text probes, patch targets, blind spots through hover)
  and `finish` (text-only rules). `MemberScan` is shared with `dr-compliance --attr` (`refactor/compliance.py`).
  `refactor/literal_rename.py` probes diagnostics with sentinel substitutions over its candidates.
- The npm twin computes TypeScript refactors with an in-process language service and is not affected.

basedpyright 1.40.2's `pyright-langserver.js` is an unminified webpack bundle: `class CommandController`
(`execute(cmdParams, token)` switch), workspaces reached through `ls.getWorkspaceForFile(uri)` and programs through
`workspace.service.run(program => ...)`, as the bundled commands do; the evaluator is program-owned and valid only
inside that callback.

Principles that apply (`architecture/system.arc42.md`; `python.refactor` and `python.lang` have no arc42 of their
own):
1. Twins — the behaviour is Python-only; the new conformance cases are `adapter` cases, and the shared wording change
   (`refactor.unsure-warning`, `--unsure` help) does not reach TypeScript output (the npm twin refuses
   `--unsure include`).
2. Parameters and texts only from the shared contract — the cache variable, the export's verified versions and the
   changed wording live in `shared/`.
3. Language-specific code only in `lang` and `refactor` — the export preload and the index client live in `lang`, the
   rules in `refactor`.
4. No target-repo code runs — the export runs inside the existing isolated language server; the cache lives outside
   the project.

Spec attachment: `refactor`, owned by `python.refactor`. No model or arc42 edit: `refactor -> lang` and
`lang -> contract` already exist.

## Goals / Non-Goals

**Goals:**
- Symptom: a 158-entry map takes 4 h 39 min. Structural cause: every rule asks the checker its own questions, one
  position at a time, per entry, and two resolvers (rope, basedpyright) feed one edit set that must agree by hand.
  Fix the cause: the checker's answers become one per-run artifact (the occurrence index) that every rule reads, so a
  run's checker cost is one export whatever the number of entries; basedpyright decides every occurrence it resolves,
  and rope resolves only what it leaves unresolved.
- One blind-spot verdict for `dr-refactor` and `dr-compliance --attr`.
- The DEV-1607 map in under 10 minutes with peak memory around one full check.

**Non-Goals:**
- Early fatal checks, all refusals at once and progress reporting (DEV-2302); per-phase timings and reuse of pulled
  diagnostics in `Literal` renames (DEV-2299 beyond its candidate-file part).
- The TypeScript twin.
- An incremental per-file cache (decision 9).
- Switching to an upstream export flag (basedpyright#1909) — when it ships, the hook moves to it and stays only for
  older pinned versions.

## Decisions

1. **The index is exported inside la's language server, not by a separate checker run.** A second preload,
   `lang/pyright_export.cjs` (beside `pyright_patch.cjs`, loaded only by the language server), adds a command
   `la.exportOccurrences` to `CommandController`. Alternative: a CLI `pyright.js` run with a `Checker.check()` hook —
   simplest hook, but a second program next to the language server the `Literal` probes and the entry fallback still
   need (about 2× peak memory), reading the disk instead of the snapshot, and computing every diagnostic for nothing.
   (user)
2. **The command runs inside the program, verified like the #11919 patch.** It resolves every requested file to one
   workspace, runs entirely inside `workspace.service.run`, first makes sure every opened candidate is analysed,
   honours the cancellation token, and reads parse results and the evaluator only through the program. The preload
   records `patched` only when the bundle's version is listed in `shared/languages.yaml` and every anchor it rewrites
   (the constructor and the dispatch branch) matches exactly once; anything else is `unverified`/`mismatch` and the
   server refuses (`refactor.pyright-failed` / `compliance.pyright-failed`). After `initialize`, la invokes the
   command once on an empty request as a self-test; a missing or failing command refuses the same way. Anchor counts
   alone do not prove the command works. (codex)
3. **What the index holds.** For every occurrence of an old name in the candidate files: kind (name, member access,
   keyword argument, dict-literal key, string-member name, dotted patch target, `Literal`-typed string,
   forward-reference string, `__all__` entry, import alias or re-export); the declarations it resolves to (aliases
   followed, every overload) and, in order, every import-alias or re-export binding it passes through on the way;
   each declaration with its class, that class's MRO, unresolved bases and keyed kind (dataclass,
   Pydantic, TypedDict); for an access or a string-member object, the receiver verdict computed by porting
   `member_scan._access_kind` and `object_kind` branch for branch (hover-equivalent type of a name or attribute
   receiver; for any other receiver the member access's type, suppressed when a resolved declaration is itself
   `Unknown`/`Any`; `Unknown` for an unresolved callee; `Unknown` wins over `Any`); for a dict literal or keyword, the
   expected class; for a string-member call, the callee's registry forms; and, flagged, every name/import/alias
   occurrence the checker resolves to no declaration (decision 6). (default; blind-spot port: codex)
4. **Facts about nodes not spelled like an old name are batched into the same request.** The AST-driven rules
   (`keyed.py`'s sinks, bindings and calls, `TypeFacts` queries for callees, annotations and receivers) first collect,
   from the AST alone, every position they will ask about, across all entries; the request carries them and the reply
   answers each (definition, type definition, class facts with MRO and keyed kind). `keyed.py`'s rules stay; only
   their fact source changes. Never one request per node. (default)
5. **String members use batched synthetic probes, as today.** Native evaluation of `obj.NAME` without a member-access
   node would have to reproduce pyright's member binding, descriptors, unions, `super()` and metaclass lookups. So a
   second, fixed round sends each file holding member calls as one probe text (all its calls replaced by
   `(obj).NAME`, as `member_scan.Probe` builds it), exports the probe accesses' declarations and verdicts in one
   request, maps them back through `TextProbe.original`, and restores the files. (codex)
6. **rope resolves only what basedpyright leaves unresolved.** Name, import and alias occurrences the index flags as
   unresolved (no declaration) go to rope in one batch per run: each site's pyname is evaluated once and matched
   against every entry's pyname, and matches join that entry's edits. basedpyright decides every site it resolves.
   Member accesses with an `Unknown`/`Any` receiver are blind spots (and `--unsure include`'s sites), never rope's.
   Alternatives: basedpyright only, refusing unresolved project sites with a new finding (renames that work today
   would refuse in repos with imperfect checker configuration, and telling project from third-party names needs
   heuristics); rope's full search once per old name (~28 s per entry, ~74 min on the target map). (user)
7. **la writes every symbol-rename edit; rope's remaining role is narrow.** rope locates and validates entries
   (`Rename`, `validate_changes`, the canonical key, method/parameter detection), renames modules (unchanged), runs
   `move-*` (unchanged) and resolves decision 6's sites. Routing a span replacement through rope adds nothing, so this
   departs from the issue's "rope only builds the edits". (default)
8. **The Python hierarchy over the checker's MRO, rope's rule kept.** A declaration's roots are the roots of OLD's
   declaration in each direct base of its class that has OLD (as the checker resolves the base), or itself when none
   has; two declarations are in one hierarchy when their roots meet. This is rope's `in_hierarchy` rule, evaluated on
   the checker's class graph; it drives the renamed hierarchy, `--with` expansion, stand-in classification, parameter
   override groups and `--no-in-hierarchy`. The spec's "rope's hierarchy" becomes this definition. (codex)
9. **A whole-run cache.** One entry per project root, keyed by a fingerprint of: every discovered project source
   file's content hash and the file manifest; the checker's effective configuration files; the interpreter's identity
   (path, version) and search paths; a fingerprint of every search-path directory outside the project (site-packages,
   stub paths: each file's path, size and mtime_ns); the basedpyright version and the export preload's hash; and a
   canonical hash of the full request (names, candidate files, batched positions, probe texts). Any difference is a
   full export. The cache lives in `$LA_CACHE_DIR`, else `$XDG_CACHE_HOME/living-architecture` (`~/.cache/…`;
   `%LOCALAPPDATA%\living-architecture\Cache` on Windows), never in the project; it is written atomically
   (temporary file + rename), and a missing, unreadable, corrupt or version-mismatched entry is a miss. The variable's
   name is declared in `shared/languages.yaml`. Alternative: per-file records with import-resolution tracking (failed
   lookups, directory listings) — reuses work after small edits, but a large soundness surface inside the hook where
   an invalidation bug silently gives wrong renames; a full export is already one check. (user)
10. **One run-scoped language-server session, started lazily.** A session object owned by `RenameMap` (and by the
    `--attr` command) spans entry resolution, export, probes, `Literal` probes and cleanup. It starts the server on
    first need, opens every candidate file with its snapshot text before the export, and closes it on every exit
    path. A full cache hit with no `Literal` entry and no rope fallback never starts it; module renames and moves
    never do. `_renamer`'s fallback uses it instead of its own server. (codex)
11. **Coordinates are LSP UTF-16 ranges on the wire.** The export returns LSP ranges against the text each file was
    opened with; only `LanguageServer` converts them to character offsets (as today), and every converted span must
    slice to the expected spelling or the run refuses with `refactor.pyright-failed`. (codex)
12. **Candidate files** are the project's Python sources whose text holds an old name, plus those holding a string
    constant equal to one under any escaped spelling (one AST pass per file per run). `Literal` member renames keep
    DEV-2299's candidates (the strings' files and the member module's reverse import closure): a probe's new
    diagnostic in an importer holding no such string is a blind spot. (default)
13. **Text-only rules read per-run tables.** Mentions, compound names and literal leftovers read tables built once per
    file per run (declared names with spans, string constants, regions), so their per-entry cost is a lookup. (default)
14. **`--unsure include` = the index's `Unknown`/`Any` receivers.** Accesses whose receiver the checker types
    `Unknown`, `Any` or a union holding either are renamed too; blind-spot refusal is unchanged. Alternatives: keep
    rope's search for this option only (a second resolution path kept alive, still ~100 s per entry); refuse it like
    the npm twin (a feature removed). (user)
15. **`dr-compliance --attr` reads the index.** One blind-spot verdict for the rename and `--attr`; `MemberScan`'s
    per-query code goes. (user)
16. **A rename refuses with `refactor.rope-walk` only for modules rope walks** (the entry's module and decision 6's
    sites' modules); walking other modules only to keep a refusal would guard nothing. (default)
17. **Approved wording.** (user, approved wording)
    - `shared/findings.yaml` `refactor.unsure-warning`: "WARNING: --unsure=include also renames occurrences the
      checker cannot resolve; it may rewrite unrelated attributes of the same name."
    - `shared/cli.yaml` `--unsure` help (both commands): "occurrences the checker cannot resolve: skip (default) or
      include (risky; Python only)"
    - `plugin/languages/python.md` line 16: "`dr-refactor` resolves a rename's occurrences with the basedpyright
      bundled with la; rope locates the renamed symbol, renames modules and computes moves."
    - `docs/deterministic-refactoring.md` lines 12–13: "Python resolves a rename's occurrences with the bundled
      basedpyright, and rope locates the symbol, renames modules and computes moves;"
18. **The old path is compared with the new before it is deleted.** During implementation the new resolver is built
    beside the old one; a temporary differential run over every Python refactor conformance fixture and the new edge
    fixtures (rope-only default occurrences, `--no-in-hierarchy` with stand-ins, two `--with` hierarchies sharing a
    reference, property getter/setter groups, inferred `self` attributes, diamonds and mixins, unresolved and external
    bases, protocol structural use versus nominal inheritance, string-member descriptors and mixed unions,
    `refactor-retarget-reexport-form` and `refactor-symbol-import-binding`) compares
    normalized edit and finding sets. Any difference stops the work for the user's call; then the old path is deleted.
    (codex)
19. **Request counts are pinned.** Instrumentation tests assert the exact number of language-server requests for a
    symbol-only map (constant in entries and occurrences), a map with a rope-fallback entry, and maps with several
    `Literal` entries (whose probes keep their own count). (codex)
20. **Sequencing with DEV-2302.** Plan now; merge `origin/main` once DEV-2302 lands (the issue's agent notes). (default)
21. **The conformance runner isolates the cache.** Each case runs with `LA_CACHE_DIR` set to its own temporary
    directory, so the corpus never reads or writes a shared cache. (default)
22. **An entry located on an import alias or re-export matches by binding.** It renames the occurrences whose recorded
    chain holds that binding, and the binding itself, never an occurrence only because it resolves to the same final
    declaration. (user)

## Risks / Trade-offs

- [The hook touches basedpyright internals] → version-pinned, anchors counted, startup self-test; a new basedpyright
  version must be verified before it is listed, as for #11919.
- [basedpyright and rope disagree on a site both resolve] → basedpyright decides; the differential run (decision 18)
  surfaces every such difference on the corpus before the old path goes.
- [The export's evaluation differs from LSP request semantics (hover, definition)] → the verdict is a branch-for-branch
  port; the differential run and the existing blind-spot and `--attr` goldens pin it.
- [A cache false hit renames wrongly] → the fingerprint covers every input the checker reads; any doubt is a miss;
  output equality hit/miss is a test.
- [The 10-minute target is missed] → profile the export and the text rules on the DEV-1607 copy; a pool of language
  servers splitting the export is the fallback only if the export itself proves impractical.
- [Peak memory] → one program per run; the export holds only records for candidate files.

## Migration Plan

No migration: the change is internal to the Python twin. The cache directory is created on first use; deleting it is
always safe.
