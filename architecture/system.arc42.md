# System

## Purpose and context

Two packages, each with a Claude Code plugin: `deterministic-refactor` (`dr-*` commands, plugin `dr`): verified
renames and moves and the type-check gate; and `living-architecture` (`la-*` commands, plugin `la`): the
architecture cross-check, the conventions gate, the review helpers and the PR flow. la depends on dr. Each package
has two native implementations (twins) that obey its contract in `shared/<package>/`: the PyPI packages in
`python/` serve Python repos, and the npm packages in `node/` serve TS/JS repos. The skills in `plugin/<package>/`
drive the commands.

## Building blocks

<!-- likec4:system -->
```mermaid
flowchart TD
  %% system: Living-architecture commands
  subgraph dr["deterministic-refactor"]
    dr__contract["Shared contract"]
    dr__config["Config"]
    dr__lang["Language adapter"]
    dr__twin["Twin forwarding"]
    dr__changes["Change set"]
    dr__typecheck["Type check"]
    dr__refactor["Deterministic refactoring"]
    dr__doctor["Doctor"]
    dr__cli["CLI"]
  end
  subgraph la["living-architecture"]
    la__contract["Shared contract"]
    la__config["Config"]
    la__cli["CLI"]
    la__c4["LikeC4 model"]
    la__archcheck["Architecture check"]
    la__conventions["Conventions and comments"]
    la__review["Review shims"]
    la__doctor["Doctor"]
    la__affected["Affected tests"]
  end
  la --> dr
  dr__changes --> dr__config
  dr__changes --> dr__contract
  dr__cli --> dr__config
  dr__cli --> dr__doctor
  dr__cli --> dr__refactor
  dr__cli --> dr__twin
  dr__cli --> dr__typecheck
  dr__config --> dr__contract
  dr__doctor --> dr__config
  dr__doctor --> dr__contract
  dr__doctor --> dr__twin
  dr__lang --> dr__contract
  dr__refactor --> dr__changes
  dr__refactor --> dr__config
  dr__refactor --> dr__contract
  dr__refactor --> dr__lang
  dr__refactor --> dr__twin
  dr__refactor --> dr__typecheck
  dr__twin --> dr__contract
  dr__typecheck --> dr__changes
  dr__typecheck --> dr__config
  dr__typecheck --> dr__contract
  dr__typecheck --> dr__lang
  dr__typecheck --> dr__twin
  la__affected --> la__contract
  la__archcheck --> la__c4
  la__archcheck --> la__config
  la__archcheck --> la__contract
  la__c4 --> la__contract
  la__cli --> la__affected
  la__cli --> la__archcheck
  la__cli --> la__c4
  la__cli --> la__config
  la__cli --> la__contract
  la__cli --> la__conventions
  la__cli --> la__doctor
  la__cli --> la__review
  la__config --> la__contract
  la__conventions --> la__config
  la__conventions --> la__contract
  la__doctor --> la__config
  la__doctor --> la__contract
  la__review --> la__contract
  classDef leaf fill:none;
  class dr__contract,dr__config,dr__lang,dr__twin,dr__changes,dr__typecheck,dr__refactor,dr__doctor,dr__cli,la__contract,la__config,la__cli,la__c4,la__archcheck,la__conventions,la__review,la__doctor,la__affected leaf;
```
<!-- /likec4:system -->

<!-- likec4:npm -->
```mermaid
flowchart TD
  %% npm: npm twin
  subgraph dr["deterministic-refactor"]
    dr__contract["Shared contract"]
    dr__config["Config"]
    dr__lang["Language adapter"]
    dr__twin["Twin forwarding"]
    dr__changes["Change set"]
    dr__typecheck["Type check"]
    dr__refactor["Deterministic refactoring"]
    dr__doctor["Doctor"]
    dr__cli["CLI"]
  end
  subgraph la["living-architecture"]
    la__contract["Shared contract"]
    la__config["Config"]
    la__cli["CLI"]
    la__c4["LikeC4 model"]
    la__archcheck["Architecture check"]
    la__conventions["Conventions and comments"]
    la__review["Review shims"]
    la__doctor["Doctor"]
    la__affected["Affected tests"]
  end
  la --> dr
  dr__changes --> dr__config
  dr__changes --> dr__contract
  dr__cli --> dr__config
  dr__cli --> dr__doctor
  dr__cli --> dr__refactor
  dr__cli --> dr__twin
  dr__cli --> dr__typecheck
  dr__config --> dr__contract
  dr__config --> dr__twin
  dr__doctor --> dr__config
  dr__doctor --> dr__contract
  dr__doctor --> dr__twin
  dr__lang --> dr__contract
  dr__refactor --> dr__changes
  dr__refactor --> dr__config
  dr__refactor --> dr__contract
  dr__refactor --> dr__lang
  dr__refactor --> dr__twin
  dr__twin --> dr__contract
  dr__typecheck --> dr__changes
  dr__typecheck --> dr__config
  dr__typecheck --> dr__contract
  dr__typecheck --> dr__lang
  dr__typecheck --> dr__twin
  la__affected --> la__contract
  la__archcheck --> la__c4
  la__archcheck --> la__config
  la__archcheck --> la__contract
  la__c4 --> la__contract
  la__cli --> la__affected
  la__cli --> la__archcheck
  la__cli --> la__c4
  la__cli --> la__config
  la__cli --> la__contract
  la__cli --> la__conventions
  la__cli --> la__doctor
  la__cli --> la__review
  la__config --> la__contract
  la__conventions --> la__config
  la__conventions --> la__contract
  la__doctor --> la__config
  la__doctor --> la__contract
  la__review --> la__contract
  classDef leaf fill:none;
  class dr__contract,dr__config,dr__lang,dr__twin,dr__changes,dr__typecheck,dr__refactor,dr__doctor,dr__cli,la__contract,la__config,la__cli,la__c4,la__archcheck,la__conventions,la__review,la__doctor,la__affected leaf;
```
<!-- /likec4:npm -->

## Principles

1. Twins: every behaviour observable through a command is identical in both implementations for the
   languages they share, on every input in the forms the tools and docs write; the conformance corpus
   decides. [enforced: test:python/dr/tests/test_conformance.py]
   [enforced: test:python/la/tests/test_conformance.py] [enforced: test:node/scripts/conformance.mjs]
2. Parameters, defaults, user-facing texts and command surfaces come only from the shared contracts. [review]
3. Language-specific code lives only in `dr.lang` and `dr.refactor`. [review]
4. Tools never import or execute target-repo code, except a configured command (`commands.*`). [review]
5. `dr` never depends on `la`. [enforced: arch_check:model-truth]

## Rationale

Each ecosystem keeps native tooling: Python repos need no Node runtime for analysis and TS/JS repos need no
Python. Only the language-neutral core is implemented twice, so the shared contract and the conformance
corpus make drift a test failure instead of a review finding. The node split is the same in both twins, and
confining language-specific code to `lang` and `refactor` keeps everything else a straight port.

Verified refactoring is useful without the architecture workflow, so it is its own package that la uses as a library;
the dependency runs one way so dr installs and runs alone.
