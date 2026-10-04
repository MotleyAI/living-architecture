// `la-count-comments`: count comment and doc lines, per file or net added versus a git ref, every language.
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, posix } from 'node:path';
import { findRepoRoot } from '../config/index.js';
import { manifest, message } from '../contract/index.js';
import { collect, FactsError, type Facts, languageOf } from './facts.js';

const PROG = 'la-count-comments';

const out = (text: string): void => void process.stdout.write(`${text}\n`);
const err = (text: string): void => void process.stderr.write(`${text}\n`);

/** Python's `f"{n:+Wd}"` (signed) or `f"{n:Wd}"`. */
function pad(n: number, width: number, signed: boolean): string {
  const text = signed && n >= 0 ? `+${n}` : String(n);
  return text.padStart(width);
}

function usage(): number {
  process.stderr.write(`${manifest()[PROG].usage}\n`);
  return 2;
}

function known(paths: string[]): string[] {
  for (const path of paths) if (languageOf(path) === null) err(message('count-comments.unknown-extension', { path }));
  return paths.filter((path) => languageOf(path) !== null);
}

/** [comment, doc] lines; zeros for a missing or unreadable file. */
function counts(entry: Facts | undefined): [number, number] {
  return entry === undefined || !('comment_lines' in entry) ? [0, 0] : [entry.comment_lines, entry.doc_lines];
}

/** Write each path's bytes at `ref` under `tree`; the paths that exist there. */
function baseTree(ref: string, paths: string[], cwd: string, tree: string): string[] {
  const present: string[] = [];
  for (const path of paths) {
    if (posix.isAbsolute(path) || path.split('/').includes('..')) continue;
    const proc = spawnSync('git', ['show', `${ref}:${path}`], { cwd, maxBuffer: 1 << 30 });
    if (proc.status !== 0) continue;
    mkdirSync(dirname(join(tree, path)), { recursive: true });
    writeFileSync(join(tree, path), proc.stdout);
    present.push(path);
  }
  return present;
}

function printRange(ref: string, paths: string[], cwd: string, repoRoot: string): void {
  const head = collect(paths, cwd, repoRoot);
  const tree = mkdtempSync(join(tmpdir(), 'la-count-comments-'));
  let base: Map<string, Facts>;
  try {
    base = collect(baseTree(ref, paths, cwd, tree), tree, repoRoot);
  } finally {
    rmSync(tree, { recursive: true, force: true });
  }
  let tc = 0;
  let td = 0;
  for (const p of paths) {
    const [hc, hd] = counts(head.get(p));
    const [bc, bd] = counts(base.get(p));
    const [dc, dd] = [hc - bc, hd - bd];
    out(message('count-comments.file', { total: pad(dc + dd, 5, true), comment: pad(dc, 4, true), doc: pad(dd, 4, true), path: p }));
    tc += dc;
    td += dd;
  }
  out(message('count-comments.net-added', { total: tc + td, comment: tc, doc: td }));
}

function printFiles(paths: string[], cwd: string, repoRoot: string): void {
  const facts = collect(paths, cwd, repoRoot);
  let tc = 0;
  let td = 0;
  for (const p of paths) {
    const [c, d] = counts(facts.get(p));
    out(message('count-comments.file', { total: pad(c + d, 5, false), comment: pad(c, 4, false), doc: pad(d, 4, false), path: p }));
    tc += c;
    td += d;
  }
  out(message('count-comments.total', { total: tc + td, comment: tc, doc: td }));
}

/** Handler for raw argv: `FILE...` or `--range REF PATH...`. */
export function countComments(args: string[]): number {
  const ranged = args[0] === '--range';
  if ((ranged && args.length < 3) || args.length === 0) return usage();
  const cwd = process.cwd();
  const repoRoot = findRepoRoot(cwd);
  try {
    if (ranged) printRange(args[1] ?? '', known(args.slice(2)), cwd, repoRoot);
    else printFiles(known(args), cwd, repoRoot);
  } catch (error) {
    if (!(error instanceof FactsError)) throw error;
    if (error.message) err(message('twin.error', { prog: PROG, error: error.message }));
    return 2;
  }
  return 0;
}
