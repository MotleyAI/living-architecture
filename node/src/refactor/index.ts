// The `dr-*` commands: TypeScript refactors and lints natively, the other language's inputs in its twin.
import { ConfigError, findRepoRoot } from '../config/index.js';
import { basePaths, mergeBase, pathsAt, resolveBaseRef } from '../changes/index.js';
import { language, languageIds, languageOf, message } from '../contract/index.js';
import * as twin from '../twin/index.js';
import { type MockBase, typescriptCompliance, typescriptMockLint } from './compliance.js';
import { complianceSelection, languageFiles, realPath, refactorLanguage, RoutingError, runSplit, split, under } from './routing.js';
import { RefactorError } from './edits.js';
import { entrySource, loadMap, MapError } from './map.js';
import { report } from './timings.js';
import { type RefactorArgs, runTypescriptRefactor } from './typescript.js';
import { loadWordTable } from './words.js';

export { unifiedDiff } from './diff.js';
export { mergeEdits, RefactorError } from './edits.js';
export type { RefactorArgs } from './typescript.js';

const print = (lines: string[]): number => {
  for (const line of lines) process.stdout.write(`${line}\n`);
  return lines.length > 0 ? 1 : 0;
};

/** The native block's findings printed (exit 1 if any); a tsconfig that cannot be loaded is reported, exit 2. */
function native(findings: () => string[]): number {
  try {
    return print(findings());
  } catch (error) {
    if (!(error instanceof RefactorError)) throw error;
    process.stderr.write(`${error.message}\n`);
    return 2;
  }
}

/** The one language of a map's entries, by their files' or modules' extensions; MapError for an invalid map or several
 * languages. */
function mapLanguage(map: string): string {
  const files = loadMap(map, map).map(entrySource);
  const unsupported = files.find((file) => languageOf(file) === null);
  if (unsupported !== undefined) throw new RoutingError(message('refactor.unsupported-extension', { path: unsupported }));
  const languages = languageIds().filter((id) => files.some((file) => languageOf(file) === id));
  if (languages.length > 1) throw new MapError(message('refactor.map-mixed-languages', { map, languages: languages.join(', ') }));
  return languages[0] ?? '';
}

/** The language `generate-map` generates for: `--language`, else the one language with sources under the project (this
 * twin's when there is none); MapError when the project holds several. */
function generateLanguage(args: RefactorArgs): string {
  if (args.language !== undefined) return args.language;
  const root = realPath(under(process.cwd(), args.project));
  const found = languageIds().filter((id) => languageFiles(root, id).length > 0);
  if (found.length > 1) throw new MapError(message('refactor.generate-language', { languages: found.join(', ') }));
  return found[0] ?? twin.NATIVE_LANGUAGE;
}

/** The language a run is of: a word table is checked first, then the map's, the generated or the source's language. */
function runLanguage(args: RefactorArgs): string {
  const table = args.subcommand === 'generate-map' ? args.table : args.words;
  if (table !== undefined) loadWordTable(table, table);
  if (args.subcommand === 'generate-map') return generateLanguage(args);
  if (args.subcommand === 'rename-map') return mapLanguage(args.map ?? '');
  const source = args.subcommand === 'move-module' ? args.module : args.file;
  return refactorLanguage(args.subcommand, source ?? '', args.dest ?? '', args.project);
}

/** `dr-refactor`: run natively, or hand the raw ARGV to the source language's twin; with `--timings`, the phase
 * times follow, unless the other twin ran and printed its own. */
export function runRefactor(argv: string[], args: RefactorArgs): number {
  return report(args.timings === true, (scope) => {
    let id: string;
    try {
      id = runLanguage(args);
    } catch (error) {
      if (!(error instanceof RoutingError) && !(error instanceof MapError)) throw error;
      process.stderr.write(`${error.message}\n`);
      return error instanceof MapError ? 2 : 1;
    }
    if (id === twin.NATIVE_LANGUAGE) return runTypescriptRefactor(args);
    let code: number;
    try {
      code = twin.forward('dr-refactor', id, argv, findRepoRoot(process.cwd()));
    } catch (error) {
      if (!(error instanceof twin.TwinError)) throw error;
      process.stderr.write(`${message('twin.error', { prog: 'dr-refactor', error: error.message })}\n`);
      return 2;
    }
    scope.cancel();
    return code;
  });
}

/** `dr-compliance`: each file with its language's checks, the other language's in its twin. */
export function runCompliance(paths: string[], select: string | null, attrs: string[]): number {
  let selected: Set<string> | null;
  let groups: Map<string, string[]>;
  try {
    selected = complianceSelection(select);
    if (selected?.has('attr-blindspot') === true && attrs.length === 0) throw new RoutingError(message('compliance.attr-required'));
    if (selected !== null && !selected.has('attr-blindspot') && attrs.length > 0) throw new RoutingError(message('compliance.attr-unselected'));
    groups = split('dr-compliance', paths);
  } catch (error) {
    if (!(error instanceof RoutingError)) throw error;
    process.stderr.write(`${error.message}\n`);
    return 2;
  }
  const options = [...(select !== null ? ['--select', select] : []), ...attrs.flatMap((attr) => ['--attr', attr])];
  const checks: string[] = language(twin.NATIVE_LANGUAGE).compliance_checks;
  const own = new Set(checks.filter((check) => selected === null || selected.has(check)));
  return runSplit('dr-compliance', groups, (files) => [...options, '--', ...files], (files) => native(() => typescriptCompliance(files, own, attrs)));
}

/** The merge base of origin/`branch` and HEAD, the paths tracked there and those renamed since. */
function mockBase(branch: string): MockBase {
  const repoRoot = findRepoRoot(process.cwd());
  const commit = mergeBase(resolveBaseRef(branch, repoRoot), repoRoot);
  return { commit, tracked: pathsAt(commit, repoRoot), renamed: basePaths(commit, repoRoot) };
}

/** `dr-mock-lint`: each file linted in its language's twin; with `base`, only the findings the base lacks. */
export function runMockLint(paths: string[], base: string | null): number {
  let groups: Map<string, string[]>;
  let compared: MockBase | null = null;
  try {
    groups = split('dr-mock-lint', paths);
    if (base !== null && groups.has(twin.NATIVE_LANGUAGE)) compared = mockBase(base);
  } catch (error) {
    if (!(error instanceof RoutingError) && !(error instanceof ConfigError)) throw error;
    process.stderr.write(`${error.message}\n`);
    return 2;
  }
  const options = base === null ? [] : ['--base', base];
  return runSplit('dr-mock-lint', groups, (files) => [...options, '--', ...files], (files) => native(() => typescriptMockLint(files, compared)));
}
