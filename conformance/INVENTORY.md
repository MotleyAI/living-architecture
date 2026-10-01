# Conformance inventory

Every output and exit branch of every command, as of the pre-restructure tool, mapped to the case(s) under
`cases/` that pin it. `tests/test_conformance.py` checks that every case is listed here and every listed id
exists. Cases marked *(new)* pin behaviour introduced by this change; their goldens are hand-written.

## la-arch-check

| Branch | Exit | Cases |
|---|---|---|
| clean model | 0 | `arch-check-ok`, `arch-check-claims-child-module-file`, `arch-check-diagrams-fresh`, `arch-check-parse-spec-inline-statements`, `arch-check-parse-views-absent`, `arch-check-spec-nested-spec-md-counts`, `arch-check-spec-no-openspec-dir-nothing-mapped`, `arch-check-tags-fences`, `arch-check-tags-id-on-next-line` |
| repo root: `--root`, `.git` discovery from a subdir, no `.git` (cwd) | 0 | `arch-check-root-flag`, `arch-check-root-discovery-from-subdir`, `arch-check-root-without-git-is-cwd` |
| `index.yaml` missing (OSError) | 2 | `arch-check-index-missing` |
| `index.yaml` invalid YAML | 2 | `arch-check-index-invalid-yaml` |
| `root_package` absent / empty / not a string | 2 | `arch-check-root-package-absent`, `arch-check-root-package-empty`, `arch-check-root-package-not-string` |
| `root_package` dir missing (OSError) | 2 | `arch-check-root-package-dir-missing` |
| invalid `living-architecture.yaml` | 2 | `arch-check-config-invalid`, `arch-check-config-invalid-regex` |
| claims-exist: package / claim missing on disk | 1 | `arch-check-claims-missing-package`, `arch-check-claims-missing-claim` |
| claims-exactly-once: claimed twice | 1 | `arch-check-claims-duplicate-claim` |
| claims-exactly-once: unclaimed top-level unit (non-units ignored) | 1 | `arch-check-claims-unclaimed-top-level` |
| claims-exactly-once: child declared twice | 1 | `arch-check-claims-child-twice` |
| claims-exactly-once: child collides with a declared unit | 1 | `arch-check-claims-child-collides` |
| claims-exist: child missing on disk | 1 | `arch-check-claims-child-missing` |
| claims-exist: virtual node with children | 1 | `arch-check-claims-virtual-children` |
| arc42-exists: system doc / node doc / cross-cutting doc missing; orphan doc | 1 | `arch-check-arc42-system-missing`, `arch-check-arc42-node-doc-missing`, `arch-check-arc42-cross-cutting-missing`, `arch-check-arc42-orphan` |
| model-identity: node / child not in model; element unmapped; no model files | 1 | `arch-check-identity-node-not-in-model`, `arch-check-identity-child-not-in-model`, `arch-check-identity-element-unmapped`, `arch-check-identity-no-model-files` |
| spec-mapping: mapped twice; node and cross-cutting; unknown touched node | 1 | `arch-check-spec-mapped-twice`, `arch-check-spec-node-and-cross-cutting`, `arch-check-spec-touches-unknown-node` |
| spec-mapping: unmapped dir; mapped dir missing; dir without spec.md; no openspec dir | 1 | `arch-check-spec-dir-unmapped`, `arch-check-spec-mapped-dir-missing`, `arch-check-spec-dir-without-spec-md`, `arch-check-spec-no-openspec-dir` |
| baseline-ratchet: missing (absent, not a mapping, no key) | 1 | `arch-check-ratchet-missing`, `arch-check-ratchet-not-mapping`, `arch-check-ratchet-no-baseline-key` |
| baseline-ratchet: not a non-negative integer, rendered with `!r` per value type | 1 | `arch-check-ratchet-bad-negative`, `arch-check-ratchet-bad-list`, `arch-check-ratchet-bad-string`, `arch-check-ratchet-bad-string-with-quote`, `arch-check-ratchet-bad-bool`, `arch-check-ratchet-bad-float`, `arch-check-ratchet-bad-null`, `arch-check-ratchet-bad-mapping` |
| baseline-ratchet: count differs | 1 | `arch-check-ratchet-mismatch` |
| model-truth: missing edge with witness; dead arrow; shadowed arrow; internal arrow | 1 | `arch-check-truth-missing-edge`, `arch-check-truth-dead-arrow`, `arch-check-truth-shadowed-arrow`, `arch-check-truth-internal-arrow` |
| model-truth measurement: witness order, TYPE_CHECKING forms, relative imports, root package, unmodelled modules, unclaimed sources | 0/1 | `arch-check-truth-witness-first-file`, `arch-check-truth-type-checking-excluded`, `arch-check-truth-type-checking-counted`, `arch-check-truth-relative-imports`, `arch-check-truth-root-package-import`, `arch-check-truth-unmodelled-modules`, `arch-check-truth-unclaimed-source-skipped` |
| enforced-tags: unclosed tag; `[review]` with text; no colon; empty id; multi-line id | 1 | `arch-check-tags-unclosed`, `arch-check-tags-review-with-text`, `arch-check-tags-no-colon`, `arch-check-tags-empty-id`, `arch-check-tags-multiline-id` |
| enforced-tags: target id vs `issue_key_pattern` (default, custom, full match, quote repr) | 1 | `arch-check-tags-target-mismatch`, `arch-check-tags-target-quote`, `arch-check-tags-custom-issue-key-pattern`, `arch-check-tags-issue-key-full-match` |
| enforced-tags: unknown enforcement id | 1 | `arch-check-tags-unknown-id`, `arch-check-tags-tag-in-node-doc` |
| enforced-tags: principle item without a status tag (continuations, nesting, headings) | 1 | `arch-check-tags-untagged-item`, `arch-check-tags-item-continuation` |
| diagrams-fresh: no diagrams block; block not a mapping | 1 | `arch-check-diagrams-block-absent`, `arch-check-diagrams-block-not-mapping` |
| diagrams-fresh: bad key, non-list, empty list, invalid ids (`!r`), duplicate ids | 1 | `arch-check-diagrams-entry-errors`, `arch-check-diagrams-bad-view-ids` |
| diagrams-fresh: mapped doc missing; view unknown | 1 | `arch-check-diagrams-doc-missing-and-view-unknown` |
| diagrams-fresh: marker pair missing / duplicate / out of order; orphan markers | 1 | `arch-check-diagrams-marker-missing`, `arch-check-diagrams-marker-duplicate`, `arch-check-diagrams-marker-order`, `arch-check-diagrams-orphan-markers` |
| diagrams-fresh: stale diagram (incl. CRLF bytes) | 1 | `arch-check-diagrams-stale`, `arch-check-diagrams-crlf-is-stale` |
| diagrams-fresh: every model-parse finding | 1 | `arch-check-parse-model-findings`, `arch-check-parse-spec-inline-before-brace` |
| diagrams-fresh: every views-parse finding; no `views {` block | 1 | `arch-check-parse-views-findings`, `arch-check-parse-views-no-views-block` |
| diagrams-fresh: `view_depth` not a mapping; unknown view; non-positive / non-integer values | 1 | `arch-check-view-depth-not-mapping`, `arch-check-view-depth-findings`, `arch-check-view-depth-bad-string`, `arch-check-view-depth-bad-bool`, `arch-check-view-depth-bad-float`, `arch-check-view-depth-bad-negative` |
| *(new)* `source_root`: src layout, prefix-free ids, architecture/specs stay at the repo root, `.`, symlink inside the repo | 0/1 | `arch-check-source-root-src-layout`, `arch-check-source-root-src-layout-findings`, `arch-check-source-root-control-findings`, `arch-check-source-root-architecture-stays-at-repo-root`, `arch-check-source-root-dot`, `arch-check-source-root-symlink-inside-repo` |
| *(new)* `source_root` invalid: absolute, `..`, escapes the repo, symlink escape, not a dir, missing, lacks `root_package`, not a string | 2 | `arch-check-source-root-invalid-absolute`, `arch-check-source-root-invalid-parent-segment`, `arch-check-source-root-invalid-escapes-repo`, `arch-check-source-root-invalid-symlink-escape`, `arch-check-source-root-invalid-not-a-directory`, `arch-check-source-root-invalid-missing`, `arch-check-source-root-invalid-lacks-root-package`, `arch-check-source-root-invalid-not-a-string` |

