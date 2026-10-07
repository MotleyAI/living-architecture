// The `dr-*` commands: TypeScript refactors and lints natively, the other language's inputs in its twin.
import { findRepoRoot } from '../config/index.js';
import { language, manifest, message } from '../contract/index.js';
import * as twin from '../twin/index.js';
import { typescriptCompliance, typescriptMockLint } from './compliance.js';
import { complianceSelection, refactorLanguage, RoutingError, runSplit, split } from './routing.js';
import { type RefactorArgs, runTypescriptRefactor } from './typescript.js';

export { unifiedDiff } from './diff.js';
export { mergeEdits, RefactorError } from './edits.js';
export type { RefactorArgs } from './typescript.js';

const print = (lines: string[]): number => {
  for (const line of lines) process.stdout.write(`${line}\n`);
  return lines.length > 0 ? 1 : 0;
};

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
export function runCompliance(paths: string[], select: string | null, attr: string | null): number {
  let selected: Set<string> | null;
  let groups: Map<string, string[]>;
  try {
    selected = complianceSelection(select);
    groups = split('dr-compliance', paths);
  } catch (error) {
    if (!(error instanceof RoutingError)) throw error;
    process.stderr.write(`${error.message}\n`);
    return 2;
  }
  const options = [...(select !== null ? ['--select', select] : []), ...(attr !== null ? ['--attr', attr] : [])];
  const checks: string[] = language(twin.NATIVE_LANGUAGE).compliance_checks;
  const own = new Set(checks.filter((check) => selected === null || selected.has(check)));
  return runSplit('dr-compliance', groups, (files) => [...options, '--', ...files], (files) => print(typescriptCompliance(files, own, attr)));
}

/** `dr-mock-lint` with raw argv: paths to files or directories, each file linted in its language's twin. */
export function runMockLint(argv: string[]): number {
  if (argv.length === 0) {
    process.stderr.write(`usage: ${manifest()['dr-mock-lint'].usage}\n`);
    return 2;
  }
  let groups: Map<string, string[]>;
  try {
    groups = split('dr-mock-lint', argv);
  } catch (error) {
    if (!(error instanceof RoutingError)) throw error;
    process.stderr.write(`${error.message}\n`);
    return 2;
  }
  return runSplit('dr-mock-lint', groups, (files) => files, (files) => print(typescriptMockLint(files)));
}
