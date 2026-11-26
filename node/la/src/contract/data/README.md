# living-architecture contract

The source of truth both la twins obey. Each twin vendors a byte-copy of this directory (refreshed by
`scripts/sync-shared`) and loads only that copy at runtime. The YAML profile, configuration filling, templates,
canonical repr, glob dialect and contract hash are trmv's (`shared/trmv/README.md`); la renders a finding id from its
own registry, else from trmv's.

| File | Defines |
|---|---|
| `schema/living-architecture.schema.json` | la's config keys, types, bounds, cross-field rules, defaults; trmv's keys by reference to trmv's schema |
| `schema/living-architecture.local.schema.json` | the per-person keys `living-architecture.local.yaml` may override |
| `schema/index.schema.json` | the `architecture/index.yaml` shape |
| `schema/node.schema.json` | a node's `metadata { }` block in the LikeC4 model |
| `schema/facts.schema.json`, `schema/conventions-facts.schema.json` | one language's architecture or conventions facts, as one twin hands them to the other |
| `schema/affected-request.schema.json`, `schema/affected-response.schema.json` | the change set one twin hands the other for `la-affected-tests`, and that language's selected tests |
| `config.yaml` | la's committed config file and its local override file |
| `findings.yaml` | every finding, verdict and hint an la command prints, by id; the arch-check ids |
| `cli.yaml` | every la command's options, positionals, subcommands and exit codes |
| `conventions.yaml` | conventions-gate rules and the waiver syntax |
| `architecture.yaml` | the LikeC4 layout: the canonical model and views files, their blocks, the source extensions |
| `vectors/` | input/output vectors both test suites consume |
| `scripts/` | the review helpers (bash, `gh`, `jq`) |

## LikeC4 layout

A LikeC4 source is a file under `architecture/`, at any depth, whose name ends in one of `source_extensions`
(case-sensitive). A symlink to a file counts as a file; a symlinked directory is not descended into. A
canonical path that exists but is not a regular file (or a symlink to one) is "not a file". Paths are listed
repo-relative, in ascending code-point order (never UTF-16 order); violations within one file follow file order.