## la-arch-diagrams

| Branch | Exit | Cases |
|---|---|---|
| fresh docs: nothing printed, nothing written | 0 | `arch-diagrams-noop-when-fresh` |
| rewritten docs printed; rendering (nested, flat, predicates, several views and docs, title escape, virtual shape, legacy dashing) | 0 | `arch-diagrams-rewrite-hierarchical`, `arch-diagrams-rewrite-flat-depth-1`, `arch-diagrams-root-flag`, `arch-diagrams-predicates-and-multiple-views`, `arch-diagrams-title-escape-and-virtual-shape`, `arch-diagrams-legacy-only-when-all-contributors-are`, `arch-diagrams-crlf-outside-block-preserved` |
| index missing / invalid YAML / not a mapping / no diagrams block / block not a mapping | 1 | `arch-diagrams-index-missing`, `arch-diagrams-index-invalid-yaml`, `arch-diagrams-index-not-mapping`, `arch-diagrams-no-diagrams-block`, `arch-diagrams-diagrams-not-mapping` |
| model/views findings block generation | 1 | `arch-diagrams-parse-findings-block-generation` |
| key not an arc42 path (`!r`) | 1 | `arch-diagrams-key-not-arc42-path` |
| view not defined (incl. no views.c4, string view list) | 1 | `arch-diagrams-view-not-defined`, `arch-diagrams-no-views-file`, `arch-diagrams-view-ids-string-iterates` |
| missing / duplicate / out-of-order markers; earlier docs already written | 1 | `arch-diagrams-marker-missing`, `arch-diagrams-marker-duplicate`, `arch-diagrams-marker-order`, `arch-diagrams-first-error-stops-later-docs` |
| mapped doc missing (OSError) | 1 | `arch-diagrams-doc-missing` |
| usage error; `--help` | 2/0 | `arch-diagrams-usage-unknown-flag`, `arch-diagrams-help` |

