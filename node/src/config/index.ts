// Per-repo config: `living-architecture.yaml` with its local overrides, validated and completed by the shared schema; the
// repo's languages.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import {
  PyFloat,
  YAMLError,
  canonicalRepr,
  configFile,
  fnmatch,
  isPortableRegex,
  language,
  languageIds,
  loadYaml,
  localConfigFile,
  manifest,
  materializeDefaults,
  message,
  pyJson,
  reprFloat,
  schema,
  validate,
} from '../contract/index.js';

export const CONFIG_FILENAME = configFile();

/** The config file is unreadable or invalid. */
export class ConfigError extends Error {}

/** The committed data with the local file merged over it, before `resolveConfig`. */
export interface RawConfig {
  data: unknown;
  overrides: string[];
  hasCommitted: boolean;
  hasLocal: boolean;
}

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

const isFile = (path: string): boolean => existsSync(path) && statSync(path).isFile();

function raw(path: string): unknown {
  if (!isFile(path)) return null;
  try {
    return loadYaml(readFileSync(path, 'utf8'));
  } catch (error) {
    if (error instanceof YAMLError) throw new ConfigError(`${path}: invalid YAML: ${error.message}`);
    throw error;
  }
}

function merge(base: unknown, over: unknown): unknown {
  if (!(base instanceof Map && over instanceof Map)) return over;
  const out = new Map(base);
  for (const [key, value] of over) out.set(key, merge(base.get(key), value));
  return out;
}

/** The dotted keys `data` sets, in the schema's property order. */
function leaves(sub: Record<string, any>, data: Map<unknown, unknown>, prefix = ''): string[] {
  const out: string[] = [];
  for (const [key, prop] of Object.entries<any>(sub.properties)) {
    if (!data.has(key)) continue;
    const value = data.get(key);
    if (prop.properties !== undefined && value instanceof Map) out.push(...leaves(prop, value, `${prefix}${key}.`));
    else out.push(`${prefix}${key}`);
  }
  return out;
}

/** Both files read and the local one checked against its schema; ConfigError naming the faulty file. */
export function loadRaw(root: string): RawConfig {
  const committed = raw(join(root, configFile()));
  const localPath = join(root, localConfigFile());
  const local = raw(localPath);
  let overrides: string[] = [];
  let data = committed;
  if (local !== null) {
    if (!(local instanceof Map)) throw new ConfigError(`${localPath}: top level must be a mapping`);
    const localSchema = schema('living-architecture.local');
    const errors = validate(localSchema, local);
    if (errors.length > 0) throw new ConfigError(`${localPath}: ${errors.join('; ')}`);
    overrides = leaves(localSchema, local);
    if (committed === null || committed instanceof Map) data = merge(committed ?? new Map(), local);
  }
  return { data, overrides, hasCommitted: isFile(join(root, configFile())), hasLocal: isFile(localPath) };
}

/** `raw` resolved; ConfigError naming the committed file. */
export function resolveRaw(root: string, raw: RawConfig): LaConfig {
  try {
    return resolveConfig(raw.data);
  } catch (error) {
    throw new ConfigError(`${join(root, configFile())}: ${(error as Error).message}`);
  }
}

/** Config at `root`; defaults when neither file exists. */
export function loadConfig(root: string): LaConfig {
  return resolveRaw(root, loadRaw(root));
}

/** The languages `commands.typecheck` sets explicitly (to a command or null); the config must be valid. */
export function explicitTypecheck(root: string): Set<string> {
  const { data } = loadRaw(root);
  const commands = data instanceof Map ? data.get('commands') : undefined;
  const typecheck = commands instanceof Map ? commands.get('typecheck') : undefined;
  return new Set(typecheck instanceof Map ? [...typecheck.keys()].map(String) : []);
}

/** Tracked and untracked-but-not-ignored files, minus the exempt globs; none outside git. ConfigError when git fails inside a repo. */
export function sourceFiles(root: string, exempt: string[]): string[] {
  const proc = spawnSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'], { cwd: root, maxBuffer: 1 << 30 }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  if (proc.status !== 0 && existsSync(join(root, '.git'))) throw new ConfigError(message('config.git-failed'));
  const paths = (proc.stdout?.toString('utf8') ?? '').split('\0');
  return paths.filter((p) => p && !exempt.some((pattern) => fnmatch(p, pattern)));
}

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

/** Run `action` on the config and its local overrides, both from one read of the files. */
function withConfig(root: string, action: (config: LaConfig, overrides: string[]) => number): number {
  let raw: RawConfig;
  let config: LaConfig;
  try {
    raw = loadRaw(root);
    config = resolveRaw(root, raw);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    process.stderr.write(`${message('config.error', { error: error.message })}\n`);
    return 1;
  }
  return action(config, raw.overrides);
}

export function runShow(root: string): number {
  return withConfig(root, (config, overrides) => {
    process.stdout.write(`${pyJson(dumpable(config), 2)}\n`);
    for (const key of overrides) {
      process.stderr.write(`${message('config.local-override', { key, file: localConfigFile() })}\n`);
    }
    return 0;
  });
}

function printLanguages(root: string, config: LaConfig): number {
  if (!existsSync(join(root, '.git'))) {
    process.stderr.write(`${message('config.not-git')}\n`);
    return 2;
  }
  let languages: string[];
  try {
    languages = repoLanguages(root, config);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    process.stderr.write(`${message('config.error', { error: error.message })}\n`);
    return 2;
  }
  process.stdout.write(`${formatValue(languages)}\n`);
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
