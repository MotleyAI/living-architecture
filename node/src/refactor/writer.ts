// A refactor's apply: every file written or none.
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { chmodSync, closeSync, existsSync, lstatSync, mkdirSync, openSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, relative } from 'node:path';
import { byCodePoint, message } from '../contract/index.js';
import { RefactorError } from './edits.js';

/** A file's new text, with the text the refactor read it as. */
export interface Write {
  path: string;
  old: string;
  text: string;
}

function replace(path: string, text: string | Buffer): void {
  const temp = join(dirname(path), `.${basename(path)}.${randomBytes(8).toString('hex')}.la-tmp`);
  const fd = openSync(temp, 'wx', 0o600);
  try {
    try {
      writeFileSync(fd, text);
    } finally {
      closeSync(fd);
    }
    if (existsSync(path)) chmodSync(temp, statSync(path).mode & 0o7777);
    renameSync(temp, path);
  } catch (error) {
    rmSync(temp, { force: true });
    throw error;
  }
}

/** `path` exists as a file, directory or link, without following a link. */
const lexists = (path: string): boolean => lstatSync(path, { throwIfNoEntry: false }) !== undefined;

/** Git tracks `path` (inside the work tree at `root`). */
function tracked(root: string, path: string): boolean {
  const proc = spawnSync('git', ['ls-files', '--error-unmatch', '--', relative(root, path)], { cwd: root }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  return proc.status === 0;
}

/** `git mv` for a tracked file or directory, so the move is staged; else a rename. */
function move(root: string, from: string, to: string): void {
  if (tracked(root, from)) {
    const proc = spawnSync('git', ['mv', '--', relative(root, from), relative(root, to)], { cwd: root }); // NOSONAR(S4036) — runs the user's own git from PATH by design
    if (proc.status !== 0) throw new Error(`git mv ${from}`);
    return;
  }
  renameSync(from, to);
}

/** Undo every move and write, each attempted whatever failed before it; the paths left changed. */
function restore(root: string, originals: Map<string, Buffer>, written: string[], moved: [string, string][]): string[] {
  const left: string[] = [];
  for (const [original, current] of moved.toReversed()) {
    try {
      move(root, current, original);
    } catch {
      left.push(original);
    }
  }
  for (const path of written.toReversed()) {
    try {
      replace(path, originals.get(path) ?? '');
    } catch {
      left.push(path);
    }
  }
  return left;
}

/** Each file's bytes; RefactorError naming the first that changed since the refactor read it. */
function unchanged(writes: Write[], shown: (path: string) => string): Map<string, Buffer> {
  const originals = new Map<string, Buffer>();
  for (const { path, old } of writes) {
    const bytes = existsSync(path) ? readFileSync(path) : null;
    if (bytes === null || bytes.toString('utf8') !== old) throw new RefactorError(message('refactor.file-changed', { path: shown(path) }));
    originals.set(path, bytes);
  }
  return originals;
}

/** Write `writes` (in order) through same-directory temporary files, then apply `moves` under the project `root`;
 * RefactorError naming the changed file before anything is written, or the failed one after restoring what was
 * written. */
export function writeAll(root: string, writes: Write[], moves: [string, string][], shown: (path: string) => string): void {
  const originals = unchanged(writes, shown);
  const written: string[] = [];
  const moved: [string, string][] = [];
  let current = '';
  try {
    for (const { path, text } of writes) {
      current = path;
      replace(path, text);
      written.push(path);
    }
    for (const [from, to] of moves) {
      current = from;
      mkdirSync(dirname(to), { recursive: true });
      try {
        move(root, from, to);
      } catch (error) {
        if (!lexists(from) && lexists(to)) moved.push([from, to]);
        throw error;
      }
      moved.push([from, to]);
    }
  } catch {
    const left = restore(root, originals, written, moved).map(shown).sort(byCodePoint);
    if (left.length > 0) throw new RefactorError(message('refactor.rollback-failed', { path: shown(current), paths: left.join(', ') }));
    throw new RefactorError(message('refactor.write-failed', { path: shown(current) }));
  }
}
