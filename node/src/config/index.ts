// Per-repo config: `living-architecture.yaml`, validated and completed by the shared schema; the repo's languages.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import {
  PyFloat,
  YAMLError,
  canonicalRepr,
  fnmatch,
  isPortableRegex,
  language,
  languageIds,
  loadYaml,
  manifest,
  materializeDefaults,
  message,
  pyJson,
  reprFloat,
  schema,
  validate,
} from '../contract/index.js';

export const CONFIG_FILENAME = 'living-architecture.yaml';

/** The config file is unreadable or invalid. */
export class ConfigError extends Error {}

export interface LaConfig {
  tracker: 'linear' | 'github' | 'none';
  openspec: boolean;
  architecture: boolean;
  reviewers: { codex: boolean; sonar: { project_key: string | null } };
  issue_key_pattern: string;
  commands: {
    test: string | null;
    lint: string | null;
    typecheck: { python: string | null; typescript: string | null };
  };
  conventions: { text_ratio_max: number; exempt: string[]; rules: string[] };
}

/** Validate raw config data (null = no file) and fill the schema defaults; Error if invalid. */
export function resolveConfig(data: unknown): LaConfig {
  const configSchema = schema('living-architecture');
  if (data !== null && !(data instanceof Map)) throw new Error('top level must be a mapping');
  const errors = validate(configSchema, data === null ? new Map() : data);
  if (errors.length > 0) throw new Error(errors.join('; '));
  const resolved = materializeDefaults(configSchema, data) as LaConfig;
  if (!isPortableRegex(resolved.issue_key_pattern)) {
    throw new Error(`issue_key_pattern ${canonicalRepr(resolved.issue_key_pattern)} is not in the portable regex subset`);
  }
  return resolved;
}

/** Nearest ancestor of `start` (inclusive) containing `.git`, else `start`. */
export function findRepoRoot(start: string): string {
  let candidate = resolve(start);
  for (;;) {
    if (existsSync(join(candidate, '.git'))) return candidate;
    const parent = dirname(candidate);
    if (parent === candidate) return resolve(start);
    candidate = parent;
  }
}

function raw(path: string): unknown {
  if (!existsSync(path) || !statSync(path).isFile()) return null;
  try {
    return loadYaml(readFileSync(path, 'utf8'));
  } catch (error) {
    if (error instanceof YAMLError) throw new ConfigError(`${path}: invalid YAML: ${error.message}`);
    throw error;
  }
}

/** Config at `root`; defaults when the file is absent. */
export function loadConfig(root: string): LaConfig {
  const path = join(root, CONFIG_FILENAME);
  const data = raw(path);
  try {
    return resolveConfig(data);
  } catch (error) {
    throw new ConfigError(`${path}: ${(error as Error).message}`);
  }
}

/** The languages `commands.typecheck` sets explicitly (to a command or null); the config must be valid. */
export function explicitTypecheck(root: string): Set<string> {
  const data = raw(join(root, CONFIG_FILENAME));
  const commands = data instanceof Map ? data.get('commands') : undefined;
  const typecheck = commands instanceof Map ? commands.get('typecheck') : undefined;
  return new Set(typecheck instanceof Map ? [...typecheck.keys()].map(String) : []);
}

/** Tracked and untracked-but-not-ignored files, minus the exempt globs. */
export function sourceFiles(root: string, exempt: string[]): string[] {
  const proc = spawnSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'], { cwd: root, maxBuffer: 1 << 30 }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  const paths = (proc.stdout?.toString('utf8') ?? '').split('\0');
  return paths.filter((p) => p && !exempt.some((pattern) => fnmatch(p, pattern)));
}

const isFile = (path: string): boolean => existsSync(path) && statSync(path).isFile();

