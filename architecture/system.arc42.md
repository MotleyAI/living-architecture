# System

## Purpose and context

Two packages, each with a Claude Code plugin: `type-rename-move` (`trmv-*` commands, plugin `trmv`): verified
renames and moves and the type-check gate; and `living-architecture` (`la-*` commands, plugin `la`): the
architecture cross-check, the conventions gate, the review helpers and the PR flow. la depends on trmv. Each package
has two native implementations (twins) that obey its contract in `shared/<package>/`: the PyPI packages in
`python/` serve Python repos, and the npm packages in `node/` serve TS/JS repos. The skills in `plugin/<package>/`
drive the commands.

## Building blocks

<!-- likec4:system -->
```mermaid
flowchart TD
  %% system: Living-architecture commands
  subgraph trmv["type-rename-move"]
    trmv__contract["Shared contract"]
    trmv__config["Config"]
    trmv__lang["Language adapter"]
    trmv__twin["Twin forwarding"]
    trmv__changes["Change set"]
    trmv__typecheck["Type check"]
    trmv__refactor["Rename and move"]
    trmv__doctor["Doctor"]
    trmv__cli["CLI"]
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
    la__leaks["Leak check"]
  end
  la --> trmv
  trmv__changes --> trmv__config
  trmv__changes --> trmv__contract
  trmv__cli --> trmv__config
  trmv__cli --> trmv__doctor
  trmv__cli --> trmv__refactor
  trmv__cli --> trmv__twin
  trmv__cli --> trmv__typecheck
  trmv__config --> trmv__contract
  trmv__doctor --> trmv__config
  trmv__doctor --> trmv__contract
  trmv__doctor --> trmv__twin
  trmv__lang --> trmv__contract
  trmv__refactor --> trmv__changes
  trmv__refactor --> trmv__config
  trmv__refactor --> trmv__contract
  trmv__refactor --> trmv__lang
  trmv__refactor --> trmv__twin
  trmv__refactor --> trmv__typecheck
  trmv__twin --> trmv__contract
  trmv__typecheck --> trmv__changes
  trmv__typecheck --> trmv__config
  trmv__typecheck --> trmv__contract
  trmv__typecheck --> trmv__lang
  trmv__typecheck --> trmv__twin
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
  la__cli --> la__leaks
  la__cli --> la__review
  la__config --> la__contract
  la__conventions --> la__config
  la__conventions --> la__contract
  la__doctor --> la__config
  la__doctor --> la__contract
  la__leaks --> la__config
  la__leaks --> la__contract
  la__review --> la__contract
  classDef leaf fill:none;
  class trmv__contract,trmv__config,trmv__lang,trmv__twin,trmv__changes,trmv__typecheck,trmv__refactor,trmv__doctor,trmv__cli,la__contract,la__config,la__cli,la__c4,la__archcheck,la__conventions,la__review,la__doctor,la__affected,la__leaks leaf;
```
<!-- /likec4:system -->

<!-- likec4:npm -->
```mermaid
flowchart TD
  %% npm: npm twin
  subgraph trmv["type-rename-move"]
    trmv__contract["Shared contract"]
    trmv__config["Config"]
    trmv__lang["Language adapter"]
    trmv__twin["Twin forwarding"]
    trmv__changes["Change set"]
    trmv__typecheck["Type check"]
    trmv__refactor["Rename and move"]
    trmv__doctor["Doctor"]
    trmv__cli["CLI"]
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
    la__leaks["Leak check"]
  end
  la --> trmv
  trmv__changes --> trmv__config
  trmv__changes --> trmv__contract
  trmv__cli --> trmv__config
  trmv__cli --> trmv__doctor
  trmv__cli --> trmv__refactor
  trmv__cli --> trmv__twin
  trmv__cli --> trmv__typecheck
  trmv__config --> trmv__contract
  trmv__config --> trmv__twin
  trmv__doctor --> trmv__config
  trmv__doctor --> trmv__contract
  trmv__doctor --> trmv__twin
  trmv__lang --> trmv__contract
  trmv__refactor --> trmv__changes
  trmv__refactor --> trmv__config
  trmv__refactor --> trmv__contract
  trmv__refactor --> trmv__lang
  trmv__refactor --> trmv__twin
  trmv__twin --> trmv__contract
  trmv__typecheck --> trmv__changes
  trmv__typecheck --> trmv__config
  trmv__typecheck --> trmv__contract
  trmv__typecheck --> trmv__lang
  trmv__typecheck --> trmv__twin
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
  la__cli --> la__leaks
  la__cli --> la__review
  la__config --> la__contract
  la__conventions --> la__config
  la__conventions --> la__contract
  la__doctor --> la__config
  la__doctor --> la__contract
  la__leaks --> la__config
  la__leaks --> la__contract
  la__review --> la__contract
  classDef leaf fill:none;
  class trmv__contract,trmv__config,trmv__lang,trmv__twin,trmv__changes,trmv__typecheck,trmv__refactor,trmv__doctor,trmv__cli,la__contract,la__config,la__cli,la__c4,la__archcheck,la__conventions,la__review,la__doctor,la__affected,la__leaks leaf;
```
<!-- /likec4:npm -->

## Principles

1. Twins: every behaviour observable through a command is identical in both implementations for the
   languages they share, on every input in the forms the tools and docs write; the conformance corpus
   decides. [enforced: test:python/trmv/tests/test_conformance.py]
   [enforced: test:python/la/tests/test_conformance.py] [enforced: test:node/scripts/conformance.mjs]
2. Parameters, defaults, user-facing texts and command surfaces come only from the shared contracts. [review]
3. Language-specific code lives only in `trmv.lang` and `trmv.refactor`. [review]
4. Tools never import or execute target-repo code, except a configured command (`commands.*`). [review]
5. `trmv` never depends on `la`. [enforced: arch_check:model-truth]

## Rationale

Each ecosystem keeps native tooling: Python repos need no Node runtime for analysis and TS/JS repos need no
Python. Only the language-neutral core is implemented twice, so the shared contract and the conformance
corpus make drift a test failure instead of a review finding. The node split is the same in both twins, and
confining language-specific code to `lang` and `refactor` keeps everything else a straight port.

Verified renames and moves are useful without the architecture workflow, so they are their own package that la uses
as a library; the dependency runs one way so trmv installs and runs alone.
