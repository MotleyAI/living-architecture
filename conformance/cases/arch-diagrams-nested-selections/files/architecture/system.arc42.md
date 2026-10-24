# System

<!-- likec4:nested -->
```mermaid
flowchart TD
  %% nested: Nested
  subgraph api__handlers["Handlers"]
    api__handlers__x["X"]
  end
  classDef leaf fill:none;
  class api__handlers__x leaf;
```
<!-- /likec4:nested -->

<!-- likec4:overlap -->
```mermaid
flowchart TD
  %% overlap: Overlap
  subgraph api["API"]
    subgraph api__handlers["Handlers"]
      api__handlers__x["X"]
    end
    api__other["Other"]
  end
  classDef leaf fill:none;
  class api__handlers__x,api__other leaf;
```
<!-- /likec4:overlap -->

<!-- likec4:anchored -->
```mermaid
flowchart TD
  %% anchored: Anchored
  subgraph api["API"]
    subgraph api__handlers["Handlers"]
      api__handlers__x["X"]
    end
  end
  subgraph core["Core"]
    subgraph core__store["Store"]
      core__store__sql["SQL"]
    end
  end
  api__handlers__x --> core__store__sql
  api__handlers --> core
  classDef leaf fill:none;
  class api__handlers__x,core__store__sql leaf;
```
<!-- /likec4:anchored -->

<!-- likec4:inbound -->
```mermaid
flowchart TD
  %% inbound: Inbound
  api["API"]
  core["Core"]
  api --> core
```
<!-- /likec4:inbound -->

<!-- likec4:descend -->
```mermaid
flowchart TD
  %% descend: Descend
  subgraph api["API"]
    api__other["Other"]
  end
  core["Core"]
  api__other --> core
  classDef leaf fill:none;
  class api__other,core leaf;
```
<!-- /likec4:descend -->

<!-- likec4:flat -->
```mermaid
flowchart TD
  %% flat: Flat
  api__handlers["Handlers"]
  core__store["Store"]
  api__handlers --> core__store
```
<!-- /likec4:flat -->