## la-config

| Branch | Exit | Cases |
|---|---|---|
| `show`: defaults (no file, empty, comments, `{}`), partial, falsy kept, YAML 1.1, duplicate keys, full, integer float, non-ASCII, portable pattern | 0 | `config-show-defaults`, `config-show-empty-file`, `config-show-comments-only`, `config-show-empty-mapping`, `config-show-partial-nested`, `config-show-explicit-falsy`, `config-show-yaml11-booleans`, `config-show-duplicate-key`, `config-show-full`, `config-show-integer-ratio`, `config-show-non-ascii`, `config-show-sonar-disabled-with-key`, `config-show-portable-patterns` |
| *(new)* strict scalar types: string/int for a bool, string for a number (pydantic used to coerce) | 1 | `config-error-lax-string-bool`, `config-error-lax-int-bool`, `config-error-lax-string-float` |
| `get`: bool, null (empty line), string, float, list/mapping as JSON, non-ASCII | 0 | `config-get-bool-true`, `config-get-bool-false`, `config-get-null-is-empty`, `config-get-string`, `config-get-float`, `config-get-integer-float`, `config-get-empty-list`, `config-get-list`, `config-get-mapping`, `config-get-non-ascii`, `config-get-non-ascii-in-list` |
| `get`: unknown key; key into a scalar | 2 | `config-get-unknown-key`, `config-get-into-scalar` |
| invalid config (key named) | 1 | `config-error-unknown-top-key`, `config-error-unknown-nested-key`, `config-error-sonar-without-key`, `config-error-sonar-empty-key`, `config-error-ratio-zero`, `config-error-ratio-above-one`, `config-error-ratio-negative`, `config-error-invalid-regex`, `config-error-pattern-not-string`, `config-error-bool-not-bool`, `config-error-exempt-not-list`, `config-error-command-not-string`, `config-error-null-section`, `config-error-top-level-list`, `config-error-top-level-scalar`, `config-error-invalid-yaml`, `config-get-invalid-config` |
| *(new)* non-portable `issue_key_pattern` | 1 | `config-error-non-portable-lookbehind`, `config-error-non-portable-named-group`, `config-error-non-portable-inline-flag`, `config-error-non-portable-possessive`, `config-error-non-portable-atomic` |
| repo root: `--root`, discovery from a subdir, no `.git` | 0 | `config-root-flag`, `config-root-discovery-from-subdir`, `config-root-without-git-is-cwd` |
| usage errors; `--help`; *(new)* `--` honoured | 2/0 | `config-usage-no-args`, `config-usage-unknown-subcommand`, `config-usage-get-without-key`, `config-usage-root-after-subcommand`, `config-usage-unknown-flag`, `config-usage-show-extra-positional`, `config-help`, `config-double-dash` |

