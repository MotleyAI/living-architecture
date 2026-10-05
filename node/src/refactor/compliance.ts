// `dr-compliance` and `dr-mock-lint` for TypeScript files: what would make a rename unverifiable.
import { relative, resolve } from 'node:path';
import type * as TS from 'typescript';
import { message } from '../contract/index.js';
import { findRepoRoot } from '../config/index.js';
import { posix, ts } from '../lang/index.js';
import { type Finding, mockFindings } from './mocks.js';
import { Workspace } from './workspace.js';

/** Implicit-any diagnostics of a parameter, a binding element and a rest parameter. */
const IMPLICIT_ANY = new Set([7006, 7031, 7019]);
const TSCONFIG_FLAGS = ['strict', 'noImplicitAny', 'noImplicitOverride'] as const;
const CHECKER_OPTIONS: TS.CompilerOptions = { noImplicitAny: true, allowJs: true, checkJs: true, noEmit: true };

function* walk(node: TS.Node): Generator<TS.Node> {
  yield node;
  for (const child of node.getChildren()) yield* walk(child);
}

/** The flags of a tsconfig's effective options that are not true (`noImplicitAny` defaults to `strict`). */
function disabledFlags(options: TS.CompilerOptions): string[] {
  const effective = { strict: options.strict, noImplicitAny: options.noImplicitAny ?? options.strict, noImplicitOverride: options.noImplicitOverride };
  return TSCONFIG_FLAGS.filter((flag) => effective[flag] !== true);
}

function untypedDefs(program: TS.Program, source: TS.SourceFile, shown: string): Finding[] {
  const names = new Map<number, string>();
  for (const node of walk(source)) {
    if (!ts().isParameter(node) && !ts().isBindingElement(node)) continue;
    if (!ts().isIdentifier(node.name)) continue;
    const rest = ts().isParameter(node) && node.dotDotDotToken !== undefined;
    names.set(rest ? node.getStart(source) : node.name.getStart(source), `${rest ? '...' : ''}${node.name.text}`);
  }
  return program
    .getSemanticDiagnostics(source)
    .filter((d) => IMPLICIT_ANY.has(d.code) && d.start !== undefined && names.has(d.start))
    .map((d) => {
      const position = d.start as number;
      const line = source.getLineAndCharacterOfPosition(position).line + 1;
      return { position, text: message('compliance.ts-untyped-def', { path: shown, line, name: names.get(position) }) };
    });
}

function fileFindings(program: TS.Program, source: TS.SourceFile, shown: string, selected: Set<string>, attr: string | null, repoRoot: string): Finding[] {
  const out: Finding[] = [];
  const line = (node: TS.Node): number => source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
  const checker = program.getTypeChecker();
  for (const node of walk(source)) {
    if (selected.has('explicit-any') && node.kind === ts().SyntaxKind.AnyKeyword) {
      out.push({ position: node.getStart(source), text: message('compliance.explicit-any', { path: shown, line: line(node) }) });
    }
    if (attr !== null && ts().isPropertyAccessExpression(node) && node.name.text === attr) {
      if ((checker.getTypeAtLocation(node.expression).flags & ts().TypeFlags.Any) !== 0) {
        const receiver = node.expression.getText(source);
        out.push({ position: node.getStart(source), text: message('compliance.ts-attr-blindspot', { path: shown, line: line(node), receiver, attr }) });
      }
    }
  }
  if (selected.has('untyped-def')) out.push(...untypedDefs(program, source, shown));
  if (selected.has('mock')) out.push(...mockFindings(program, source.fileName, shown, repoRoot));
  return out.sort((a, b) => a.position - b.position);
}

/** Every TypeScript finding of `paths` (relative to the working directory), in input order. */
export function typescriptCompliance(paths: string[], selected: Set<string>, attr: string | null): string[] {
  const repoRoot = findRepoRoot(process.cwd());
  const workspace = new Workspace(repoRoot);
  const files = paths.map((p) => resolve(p));
  const programs = workspace.programs(files, CHECKER_OPTIONS);
  const reported = new Set<string>();
  const out: string[] = [];
  for (const [i, file] of files.entries()) {
    const shown = paths[i] as string;
    const project = workspace.governing(file);
    if (selected.has('tsconfig') && project.config !== null && project.parsed !== null && !reported.has(project.config)) {
      reported.add(project.config);
      const config = posix(relative(process.cwd(), project.config));
      out.push(...disabledFlags(project.parsed.options).map((flag) => message('compliance.tsconfig', { path: config, flag })));
    }
    const program = programs.get(file) as TS.Program;
    const source = program.getSourceFile(file);
    if (source === undefined) continue;
    const [syntax] = program.getSyntacticDiagnostics(source);
    if (syntax !== undefined) {
      const line = source.getLineAndCharacterOfPosition(syntax.start ?? 0).line + 1;
      out.push(message('compliance.parse-error', { path: shown, line, error: ts().flattenDiagnosticMessageText(syntax.messageText, '\n') }));
      continue;
    }
    out.push(...fileFindings(program, source, shown, selected, attr, repoRoot).map((f) => f.text));
  }
  return out;
}

/** Every TypeScript mock-lint finding of `paths` (relative to the working directory), in input order. */
export function typescriptMockLint(paths: string[]): string[] {
  const repoRoot = findRepoRoot(process.cwd());
  const files = paths.map((p) => resolve(p));
  const programs = new Workspace(repoRoot).programs(files, { allowJs: true, noEmit: true });
  return files.flatMap((file, i) =>
    mockFindings(programs.get(file) as TS.Program, file, paths[i] as string, repoRoot)
      .sort((a, b) => a.position - b.position)
      .map((f) => f.text),
  );
}