/** Languages with an explicit typecheck command, or with a root marker and a counted file; registry order. */
export function repoLanguages(root: string, config: LaConfig): string[] {
  const explicit = explicitTypecheck(root);
  let files: string[] | null = null;
  const out: string[] = [];
  for (const id of languageIds()) {
    if (explicit.has(id) && config.commands.typecheck[id as 'python' | 'typescript'] !== null) {
      out.push(id);
      continue;
    }
    const entry = language(id);
    if (!(entry.markers as string[]).some((marker) => isFile(join(root, marker)))) continue;
    files ??= sourceFiles(root, config.conventions.exempt);
    const extensions = entry.source_extensions as string[];
    if (files.some((f) => extensions.some((ext) => f.endsWith(ext)))) out.push(id);
  }
  return out;
}

/** A public fact of a registered language; RangeError for any other language or key. */
export function languageFact(id: string, key: string): unknown {
  const keys: string[] = manifest()['la-config'].subcommands.get.language_keys;
  if (!languageIds().includes(id) || !keys.includes(key)) throw new RangeError(key);
  const entry = language(id);
  if (key === 'source_globs') return (entry.source_extensions as string[]).map((ext) => `**/*${ext}`);
  if (key === 'waiver') return message('config.waiver', { prefix: entry.comment_prefix });
  return entry[key];
}

/** `value` with its keys in the schema's property order, as the typed config dumps it. */
function ordered(sub: any, value: any): any {
  if (value === null || typeof value !== 'object' || Array.isArray(value) || sub?.properties === undefined) return value;
  return Object.fromEntries(Object.keys(sub.properties).map((key) => [key, ordered(sub.properties[key], value[key])]));
}

/** The resolved config as Python dumps it: schema order, `text_ratio_max` always a float. */
function dumpable(config: LaConfig): unknown {
  const out = ordered(schema('living-architecture'), config);
  out.conventions.text_ratio_max = new PyFloat(config.conventions.text_ratio_max);
  return out;
}

function lookup(data: unknown, dotted: string): unknown {
  let node = data;
  for (const part of dotted.split('.')) {
    if (node === null || typeof node !== 'object' || Array.isArray(node) || node instanceof PyFloat || !Object.hasOwn(node, part)) {
      throw new RangeError(dotted);
    }
    node = (node as Record<string, unknown>)[part];
  }
  return node;
}

/** Shell-friendly: bools lowercase, null empty, containers as JSON. */
export function formatValue(value: unknown): string {
  if (value === true) return 'true';
  if (value === false) return 'false';
  if (value === null) return '';
  if (value instanceof PyFloat) return reprFloat(value.value);
  if (typeof value === 'object') return pyJson(value);
  return String(value);
}

function withConfig(root: string, action: (config: LaConfig) => number): number {
  let config: LaConfig;
  try {
    config = loadConfig(root);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    process.stderr.write(`${message('config.error', { error: error.message })}\n`);
    return 1;
  }
  return action(config);
}

export function runShow(root: string): number {
  return withConfig(root, (config) => {
    process.stdout.write(`${pyJson(dumpable(config), 2)}\n`);
    return 0;
  });
}

function printLanguages(root: string, config: LaConfig): number {
  if (!existsSync(join(root, '.git'))) {
    process.stderr.write(`${message('config.not-git')}\n`);
    return 2;
  }
  process.stdout.write(`${formatValue(repoLanguages(root, config))}\n`);
  return 0;
}

function value(config: LaConfig, key: string): unknown {
  const parts = key.split('.');
  if (parts[0] === 'lang' && parts.length === 3) return languageFact(parts[1] ?? '', parts[2] ?? '');
  if (parts[0] === 'lang') throw new RangeError(key);
  return lookup(dumpable(config), key);
}

export function runGet(root: string, key: string): number {
  return withConfig(root, (config) => {
    if (key === 'languages') return printLanguages(root, config);
    let found: unknown;
    try {
      found = value(config, key);
    } catch (error) {
      if (!(error instanceof RangeError)) throw error;
      process.stderr.write(`${message('config.unknown-key', { key })}\n`);
      return 2;
    }
    process.stdout.write(`${formatValue(found)}\n`);
    return 0;
  });
}
