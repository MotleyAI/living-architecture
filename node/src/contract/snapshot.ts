// The vendored contract snapshot: its location, hash and data files.
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { toPlain } from './values.js';
import { loadYaml } from './yaml.js';

export const HASH_FILE = 'CONTRACT_HASH';

export function snapshotDir(): string {
  return join(dirname(fileURLToPath(import.meta.url)), 'data');
}

function files(root: string): string[] {
  const rels = readdirSync(root, { recursive: true, encoding: 'utf8' })
    .map((entry) => relative(root, join(root, entry)).split(sep).join('/'))
    .filter((rel) => statSync(join(root, rel)).isFile() && rel.split('/').pop() !== HASH_FILE);
  return rels.sort((a, b) => Buffer.compare(Buffer.from(a), Buffer.from(b)));
}

/** sha256 over (POSIX path, executable bit, length, bytes) of every file but the hash file. */
export function computeHash(root: string): string {
  const digest = createHash('sha256');
  for (const rel of files(root)) {
    const path = join(root, rel);
    const data = readFileSync(path);
    const executable = (statSync(path).mode & 0o111) !== 0 ? '1' : '0';
    digest.update(Buffer.concat([Buffer.from(`${rel}\0${executable}\0${data.length}\0`), data]));
  }
  return digest.digest('hex');
}

/** The hash recorded when the snapshot was vendored. */
export function contractHash(): string {
  return readFileSync(join(snapshotDir(), HASH_FILE), 'utf8').trim();
}

const cache = new Map<string, any>();

function data(name: string, load: (text: string) => any): any {
  if (!cache.has(name)) cache.set(name, load(readFileSync(join(snapshotDir(), name), 'utf8')));
  return cache.get(name);
}

const yamlFile = (name: string): any => data(name, (text) => toPlain(loadYaml(text)));

export function schema(name: string): Record<string, any> {
  return data(join('schema', `${name}.schema.json`), JSON.parse);
}

export function findings(): Record<string, string> {
  return yamlFile('findings.yaml').findings;
}

export function checkIds(): string[] {
  return yamlFile('findings.yaml').check_ids;
}

export function manifest(): Record<string, any> {
  return yamlFile('cli.yaml').commands;
}

export function language(id: string): Record<string, any> {
  return yamlFile('languages.yaml')[id];
}

/** Every language of the registry, in id order. */
export function languageIds(): string[] {
  return Object.keys(yamlFile('languages.yaml')).sort();
}

export function conventions(): Record<string, any> {
  return yamlFile('conventions.yaml');
}

export function architecture(): Record<string, any> {
  return yamlFile('architecture.yaml');
}

export function scriptPath(name: string): string {
  return join(snapshotDir(), 'scripts', name);
}