## la-doctor

| Branch | Exit | Cases |
|---|---|---|
| healthy (defaults / config file / `--root`), `--expect` matching | 0 | `doctor-ok-defaults`, `doctor-ok-config-file`, `doctor-root-flag`, `doctor-expect-match` |
| version mismatch; invalid config; `git`/`gh` missing; all problems in order | 1 | `doctor-expect-mismatch`, `doctor-config-invalid`, `doctor-missing-git`, `doctor-missing-gh`, `doctor-missing-both`, `doctor-all-problems-in-order` |
| usage errors; `--help` | 2/0 | `doctor-usage-unknown-flag`, `doctor-usage-expect-without-value`, `doctor-help` |

`--contract-hash` *(new)* prints a value that changes with `shared/`; it is pinned by `tests/test_contract.py`.

## la-check-conventions

| Branch | Exit | Cases |
|---|---|---|
| gate CLEAR | 0 | `conventions-clean`, `conventions-import-wrappers-in-prologue`, `conventions-missing-file-skipped`, `conventions-text-ratio-empty-file`, `conventions-text-ratio-boundary-equal`, `conventions-test-file-classification-bare-names` |
| import-not-top: after code, in functions, wrappers after code, def in a wrapper, second string | 1 | `conventions-import-after-code`, `conventions-import-in-functions`, `conventions-import-wrappers-after-code`, `conventions-import-wrapper-with-def-ends-prologue`, `conventions-import-after-second-string` |
| composite-assert (tests only); raises-single-throw (every callee form) | 1 | `conventions-composite-assert`, `conventions-raises-single-throw` |
| test-file classification | 1/0 | `conventions-test-file-classification`, `conventions-test-file-classification-bare-names` |
| waivers (valid, compact, wrong rule, no reason, wrong case) | 1 | `conventions-waivers` |
| unreadable (decode error, directory); syntax error | 1 | `conventions-unreadable-binary`, `conventions-unreadable-directory`, `conventions-syntax-error` |
| text-ratio: source over, tests over, standalone strings; cap from flag / config | 1/0 | `conventions-text-ratio-source-over`, `conventions-text-ratio-tests-over`, `conventions-text-ratio-standalone-strings`, `conventions-text-ratio-cap-flag`, `conventions-text-ratio-config-cap` |
| exempt globs (config + `--exclude`, fnmatch semantics) | 0 | `conventions-exempt-config-and-flag`, `conventions-accepted-invocation-vector`, `conventions-accepted-invocation-vector-with-exempt-file`, `conventions-equals-forms` |
| `--base`: committed, staged, unstaged, untracked, deleted, renamed; origin vs local; no .py changes | 0/1 | `conventions-base-committed`, `conventions-base-working-tree`, `conventions-base-uses-origin-not-local`, `conventions-base-no-python-changes` |
| `--base` ref missing; not a git repo | 2 | `conventions-base-ref-missing`, `conventions-base-not-a-git-repo` |
| PR lookup: resolves, `--repo`, fails; `--base` wins; `--file` wins | 1/2/0 | `conventions-pr-resolves-base`, `conventions-pr-with-repo`, `conventions-pr-lookup-fails`, `conventions-pr-and-base-prefers-base`, `conventions-file-overrides-base`, `conventions-double-dash-pr` |
| invalid config | 2 | `conventions-config-invalid` |
| usage errors; `--help`; *(new)* abbreviated option rejected | 2/0 | `conventions-usage-no-target`, `conventions-usage-cap-not-a-number`, `conventions-help`, `conventions-usage-abbreviated-option` |

