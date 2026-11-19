// The vendored contract snapshot: its location, hash and data files.
import { createHash } from 'node:crypto';
// eslint-disable-next-line no-restricted-imports -- the bundled contract snapshot
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { globMatch } from './glob.js';
import { byCodePoint } from './text.js';
import { toPlain } from './values.js';
import { loadYaml } from './yaml.js';

export const HASH_FILE = 'CONTRACT_HASH';

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

/** A vendored contract directory: its recorded hash and its data files. */
export class Snapshot {
  private readonly cache = new Map<string, any>();

  constructor(readonly root: string) {}

  /** The hash recorded when the snapshot was vendored. */
  contractHash(): string {
    return readFileSync(join(this.root, HASH_FILE), 'utf8').trim();
  }

  private data(name: string, load: (text: string) => any): any {
    if (!this.cache.has(name)) this.cache.set(name, load(readFileSync(join(this.root, name), 'utf8')));
    return this.cache.get(name);
  }

  yaml(name: string): any {
    return this.data(name, (text) => toPlain(loadYaml(text)));
  }

  schema(name: string): Record<string, any> {
    return this.data(join('schema', `${name}.schema.json`), JSON.parse);
  }

  /** Every schema's name, as `schema` takes it. */
  schemaNames(): string[] {
    return readdirSync(join(this.root, 'schema'))
      .filter((name) => name.endsWith('.schema.json'))
      .map((name) => name.slice(0, -'.schema.json'.length))
      .sort();
  }

  findings(): Record<string, string> {
    return this.yaml('findings.yaml').findings;
  }

  manifest(): Record<string, any> {
    return this.yaml('cli.yaml').commands;
  }

  scriptPath(name: string): string {
    return join(this.root, 'scripts', name);
  }
}

export const DR = new Snapshot(join(dirname(fileURLToPath(import.meta.url)), 'data'));

export function snapshotDir(): string {
  return DR.root;
}

/** The hash recorded when dr's snapshot was vendored. */
export function contractHash(): string {
  return DR.contractHash();
}

export function schema(name: string): Record<string, any> {
  return DR.schema(name);
}

/** Every dr schema's name, as `schema` takes it. */
export function schemaNames(): string[] {
  return DR.schemaNames();
}

export function findings(): Record<string, string> {
  return DR.findings();
}

export function manifest(): Record<string, any> {
  return DR.manifest();
}

const cli = (): any => DR.yaml('cli.yaml');

/** Seconds after which the best-effort fetch of a base branch is killed. */
export function baseFetchTimeout(): number {
  return Number(cli().base_fetch_timeout_seconds);
}

/** The substrings a literal member's new value may not hold. */
export function literalValueForbidden(): string[] {
  return (cli().literal_value_forbidden as unknown[]).map(String);
}

/** The phases `dr-refactor --timings` reports, in print order. */
export function timingPhases(): string[] {
  return (cli().timing_phases as unknown[]).map(String);
}

/** The public `lang.<language>.<key>` keys. */
export function languageKeys(): string[] {
  return (cli().language_keys as unknown[]).map(String);
}

export function language(id: string): Record<string, any> {
  return DR.yaml('languages.yaml')[id];
}

/** Every language of the registry, in id order. */
export function languageIds(): string[] {
  return Object.keys(DR.yaml('languages.yaml')).sort(byCodePoint);
}

/** The registry language whose source extensions contain the path's extension, else null. */
export function languageOf(path: string): string | null {
  return languageIds().find((id) => (language(id).source_extensions as string[]).some((ext) => path.endsWith(ext))) ?? null;
}

/** A path with a registry language's source extension matching that language's test globs. */
export function isTestFile(rel: string): boolean {
  const id = languageOf(rel);
  return id !== null && (language(id).test_globs as string[]).some((glob) => globMatch(glob, rel));
}

/** The committed config files a dr command reads, in order: the first present at the repo root. */
export function configFiles(): string[] {
  return [...DR.yaml('config.yaml').files];
}

/** Every released format of config file `file`, oldest first. */
export function configFormats(file: string): string[] {
  return [...DR.yaml('config.yaml').formats[file]];
}
