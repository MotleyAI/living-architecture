// Temp TypeScript projects for the dr-refactor CLI tests, and the output they are expected to print.
import { execFileSync } from 'node:child_process';
import { cpSync, mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { currentFormat } from '../src/config/index.js';
import { byCodePoint, message } from '../src/contract/index.js';
import { unifiedDiff } from '../src/refactor/index.js';
import { run, tempRepo, type Run } from './cli-run.js';
import { tree } from './helpers.js';

export const TSCONFIG = `${JSON.stringify(
  {
    compilerOptions: { target: 'es2022', module: 'esnext', moduleResolution: 'bundler', strict: true, noImplicitOverride: true, noEmit: true },
    include: ['src'],
  },
  null,
  2,
)}\n`;

/** A git repo with a strict tsconfig over `src`, the current format and `config` appended to the repo config. */
export function tsProject(files: Record<string, string>, config = ''): string {
  return tempRepo({ 'tsconfig.json': TSCONFIG, 'living-architecture.yaml': `format: ${currentFormat()}\n${config}`, ...files });
}

/** A copy of `root` in a fresh temp directory. */
export function copyProject(root: string): string {
  const copy = join(mkdtempSync(join(tmpdir(), 'la-copy-')), 'repo');
  cpSync(root, copy, { recursive: true });
  return copy;
}

export const refactor = (root: string, ...argv: string[]): Run => run(root, 'dr-refactor', argv);

export const read = (root: string, rel: string): string => readFileSync(join(root, rel), 'utf8');

/** Every file outside `.git`, as relative path -> text. */
export function files(root: string): Record<string, string> {
  return Object.fromEntries(
    Object.entries(tree(root))
      .filter(([rel]) => !rel.startsWith('.git/'))
      .map(([rel, [, bytes]]) => [rel, bytes.toString('utf8')]),
  );
}

/** The 1-based line and column of the `nth` occurrence of `needle` in `rel`, plus `shift` columns. */
export function lineCol(root: string, rel: string, needle: string, nth = 0, shift = 0): string[] {
  const text = read(root, rel);
  let index = -1;
  for (let i = 0; i <= nth; i += 1) index = text.indexOf(needle, index + 1);
  if (index < 0) throw new Error(`${needle} not found in ${rel}`);
  const before = text.slice(0, index).split('\n');
  return ['--line', String(before.length), '--col', String((before.at(-1) ?? '').length + 1 + shift)];
}

export interface Change {
  path: string;
  old: string;
  new: string;
}

/** What dr-refactor prints: the headers, one diff per change in path order, then the footer. */
export function expectedOut(headers: string[], changes: Change[], apply: boolean): string {
  const sorted = changes.toSorted((a, b) => byCodePoint(a.path, b.path));
  const body = sorted.map((c) => `${unifiedDiff(c.old, c.new, c.path)}\n`).join('');
  const applied = sorted.map((c) => `${message('refactor.applied-file', { path: c.path })}\n`).join('');
  const footer = apply ? `${message('refactor.applied', { count: sorted.length })}\n${applied}` : `${message('refactor.dry-run', { count: sorted.length })}\n`;
  return `${headers.join('\n')}\n\n\n${body}\n${footer}`;
}

export const renameHeader = (old: string, next: string): string => message('refactor.ts-rename-header', { old, new: next });

/** A rename map file: one `{key: value}` mapping per entry. */
export function mapYaml(entries: Record<string, string | number>[]): string {
  return entries
    .map((entry) =>
      Object.entries(entry)
        .map(([key, value], i) => `${i === 0 ? '- ' : '  '}${key}: ${typeof value === 'number' ? value : JSON.stringify(value)}`)
        .join('\n'),
    )
    .join('\n')
    .concat('\n');
}

/** `.tsc-baseline.json` as la-typecheck writes it, from `[file, code, message, count]` keys. */
export function tscBaseline(keys: [string, string, string, number][]): string {
  const sorted = keys.toSorted((a, b) => byCodePoint(a[0], b[0]) || byCodePoint(a[1], b[1]) || byCodePoint(a[2], b[2]));
  const out: Record<string, { code: string; message: string; count: number }[]> = {};
  for (const [file, code, msg, count] of sorted) {
    out[file] = [...(out[file] ?? []), { code, message: msg, count }];
  }
  return `${JSON.stringify({ files: out }, null, 2)}\n`;
}

/** Commit everything in `root`. */
export function commitAll(root: string, msg = 'init'): void {
  execFileSync('git', ['add', '-A'], { cwd: root }); // NOSONAR(S4036) — test helper runs the developer's git from PATH
  execFileSync('git', ['-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', msg], { cwd: root }); // NOSONAR(S4036) — test helper runs the developer's git from PATH
}
