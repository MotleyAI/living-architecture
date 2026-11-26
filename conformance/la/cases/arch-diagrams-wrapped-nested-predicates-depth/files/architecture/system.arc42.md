# System

1. Handlers reach the store only through core. [enforced: arch_check:model-truth]

<!-- likec4:inbound -->
```mermaid
flowchart TD
  %% inbound: Into core
  subgraph api["API"]
    api__handlers["Handlers"]
  end
  core["Core"]
  legacy("Legacy")
  api__handlers --> core
  legacy --> core
  classDef leaf fill:none;
  class api__handlers,core,legacy leaf;
```
<!-- /likec4:inbound -->

<!-- likec4:deep -->
```mermaid
flowchart TD
  %% deep: Deep
  subgraph api["API"]
    subgraph api__handlers["Handlers"]
      api__handlers__x["X"]
    end
  end
  store["Store"]
  api -.-> store
  api__handlers__x -.-> store
  classDef leaf fill:none;
  class api__handlers__x,store leaf;
```
*Dashed arrows: legacy edges slated to die.*
<!-- /likec4:deep -->

<!-- likec4:outbound -->
```mermaid
flowchart TD
  %% outbound: API out
  api["API"]
  core["Core"]
  store["Store"]
  api --> core
  api -.-> store
```
*Dashed arrows: legacy edges slated to die.*
<!-- /likec4:outbound -->
