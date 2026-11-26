// The stealth merge-base baseline cache: its key and its entries under the trmv stealth directory.
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';
import { byCodePoint, isRegularFile, language, readFile } from '../contract/index.js';

export interface CacheKeyInput {
  commit: string;
  language: string;
  command: string;
  version: string;
  fingerprints: Map<string, Buffer>;
}

const sha256 = (data: Uint8Array | string): string => createHash('sha256').update(data).digest('hex');

/** The hex sha256 of the merge-base commit, the language, the checker command, the trmv version and each fingerprint
 * file's name and content digest, in code-point order of name. */
export function cacheKey({ commit, language: id, command, version, fingerprints }: CacheKeyInput): string {
  const fields = [commit, id, command, version];
  for (const name of [...fingerprints.keys()].sort(byCodePoint)) fields.push(name, sha256(fingerprints.get(name) ?? Buffer.alloc(0)));
  return sha256(fields.join('\0'));
}

/** The contents of the language's fingerprint files that exist at `root`. */
export function fingerprints(root: string, id: string): Map<string, Buffer> {
  const out = new Map<string, Buffer>();
  for (const name of language(id).fingerprint_files as string[]) {
    try {
      if (isRegularFile(join(root, name))) out.set(name, readFile(join(root, name)));
    } catch {
      // unreadable: left out of the key
    }
  }
  return out;
}

/** A cached baseline's text, null when absent or unreadable. */
export function readEntry(path: string): string | null {
  try {
    return readFile(path, 'utf8');
  } catch {
    return null;
  }
}

/** Store a baseline's text whole or not at all; a failure only costs the next run a recomputation. */
export function writeEntry(path: string, text: string): void {
  let temp: string | null = null;
  try {
    mkdirSync(dirname(path), { recursive: true });
    temp = mkdtempSync(join(dirname(path), `${basename(path)}.`));
    writeFileSync(join(temp, 'entry'), text);
    renameSync(join(temp, 'entry'), path);
  } catch {
    // the next run recomputes
  } finally {
    if (temp !== null) rmSync(temp, { recursive: true, force: true });
  }
}
