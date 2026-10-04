# System

## Purpose and context

The `la-*` and `dr-*` commands behind the `la` Claude Code plugin: the architecture cross-check, the
conventions gate, the review helpers and verified refactoring. Two native implementations (twins) obey one
contract in `shared/`: the PyPI package in `python/` serves Python repos, and an npm twin serves TS/JS
repos. The skills in `plugin/` drive the commands.

## Building blocks

<!-- likec4:system -->
```mermaid
flowchart TD
  %% system: Living-architecture commands
  contract["Shared contract"]
  config["Config"]
  cli["CLI"]
  c4["LikeC4 model"]
  archcheck["Architecture check"]
  lang["Language adapter"]
  conventions["Conventions and comments"]
  review["Review shims"]
  doctor["Doctor"]
  refactor["Deterministic refactoring"]
  twin["Twin forwarding"]
  typecheck["Type check"]
  cli --> contract
  cli --> config
  cli --> archcheck
  cli --> c4
  cli --> conventions
  cli --> review
  cli --> doctor
  cli --> refactor
  archcheck --> c4
  archcheck --> lang
  archcheck --> config
  archcheck --> contract
  conventions --> lang
  conventions --> config
  conventions --> contract
  c4 --> contract
  config --> contract
  review --> config
  review --> contract
  doctor --> config
  doctor --> contract
  refactor --> contract
  cli --> twin
  archcheck --> twin
  twin --> contract
  cli --> typecheck
  typecheck --> lang
  typecheck --> config
  typecheck --> contract
  typecheck --> twin
  conventions --> twin
```
<!-- /likec4:system -->

<!-- likec4:npm -->
```mermaid
flowchart TD
  %% npm: npm twin
  contract["Shared contract"]
  config["Config"]
  cli["CLI"]
  c4["LikeC4 model"]
  archcheck["Architecture check"]
  lang["Language adapter"]
  review["Review shims"]
  doctor["Doctor"]
  twin["Twin forwarding"]
  conventions["Conventions and comments"]
  typecheck["Type check"]
  cli --> contract
  cli --> config
  cli --> archcheck
  cli --> c4
  cli --> review
  cli --> doctor
  cli --> twin
  archcheck --> c4
  archcheck --> lang
  archcheck --> config
  archcheck --> contract
  archcheck --> twin
  lang --> contract
  c4 --> contract
  config --> contract
  review --> config
  review --> contract
  doctor --> config
  doctor --> contract
  twin --> contract
  cli --> conventions
  cli --> typecheck
  conventions --> lang
  conventions --> config
  conventions --> contract
  conventions --> twin
  typecheck --> lang
  typecheck --> config
  typecheck --> contract
  typecheck --> twin
```
<!-- /likec4:npm -->

## Principles

1. Twins: every behaviour observable through a command is identical in both implementations for the
   languages they share; the conformance corpus decides. [enforced: test:python/tests/test_conformance.py]
   [enforced: test:node/scripts/conformance.mjs]
2. Parameters, defaults, user-facing texts and command surfaces come only from the shared contract.
   [review]
3. Language-specific code lives only in `lang` and `refactor`. [review]
4. Tools never import or execute target-repo code, except a configured command (`commands.*`). [review]

## Rationale

Each ecosystem keeps native tooling: Python repos need no Node runtime for analysis and TS/JS repos need no
Python. Only the language-neutral core is implemented twice, so the shared contract and the conformance
corpus make drift a test failure instead of a review finding. The node split is the same in both twins, and
confining language-specific code to `lang` and `refactor` keeps everything else a straight port.