## la-count-comments

| Branch | Exit | Cases |
|---|---|---|
| per-file counts and total (comments, every docstring owner) | 0 | `count-comments-files` |
| missing file, syntax error, tokenize error | 0 | `count-comments-missing-file`, `count-comments-syntax-error`, `count-comments-tokenize-error` |
| passthrough argv (`--`, `--help` are paths) | 0 | `count-comments-double-dash-is-a-path`, `count-comments-help-is-a-path` |
| `--range`: added, removed, unchanged, new file; repo-relative ref paths | 0 | `count-comments-range`, `count-comments-range-paths-are-repo-relative` |
| usage: no args; `--range` with too few args | 2 | `count-comments-usage-no-args`, `count-comments-range-too-few-args` |

## dr-compliance

| Branch | Exit | Cases |
|---|---|---|
| every check, string-sorted output | 1 | `compliance-all-checks` |
| `--select` subset / whitespace / empty; unknown check | 1/0/2 | `compliance-select-subset`, `compliance-select-whitespace`, `compliance-select-empty`, `compliance-select-unknown` |
| `--attr` blind spots | 1 | `compliance-attr-blindspot` |
| directory recursion; parse error; clean | 1/0 | `compliance-directory-recursion`, `compliance-parse-error`, `compliance-clean` |
| `--` before paths | 0/1 | `compliance-double-dash`, `compliance-double-dash-dash-path` |
| usage error; `--help` | 2/0 | `compliance-usage-no-paths`, `compliance-help` |

## dr-mock-lint

| Branch | Exit | Cases |
|---|---|---|
| every mock and patch form | 1 | `mock-lint-violations` |
| directory recursion; clean | 1/0 | `mock-lint-directory-recursion`, `mock-lint-clean` |
| usage error | 2 | `mock-lint-usage-no-args` |

## dr-refactor

| Branch | Exit | Cases |
|---|---|---|
| rename: dry-run / apply by name, line+col, offset; hierarchy on/off; `--unsure include` warning; *(new)* changes printed sorted by path | 0 | `refactor-rename-dry-run`, `refactor-rename-apply`, `refactor-rename-single-file-dry-run`, `refactor-rename-single-file-apply`, `refactor-rename-line-col`, `refactor-rename-no-in-hierarchy`, `refactor-rename-offset`, `refactor-rename-unsure-include` |
| move-symbol (*(new)* sorted by path); move-module (tracked, untracked); `--project` | 0 | `refactor-move-symbol-apply`, `refactor-move-module-apply`, `refactor-move-module-uncommitted`, `refactor-project-flag` |
| no locator; line out of range; symbol not found; path outside the project | 1 | `refactor-no-locator`, `refactor-line-out-of-range`, `refactor-symbol-not-found`, `refactor-path-outside-project` |
| usage errors; `--help` | 2/0 | `refactor-usage-no-subcommand`, `refactor-usage-rename-without-new-name`, `refactor-usage-rename-without-file`, `refactor-usage-bad-unsure-choice`, `refactor-usage-offset-not-int`, `refactor-help` |

## Review shims and their bundled scripts

