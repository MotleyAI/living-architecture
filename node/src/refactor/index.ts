// The `dr-*` commands: TypeScript refactors and lints natively, the other language's inputs in its twin.
import { ConfigError, findRepoRoot } from '../config/index.js';
import { basePaths, mergeBase, pathsAt, resolveBaseRef } from '../changes/index.js';
import { language, message } from '../contract/index.js';
import * as twin from '../twin/index.js';
import { type MockBase, typescriptCompliance, typescriptMockLint } from './compliance.js';
import { complianceSelection, refactorLanguage, RoutingError, runSplit, split } from './routing.js';
import { RefactorError } from './edits.js';
import { type RefactorArgs, runTypescriptRefactor } from './typescript.js';

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

/** `dr-refactor`: run natively, or hand the raw ARGV to the source language's twin. */
export function runRefactor(argv: string[], args: RefactorArgs): number {
  let id: string;
  try {
    const source = args.subcommand === 'move-module' ? args.module : args.file;
    id = refactorLanguage(args.subcommand, source ?? '', args.dest ?? '', args.project);
  } catch (error) {
    if (!(error instanceof RoutingError)) throw error;
    process.stderr.write(`${error.message}\n`);
    return 1;
  }
  if (id === twin.NATIVE_LANGUAGE) return runTypescriptRefactor(args);
  try {
    return twin.forward('dr-refactor', id, argv, findRepoRoot(process.cwd()));
  } catch (error) {
    if (!(error instanceof twin.TwinError)) throw error;
    process.stderr.write(`${message('twin.error', { prog: 'dr-refactor', error: error.message })}\n`);
    return 2;
  }
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
