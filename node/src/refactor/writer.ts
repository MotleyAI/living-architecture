// A refactor's apply: every file written or none.
import { chmodSync, existsSync, mkdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';
import { message } from '../contract/index.js';
import { RefactorError } from './edits.js';

/** A file's new text, with the text the refactor read it as. */
export interface Write {
  path: string;
  old: string;
  text: string;
}

function replace(path: string, text: string | Buffer): void {
  const temp = join(dirname(path), `.${basename(path)}.dr-refactor-${process.pid}`);
  try {
    writeFileSync(temp, text);
    if (existsSync(path)) chmodSync(temp, statSync(path).mode & 0o7777);
    renameSync(temp, path);
  } catch (error) {
    rmSync(temp, { force: true });
    throw error;
  }
}

/** Write `writes` (in order) through same-directory temporary files, then apply `moves`; RefactorError naming the
 * changed file before anything is written, or the failed one after restoring what was written. */
export function writeAll(writes: Write[], moves: [string, string][], shown: (path: string) => string): void {
  const originals = new Map<string, Buffer>();
  for (const { path, old } of writes) {
    const bytes = existsSync(path) ? readFileSync(path) : null;
    if (bytes === null || bytes.toString('utf8') !== old) throw new RefactorError(message('refactor.file-changed', { path: shown(path) }));
    originals.set(path, bytes);
  }
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
      current = to;
      mkdirSync(dirname(to), { recursive: true });
      renameSync(from, to);
      moved.push([from, to]);
    }
  } catch {
    for (const [from, to] of moved.reverse()) renameSync(to, from);
    for (const path of written) replace(path, originals.get(path) ?? '');
    throw new RefactorError(message('refactor.write-failed', { path: shown(current) }));
  }
}
