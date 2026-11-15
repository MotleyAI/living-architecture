// `dr-compliance` and `dr-mock-lint` for TypeScript files: what would make a rename unverifiable.
import { relative, resolve } from 'node:path';
import type * as TS from 'typescript';
import { language, message } from '../contract/index.js';
import { findRepoRoot } from '../config/index.js';
import { posix, ts } from '../lang/index.js';
import { Lines } from './lines.js';
import { anyReceivers } from './members.js';
import { type Finding, type MockFinding, mockFindings } from './mocks.js';
import { fileAt, repoPathBytes } from '../changes/index.js';
import { listingOf, Workspace } from './workspace.js';

/** Implicit-any diagnostics of a parameter, a binding element and a rest parameter. */
const IMPLICIT_ANY = new Set([7006, 7031, 7019]);
const TSCONFIG_FLAGS = ['strict', 'noImplicitAny', 'noImplicitOverride'] as const;
export const CHECKER_OPTIONS: TS.CompilerOptions = { noImplicitAny: true, allowJs: true, checkJs: true, noEmit: true };

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
  const lines = new Lines(source.text);
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
      const line = lines.lineOf(position);
      return { position, text: message('compliance.ts-untyped-def', { path: shown, line, name: names.get(position) }) };
    });
}

function fileFindings(program: TS.Program, source: TS.SourceFile, shown: string, selected: Set<string>, attrs: string[], repoRoot: string): Finding[] {
  const out: Finding[] = [];
  const lines = new Lines(source.text);
  const line = (node: TS.Node): number => lines.lineOf(node.getStart(source));
  const checker = program.getTypeChecker();
  const { any_type: any, top_type: top } = language('typescript');
  for (const node of walk(source)) {
    if (selected.has('explicit-any') && node.kind === ts().SyntaxKind.AnyKeyword) {
      out.push({ position: node.getStart(source), text: message('compliance.explicit-any', { path: shown, line: line(node), any, top }) });
    }
  }
  for (const attr of new Set(attrs)) {
    for (const { position, receiver } of anyReceivers(checker, source, attr)) {
      const at = lines.lineOf(position);
      out.push({ position, text: message('compliance.attr-blindspot', { path: shown, line: at, receiver, attr, type: 'any' }) });
    }
  }
  if (selected.has('untyped-def')) out.push(...untypedDefs(program, source, shown));
  if (selected.has('mock')) out.push(...mockFindings(program, source.fileName, shown, repoRoot));
  return out.sort((a, b) => a.position - b.position);
}

/** Every TypeScript finding of `paths` (relative to the working directory), in input order. */
export function typescriptCompliance(paths: string[], selected: Set<string>, attrs: string[]): string[] {
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
      const line = new Lines(source.text).lineOf(syntax.start ?? 0);
      out.push(message('compliance.parse-error', { path: shown, line, error: ts().flattenDiagnosticMessageText(syntax.messageText, '\n') }));
      continue;
    }
    out.push(...fileFindings(program, source, shown, selected, attrs, repoRoot).map((f) => f.text));
  }
  return out;
}

const MOCK_OPTIONS: TS.CompilerOptions = { allowJs: true, noEmit: true };

/** The merge base a `--base` run compares with: its commit, the paths tracked there and those renamed since. */
export interface MockBase {
  commit: string;
  tracked: Set<string>;
  renamed: Map<string, string>;
}

/** The findings of `current` beyond the base's count of their key, the earliest lines taken as the base's. */
function added(current: MockFinding[], base: MockFinding[]): MockFinding[] {
  const left = new Map<string, number>();
  for (const f of base) left.set(f.key, (left.get(f.key) ?? 0) + 1);
  const kept = new Set<MockFinding>();
  for (const f of current.toSorted((a, b) => a.line - b.line)) {
    const n = left.get(f.key) ?? 0;
    if (n > 0) left.set(f.key, n - 1);
    else kept.add(f);
  }
  return current.filter((f) => kept.has(f));
}

/** Each file's findings at the base: a program over the tracked files as they are there, each file read at its base path. */
function baseFindings(files: string[], paths: string[], repoRoot: string, base: MockBase): MockFinding[][] {
  const rel = (path: string): string => posix(relative(repoRoot, path));
  const current = new Set(repoPathBytes(repoRoot).map((p) => p.toString('utf8')));
  const blobs = new Map<string, string | null>();
  const blob = (name: string): string | null => {
    if (!blobs.has(name)) blobs.set(name, fileAt(base.commit, name, repoRoot)?.toString('utf8') ?? null);
    return blobs.get(name) ?? null;
  };
  const overlay = (path: string): string | null | undefined => {
    const name = rel(path);
    if (name.startsWith('../') || (!base.tracked.has(name) && !current.has(name))) return undefined;
    return base.tracked.has(name) ? blob(name) : null;
  };
  const baseFiles = files.map((file) => resolve(repoRoot, base.renamed.get(rel(file)) ?? rel(file)));
  const present = baseFiles.filter((file) => base.tracked.has(rel(file)));
  const workspace = new Workspace(repoRoot, overlay, new Map(), listingOf(repoRoot, base.tracked));
  const programs = workspace.programs(present, MOCK_OPTIONS);
  const host = workspace.resolutionHost();
  return baseFiles.map((file, i) => {
    const program = programs.get(file);
    return program === undefined ? [] : mockFindings(program, file, paths[i] as string, repoRoot, host);
  });
}

/** Every TypeScript mock-lint finding of `paths` (relative to the working directory), in input order; with `base`,
 * only those the base lacks. */
export function typescriptMockLint(paths: string[], base: MockBase | null): string[] {
  const repoRoot = findRepoRoot(process.cwd());
  const files = paths.map((p) => resolve(p));
  const programs = new Workspace(repoRoot).programs(files, MOCK_OPTIONS);
  const found = files.map((file, i) => mockFindings(programs.get(file) as TS.Program, file, paths[i] as string, repoRoot).sort((a, b) => a.position - b.position));
  const flagged = base === null ? [] : found.flatMap((f, i) => (f.length > 0 ? [i] : []));
  const before = base === null || flagged.length === 0 ? [] : baseFindings(flagged.map((i) => files[i] as string), flagged.map((i) => paths[i] as string), repoRoot, base);
  const baseOf = new Map(flagged.map((i, k) => [i, before[k] ?? []]));
  return found.flatMap((f, i) => {
    const prior = baseOf.get(i);
    return (prior === undefined ? f : added(f, prior)).map((x) => x.text);
  });
}
