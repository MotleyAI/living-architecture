// la's config: `living-architecture.yaml` with `living-architecture.local.yaml` merged over it, into the typed config.
import { existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import {
  ConfigError,
  type ConfigView,
  type Handler,
  type LanguageSettings,
  type RefactorConfig,
  type TypecheckConfig,
  checkStringForms,
  explicitTypecheck,
  readConfig,
  runCommand as drRunCommand,
} from 'deterministic-refactor/config';
import {
  PyFloat,
  canonicalRepr,
  configFile,
  identity,
  isPortableRegex,
  localConfigFile,
  manifest,
  materializeDefaults,
  schema,
  schemaOrdered,
  validate,
} from '../contract/index.js';

/** The committed data with the local file merged over it, before `resolveConfig`. */
export interface RawConfig {
  data: unknown;
  overrides: string[];
  hasCommitted: boolean;
  hasLocal: boolean;
}

/** The resolved config; built only by `resolveConfig`, so every default comes from the schemas. */
export interface LaConfig {
  format: string | null;
  exempt: string[];
  tracker: 'linear' | 'github' | 'none';
  openspec: boolean;
  architecture: boolean;
  reviewers: { codex: boolean; sonar: { project_key: string | null } };
  issue_key_pattern: string;
  commands: { test: string | null; lint: string | null; typecheck: TypecheckConfig };
  refactor: RefactorConfig;
  conventions: { text_ratio_max: number; rules: string[] };
}

/** Validate raw config data (null = no file) and fill the schema defaults; Error if invalid. */
export function resolveConfig(data: unknown): LaConfig {
  const configSchema = schema('living-architecture');
  if (data !== null && !(data instanceof Map)) throw new Error('top level must be a mapping');
  const errors = validate(configSchema, data ?? new Map());
  if (errors.length > 0) throw new Error(errors.join('; '));
  const resolved = materializeDefaults(configSchema, data) as LaConfig;
  if (!isPortableRegex(resolved.issue_key_pattern)) {
    throw new Error(`issue_key_pattern ${canonicalRepr(resolved.issue_key_pattern)} is not in the portable regex subset`);
  }
  checkStringForms(resolved.refactor.string_forms);
  return resolved;
}

const isFile = (path: string): boolean => existsSync(path) && statSync(path).isFile();

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
  const committed = readConfig(root, configFile());
  const localPath = join(root, localConfigFile());
  const local = readConfig(root, localConfigFile());
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

/** `config` as language detection reads it. */
export function languagesOf(config: LaConfig, raw: RawConfig): LanguageSettings {
  return { exempt: config.exempt, typecheck: config.commands.typecheck, explicit: explicitTypecheck(raw.data) };
}

/** la's config at `root`, as `la-config` prints it (schema order, `text_ratio_max` a float), from one read of both files. */
export function laView(root: string): ConfigView {
  const raw = loadRaw(root);
  const config = resolveRaw(root, raw);
  const values = schemaOrdered(schema('living-architecture'), config);
  values.conventions.text_ratio_max = new PyFloat(config.conventions.text_ratio_max);
  return { values, overrides: raw.overrides, localFile: localConfigFile(), languages: languagesOf(config, raw) };
}

/** `command` of la's manifest run through dr's command runner, checking la's config file. */
export function runCommand(
  command: string,
  argv: string[],
  handlers: Record<string, Handler>,
  shim?: (command: string, argv: string[]) => number,
): number {
  return drRunCommand(command, argv, handlers, { commands: manifest(), configFile: configFile(), who: identity(), shim });
}
