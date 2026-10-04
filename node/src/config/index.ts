// Per-repo config: `living-architecture.yaml`, validated and completed by the shared schema.
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import {
  PyFloat,
  YAMLError,
  canonicalRepr,
  isPortableRegex,
  loadYaml,
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
  reviewers: { coderabbit: boolean; sonar: { enabled: boolean; project_key: string | null } };
  issue_key_pattern: string;
  commands: {
    test: string | null;
    lint: string | null;
    typecheck: { python: string | null; typescript: string | null };
  };
  conventions: { text_ratio_max: number; exempt: string[] };
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

function withConfig(root: string, action: (data: unknown) => number): number {
  let data: unknown;
  try {
    data = dumpable(loadConfig(root));
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    process.stderr.write(`${message('config.error', { error: error.message })}\n`);
    return 1;
  }
  return action(data);
}

export function runShow(root: string): number {
  return withConfig(root, (data) => {
    process.stdout.write(`${pyJson(data, 2)}\n`);
    return 0;
  });
}

export function runGet(root: string, key: string): number {
  return withConfig(root, (data) => {
    let value: unknown;
    try {
      value = lookup(data, key);
    } catch {
      process.stderr.write(`${message('config.unknown-key', { key })}\n`);
      return 2;
    }
    process.stdout.write(`${formatValue(value)}\n`);
    return 0;
  });
}
