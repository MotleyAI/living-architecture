# Support multiple root packages per language

Living Architecture currently assumes one `root_package` per language section. Repositories such as Operalta place
owned source across several top-level directories, so they cannot enable the strict architecture checker without
pretending the repository root is one package. Add a backward-compatible `root_packages` list and make source
discovery, unit checks and import measurement cover its roots as one language-wide surface in both twins.

## Non-goals

- Changing LikeC4 node mapping notation or allowing a node to claim multiple packages through a new syntax.
- Following source outside `source_root`, changing import resolution, or adding cross-language import edges.
- Migrating an adopting repository as part of this change.
- Several import roots per language: every root of a section shares its one `source_root`.
