// OS errors rendered from the shared os.* templates, the one existence probe, and the path-carrying file read.
// eslint-disable-next-line no-restricted-imports -- the one place target-repo files are read from
import { readFileSync, statSync } from 'node:fs';
import { isAbsolute, relative, resolve, sep } from 'node:path';
import { message } from './render.js';

const REASONS: Record<string, string> = {
  ENOENT: 'os.not-found',
  EACCES: 'os.permission-denied',
  EISDIR: 'os.is-a-directory',
  ENOTDIR: 'os.not-a-directory',
};

function field(error: unknown, key: string): unknown {
  return error !== null && typeof error === 'object' ? (error as Record<string, unknown>)[key] : undefined;
}

/** Whether `error` is an OS error: it carries an errno-style symbolic code (not Node's own `ERR_*`). */
export function isOsError(error: unknown): error is NodeJS.ErrnoException {
  const code = field(error, 'code');
  return error instanceof Error && typeof code === 'string' && /^E[A-Z0-9]+$/.test(code);
}

/** The reason alone, chosen by the error's symbolic code. */
export function osErrorReason(error: unknown): string {
  const code = field(error, 'code');
  const id = typeof code === 'string' ? REASONS[code] : undefined;
  if (id !== undefined) return message(id);
  return message('os.other', { code: typeof code === 'string' ? code : 'unknown' });
}

/** `path` relative to `root` with `/` separators when lexically under it, else absolute. */
export function displayPath(path: string, root: string): string {
  const full = resolve(path);
  const rel = relative(resolve(root), full);
  if (rel === '') return '.';
  if (rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel)) return full;
  return rel.split(sep).join('/');
}

/** `{path}: {reason}` for the site's path, else the error's own; the reason alone when there is neither. */
export function osErrorText(error: unknown, root: string, path?: string): string {
  const own = field(error, 'path');
  const shown = path ?? (typeof own === 'string' ? own : undefined);
  const reason = osErrorReason(error);
  return shown === undefined ? reason : message('os.error', { path: displayPath(shown, root), reason });
}

/** True for a regular file, false when missing or not regular; any other stat error propagates. */
export function isRegularFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch (error) {
    if (field(error, 'code') === 'ENOENT') return false;
    throw error;
  }
}

/** `readFileSync` whose error always carries `path`. */
export function readFile(path: string): Buffer;
export function readFile(path: string, encoding: 'utf8'): string;
export function readFile(path: string, encoding?: 'utf8'): Buffer | string {
  try {
    return encoding === undefined ? readFileSync(path) : readFileSync(path, encoding);
  } catch (error) {
    if (error !== null && typeof error === 'object' && typeof field(error, 'path') !== 'string') {
      Object.assign(error, { path });
    }
    throw error;
  }
}