| Branch | Exit | Cases |
|---|---|---|
| CodeRabbit-gated shims: disabled; invalid config | 3/2 | `shim-fetch-coderabbit-threads-disabled`, `shim-reply-invalid-coderabbit-disabled`, `shim-fetch-coderabbit-threads-config-invalid`, `shim-reply-invalid-coderabbit-config-invalid` |
| ungated shims ignore the config | 0 | `shim-reply-to-pr-thread-ignores-config`, `shim-fetch-failed-pr-checks-ignores-config` |
| `la-wait-for-reviews` reads the config (invalid → 2; disabled → `--skip-coderabbit` appended) | 2/0 | `shim-wait-for-reviews-config-invalid`, `shim-wait-for-reviews-disabled-skips-settle` |
| fetch-coderabbit-threads: threads + nitpicks + outside-diff; all authors; argument and repo errors | 0/2 | `shim-fetch-coderabbit-threads-ok`, `shim-fetch-coderabbit-threads-all-authors`, `shim-fetch-coderabbit-threads-bad-pr`, `shim-fetch-coderabbit-threads-bad-repo`, `shim-fetch-coderabbit-threads-unknown-flag`, `shim-fetch-coderabbit-threads-repo-autodetect-fails` |
| reply-invalid-coderabbit: mention prepended; empty body | 0/2 | `shim-reply-invalid-coderabbit-ok`, `shim-reply-invalid-coderabbit-empty-body` |
| reply-to-pr-thread: URL; explicit ids; review-summary URL; bad URL; empty body; bad id | 0/2 | `shim-reply-to-pr-thread-ok`, `shim-reply-to-pr-thread-explicit-ids`, `shim-reply-to-pr-thread-review-summary-url`, `shim-reply-to-pr-thread-bad-url`, `shim-reply-to-pr-thread-empty-body`, `shim-reply-to-pr-thread-bad-comment-id` |
| fetch-failed-pr-checks: failures with logs; full-log fallback; none; argument errors | 0/2 | `shim-fetch-failed-pr-checks-ok`, `shim-fetch-failed-pr-checks-full-log-fallback`, `shim-fetch-failed-pr-checks-none`, `shim-fetch-failed-pr-checks-bad-pr`, `shim-fetch-failed-pr-checks-bad-max-log` |
| wait-for-reviews: no CodeRabbit context; fresh summary; rate limited; gate fails closed; no PR; repo auto-detect fails | 0/3/1/64/2 | `shim-wait-for-reviews-no-coderabbit-context`, `shim-wait-for-reviews-fresh-summary`, `shim-wait-for-reviews-rate-limited`, `shim-wait-for-reviews-gate-fails-closed`, `shim-wait-for-reviews-requires-pr`, `shim-wait-for-reviews-repo-autodetect-fails` |

The scripts are shared byte-for-byte between the twins. Their remaining internal branches (thread and
comment pagination, the polling loops' sleep-and-retry paths, the 10-minute CodeRabbit cap) depend on wall
time or many paged responses. Those branches are pinned by `tests/test_review_scripts.py`, not by the corpus.

## Excluded: crashes

These inputs crash today's tool with a traceback (exit 1). A traceback's module paths and line numbers cannot
survive the restructure, so the corpus does not pin them, and the post-change behaviour is not part of the
contract:

- `la-arch-check`: `index.yaml` that is not a mapping, a node without `package`, non-mapping node specs, a
  syntax error in a measured `.py` file, non-list `children`/`claims`/`specs`
- `la-arch-diagrams`: a `diagrams` entry whose view list is neither a list nor a string
- `dr-compliance`, `dr-mock-lint`: a path that does not exist; `dr-mock-lint` on a file with a syntax error
- `dr-refactor`: rope errors on a location that is not a renameable symbol

## Excluded from byte comparison

- `--help` text and parser error wording: the exit code is pinned and the streams are `ignore`.
- Config validation wording: the exit code and the offending key are pinned (`contains`).
- Wording from git and the YAML parser.
