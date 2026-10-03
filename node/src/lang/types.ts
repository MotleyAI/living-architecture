// The adapter's shared types.

/** A setup error the arch-check reports with exit 2 (the text after `arch_check: `). */
export class LangError extends Error {}

/** One TypeScript section of index.yaml, already validated by the arch-check. */
export interface TsLayout {
  /** Absolute repo root. */
  repoRoot: string;
  /** Absolute `<repoRoot>/<source_root>` (not realpath'd). */
  sourceRoot: string;
  /** The section's `root_package`, e.g. `src`. */
  rootPackage: string;
  /** The section's `tsconfig` (repo-relative), or null. */
  tsconfig: string | null;
}

export type UnitStatus =
  | { status: 'present' | 'missing'; candidates: [] }
  | { status: 'ambiguous'; candidates: string[] };

export interface ModuleImports {
  /** The source's module id (extensionless, relative to sourceRoot; `<dir>/index.<ext>` is `<dir>`). */
  module: string;
  /** Module ids of its runtime import targets under root_package (resolved, or lexical when unresolved relative). */
  targets: string[];
}
