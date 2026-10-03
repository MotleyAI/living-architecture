// The TypeScript language adapter: units, import edges and conventions facts (TypeScript 6.0 API), the tsc ratchet.
import { Tree } from './files.js';
import type { TsLayout, UnitStatus } from './types.js';

export { conventionsFacts, type ConventionsFileFacts, type Detection } from './conventions.js';
export { moduleImports } from './imports.js';
export { checkTypescript, parseTscOutput, type TscDiagnostic, type TscRun } from './tsc.js';
export { LangError, type ModuleImports, type TsLayout, type UnitStatus } from './types.js';

/** Whether `unit` (a sourceRoot-relative extensionless path) is present, missing or ambiguous (sorted candidates). */
export function unitStatus(layout: TsLayout, unit: string): UnitStatus {
  return new Tree(layout).unitStatus(unit);
}

/** The top-level units under root_package, sorted. */
export function topLevelUnits(layout: TsLayout): string[] {
  return new Tree(layout).topLevelUnits();
}
