## Context

See proposal.md (Why). DEV-2025 shipped the npm twin, the `twin` node (identity handshake, PATH discovery,
runner probe, wholesale forwarding, the arch-check facts transport), the two-root model and the conformance case
model with an invoking twin. Today `la-check-conventions` and `la-count-comments` are `native: [python]`; the npm
twin forwards them wholesale and the PyPI twin ignores non-Python files. Normative harnesses
(`architecture/system.arc42.md`): principle 1 (twins identical, the corpus decides), 2 (parameters, texts and
surfaces only from `shared/`), 3 (language-specific code only in `lang` and `refactor`), 4 (no target-repo code
imported or executed). Principles 1–3 hold unchanged; principle 4 gains one exception (D7).

## Goals / Non-Goals

**Goals:**
- Conventions and typecheck output depends only on the repo, never on the invoking twin.
- Each language's facts come from exactly one adapter; gate math has one implementation per twin.
- Zero-config `la-typecheck` is safe in repos with stray files of another language.

**Non-Goals:**
- Enforcing suppression forms (`@ts-ignore`, bare `# type: ignore`): recorded as a `languages.yaml` fact only.
- Skill text changes (DEV-2027 switches skills to `la-typecheck`), TS `dr-*`, the first public npm release.
- Multi-package workspaces: one marker, local bin dir and baseline per language at the repo root.

## Decisions

### D1 — Facts, not findings, for conventions (as DEV-2025 D3)
Both conventions commands become neutral. A twin analyses its own language in-process and asks the other twin for
a `conventions-facts` document (new `shared/schema/conventions-facts.schema.json`) through internal options
`la-check-conventions --language L --emit facts`, paths on stdin as a JSON array (avoids argv limits; keeps
order). The document carries per path: status, failure line/message, detections with the flagged line's text,
text/total line counts and comment/doc counts — one schema for both commands. Carrying the line text keeps file
decoding inside the language's own adapter, so the neutral waiver check never reads target files.
Alternatives: wholesale or `--file` forwarding of rendered output (two verdicts; order depends on the invoking
twin; waivers and ratio computed twice); a JSON report merged by the parent with per-language ratio groups
(rejected in favour of cross-language groups, D3).

### D2 — Routing by extension, NUL-safe
`git diff --name-only -z --diff-filter=ACMR` for both diff targets and `git ls-files -z` for typecheck discovery.
Unknown extensions: silent from a diff, warned when explicit. No `index.yaml` coupling: `conventions` keeps its
arrows. Alternative: only the languages with an `index.yaml` section (couples the gate to the architecture setup;
leaves mixed-repo code unchecked).

### D3 — One report, cross-language ratio groups
Text-ratio keeps the two groups `source`/`tests` across languages, so single-language output is unchanged; the
per-file breakdown still names the worst files. The files label joins each present language's `files_label`
(`.py`, `TS/JS`) in language-id order, or `source` when nothing was checked.

### D4 — TS detectors
TypeScript 6.0 `ts.createSourceFile` per file with the ScriptKind of its extension; syntactic diagnostics give
`syntax-error`. Comments come from the scanner (`ts.forEachLeadingCommentRange`/trailing ranges over the full
text). Rule semantics are in the conventions spec; the reference behaviours are eslint `import/first`,
`n/global-require`, and the Python twin's `raises-single-throw` call counting (`new` counts as a call, as
`Foo()` does in Python). TS-worded findings templates; Python templates unchanged.

### D5 — `la-typecheck` architecture
A new neutral `typecheck` node in both twins: applicable languages, command resolution (shared shell-word split
pinned by `shared/vectors/command-split.yaml`; local bin dir then `PATH`), headers, language order, exit
combination, `--write-baseline` skip logic (baseline paths from `languages.yaml` `baseline_file`), and forwarding
the other language through `twin` (internal `la-typecheck --language L`, output relayed). Checker specifics live
in each twin's `lang`: basedpyright flag, exit-code mapping (PyPI twin); tsc diagnostic grammar
(`^(.+)\((\d+),(\d+)\): error (TS\d+): `, greedy path), multiset baseline and its JSON (npm twin).
Alternative: inside `conventions` (a grab bag; its name stops fitting).

### D6 — Applicability and config
`commands.typecheck` is a map only; defaults (`basedpyright`, `tsc --noEmit`) live in the schema, the only source
of defaults (DEV-1990 D4), so `languages.yaml` `type_checker` is removed. A language applies when explicitly
configured, or when it has files and a root marker (`markers`: `pyproject.toml`/`setup.py`; `tsconfig.json`).
Alternatives: files alone (a stray `docs/static/app.js` makes tsc fail in every Python repo); a string form (its
language is ambiguous without a repo language, which DEV-2025 dropped).

### D7 — Principle 4 exception (approved wording)
`4. Tools never import or execute target-repo code, except a configured command (`commands.*`).` Running the
repo's own checker is the point of `la-typecheck`; defaults count as configuration because they materialize from
the schema.

### D8 — Baseline semantics mirror basedpyright
Probed on basedpyright 1.39: it shrinks only on runs without new errors, exits 1 on an initial
`--writebaseline` with errors, and writes no file for a clean project. The tsc ratchet mirrors the shrink rule;
`la-typecheck` normalizes write mode to exit 0, writes an empty baseline for a clean language, and refuses (per
language, skip with notice) to overwrite an existing baseline. Count increases list every occurrence of the key:
the multiset cannot tell which one is new.

### D9 — Model (approval-gated, exact text at implement time)
`python`: add `typecheck`; `cli -> typecheck`, `typecheck -> lang/config/contract/twin`, `conventions -> twin`.
`typescript`: add `conventions` and `typecheck`; `cli -> conventions`, `cli -> typecheck`,
`conventions -> lang/config/contract/twin`, `typecheck -> lang/config/contract/twin`. Spec mapping at archive:
`conventions` on `python.conventions`, `typecheck` on `python.typecheck` (DEV-2025 precedent).

## Risks / Trade-offs

- [Python repos whose diffs touch JS now need the npm twin] → Node is already a prerequisite (OpenSpec, LikeC4);
  `conventions.exempt` opts paths out; documented as BREAKING.
- [A TS-only repo with a stray `.py` change invokes `uvx`, against DEV-2027's Node-only acceptance] → exempt it;
  the acceptance fixture must not contain Python.
- [Custom Python commands that aren't basedpyright-compatible misbehave] → documented in the schema description;
  a conformance case pins the failure mode.
- [`--baselinefile` elsewhere defeats the existence check] → documented limit.
- [Real checker output is version-dependent] → conformance uses fake checkers in the fixture's local bin dir; one
  real-checker test per twin in the integration set.

## Migration Plan

Users upgrade both twins together (versions move in lockstep). Repos with TS files under `docs/` or similar that
should not be gated add them to `conventions.exempt`. `la-typecheck --write-baseline` once per repo. Rollback is
reverting to the previous release; the only persisted artefacts are baseline files.
