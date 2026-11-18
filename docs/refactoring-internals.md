# Inside dr-refactor

Which libraries and processes `dr-refactor` (and `dr-compliance --attr`) use, and what each one is for. For what
the commands do, see [Deterministic refactoring](deterministic-refactoring.md).

## Python twin

```mermaid
flowchart LR
  cmd["dr-refactor / dr-compliance --attr"]
  subgraph la["living-architecture (Python)"]
    rules["rules: references, hierarchy, stand-ins,<br/>blind spots, keyed keys, keyword links,<br/>**kwargs carriers, string members,<br/>targets, --docs mentions"]
    client["LSP client<br/>(lang/language_server.py)"]
    cache[("occurrence index cache<br/>LA_CACHE_DIR")]
    stdlib["stdlib ast / tokenize<br/>(text rules, edit placement)"]
    writer["diff + all-or-nothing writer"]
    static["la's static resolver"]
  end
  rope["rope + la's walker patches"]
  subgraph node["node (nodejs-wheel-binaries)"]
    ls["basedpyright language server"]
    patch["preload: pyright#11919 fix"]
    export["preload: la.exportOccurrences"]
  end
  checker["project's checker<br/>(commands.typecheck.python)"]

  cmd --> rope
  cmd --> rules
  rules --> cache
  rules --> client
  client -- "LSP over stdio" --> ls
  patch -.-> ls
  export -.-> ls
  rules --> static
  rules --> stdlib
  rules --> writer
  writer --> checker
```

| Component | Used for | Needed because |
|---|---|---|
| basedpyright (bundled, pinned) | The occurrence index: every occurrence of each old name with its declarations, class, MRO and receiver type. Also the `Literal`, string-member and keyword-signature probes. | It is the type checker the gate trusts. A rename resolved by the checker that later verifies it can't disagree with it. |
| Node (`nodejs-wheel-binaries`) | Runs basedpyright, which is a Node program. | basedpyright's own dependency. The project needs no Node. |
| LSP | The protocol la uses to talk to one long-lived basedpyright process. la's client is about 350 lines. | It's the only stable host for basedpyright's analysis. The server finds the project's configuration and interpreter itself, takes in-memory file texts (the snapshot and the probes), and keeps one warm program for the whole run. |
| la's preloads | Patch basedpyright's bundle as Node loads it: the pyright#11919 fix, and the export command that returns the whole index in one request. | basedpyright has no batch export (requested upstream as basedpyright#1909). Both are pinned to verified versions; any other version refuses. |
| rope (+ la's walker patches) | Computes `move-symbol` and `move-module`. | Moves are built on it. |
| la's static resolver | Resolves names, imports and module attribute chains by Python's scoping over the project's source folders: entry locations, the names basedpyright leaves unresolved, retarget's lookups and module renames. | It reads files only, so it resolves what the checker's configuration misses without running project code. |
| stdlib `ast` / `tokenize` | Edit placement, `--docs` mentions, compound names, dict-key and keyword shapes. | These rules read text and syntax only. |
| Occurrence index cache | Reuses the index when nothing that can change it has changed (sources, config, interpreter, packages, request). | It makes the dry-run → fix flags → re-run loop cost no checker time. |
| The project's checker | Keeps the type-check baseline aligned after the edits. | The baseline belongs to the checker the project configures, not to la's bundled one. |

A run locates each map entry from the syntax tree and la's static resolver first. Then it reads the index from the cache, or exports it in one
request, and runs every rule over it. Finally it prints one diff and, with `--apply`, writes every file or none.
Module renames and moves never start the language server.

A call keyword `old=` the checker resolves to no declaration of that name is linked in one of two ways. A parameter
rename asks the checker for the callee's signature again, with the renamed parameters renamed in memory: the keyword
follows when every callable alternative binds the old name before and the new name after. A `**kwargs` carrier (a
`def` whose `**kw` only reaches calls it is unpacked into, key lookups and truth tests) passes the keyword on to what
it builds: a keyed class, a function, a constructor or another carrier. A keyword proved to land on another
declaration, or on none, is left alone. Any other keyword neither rule links (a callee whose signature does not bind
the name, a carrier whose flow is mixed or unprovable), and one on a callee typed `Unknown`, `Any` or `Never`, is an
`unlinked-keyword` blind spot of a parameter or field rename.

## TypeScript twin

The npm twin uses only the bundled `typescript` package. Its in-process language service locates symbols, finds
references and rename locations, types receivers, and keeps the baseline aligned. There's no second process, no
protocol and no second resolver.
