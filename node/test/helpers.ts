// Test-only paths and loaders. Vector files are read with the `yaml` package's core schema, which reads every vector
// file as PyYAML does; its 1.1 schema does not (`n` -> false, `.` -> NaN).
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { basename, dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';

export const NODE_ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
export const REPO_ROOT = dirname(NODE_ROOT);
export const SHARED = join(REPO_ROOT, 'shared');
export const VECTORS = join(SHARED, 'vectors');
export const SNAPSHOT = join(NODE_ROOT, 'src', 'contract', 'data');
export const HASH_FILE = 'CONTRACT_HASH';

/** `strings` reads every scalar as text (for expected texts such as `1e+16`, a string to PyYAML). */
export function loadYamlFile(path: string, strings = false): any {
  return parse(readFileSync(path, 'utf8'), { uniqueKeys: false, ...(strings && { schema: 'failsafe' }) });
}

/** The vector file's content, or undefined while it does not exist. */
export function vectors(name: string, strings = false): any {
  const path = join(VECTORS, name);
  return existsSync(path) ? loadYamlFile(path, strings) : undefined;
}

export function readJson(path: string): any {
  return JSON.parse(readFileSync(path, 'utf8'));
}

/** A field of a loaded mapping, whether the twin represents mappings as objects or Maps. */
export function field(mapping: any, key: string): any {
  return mapping instanceof Map ? mapping.get(key) : mapping[key];
}

/** A twin value as plain JSON-like data: bigint and boxed numbers become numbers, Maps become objects. */
export function plain(value: any): any {
  if (typeof value === 'bigint') return Number(value);
  if (Array.isArray(value)) return value.map(plain);
  if (value instanceof Map) return Object.fromEntries([...value].map(([k, v]) => [String(k), plain(v)]));
  if (value !== null && typeof value === 'object') {
    if (Object.getPrototypeOf(value) !== Object.prototype && typeof value.valueOf() === 'number') return value.valueOf();
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, plain(v)]));
  }
  return value;
}

/** Relative POSIX path -> [executable, bytes] for every file under `root`, minus the hash file. */
export function tree(root: string): Record<string, [boolean, Buffer]> {
  if (!existsSync(root)) return {};
  const out: Record<string, [boolean, Buffer]> = {};
  for (const entry of readdirSync(root, { recursive: true, encoding: 'utf8' })) {
    const path = join(root, entry);
    const stat = statSync(path);
    if (stat.isFile() && basename(path) !== HASH_FILE) {
      out[relative(root, path).split(sep).join('/')] = [(stat.mode & 0o111) !== 0, readFileSync(path)];
    }
  }
  return out;
}
