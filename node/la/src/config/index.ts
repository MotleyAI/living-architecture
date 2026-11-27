// la's config: `living-architecture.yaml` with `living-architecture.local.yaml` merged over it, or la's stealth config,
// into the typed config.
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import {
  ConfigError,
  type ConfigFile,
  type ConfigView,
  type Handler,
  type LanguageSettings,
  type RefactorConfig,
  type TypecheckConfig,
  checkStringForms,
  displayName,
  explicitTypecheck,
  findConfig,
  readConfig,
  runCommand as trmvRunCommand,
  stealthDir,
  stealthRefusal,
  stealthView,
} from 'type-rename-move/config';
import {
  PyFloat,
  canonicalRepr,
  configFile,
  identity,
  isPortableRegex,
  leakTokenGroups,
  localConfigFile,
  manifest,
  materializeDefaults,
  message,
  schema,
  schemaOrdered,
  stealthPath,
  validate,
} from '../contract/index.js';

/** The config file's data with the local file merged over it, before `resolveConfig`; `source` is the config file. */
export interface RawConfig {
  data: unknown;
  overrides: string[];
  hasCommitted: boolean;
  hasLocal: boolean;
  source: ConfigFile | null;
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
  /** The stealth config's tolerated leak tokens; none outside stealth mode. */
  leaks: { allow: string[] };
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
  resolved.leaks ??= { allow: [] };
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

/** The config file's data with the stealth config's `leaks.allow` checked and defaulted; ConfigError for `leaks` in a
 * root file. */
function withLeaks(data: unknown, source: ConfigFile): unknown {
  const name = displayName(source);
  if (!source.stealth) {
    if (data instanceof Map && data.has('leaks')) throw new ConfigError(message('config.leaks-not-stealth', { path: name }));
    return data;
  }
  const base = data ?? new Map();
  const leaks = base instanceof Map ? (base.get('leaks') ?? new Map()) : null;
  if (!(base instanceof Map) || !(leaks instanceof Map)) return base;
  const allow = leaks.get('allow') ?? [];
  const waivable = leakTokenGroups()[1];
  for (const token of Array.isArray(allow) ? allow : []) {
    if (!waivable.includes(token)) throw new ConfigError(message('config.leak-not-waivable', { path: name, token }));
  }
  return new Map([...base, ['leaks', new Map([...leaks, ['allow', allow]])]]);
}

/** The config file and the local one read, the local one checked against its schema; ConfigError naming the faulty
 * file. In stealth mode a local file is refused. */
export function loadRaw(root: string): RawConfig {
  const source = findConfig(root, 'la');
  const name = source === null ? configFile() : displayName(source);
  let committed = readConfig(root, name);
  if (source?.stealth) stealthRefusal(committed, name);
  if (source !== null) committed = withLeaks(committed, source);
  const localPath = join(root, localConfigFile());
  if (source?.stealth && isFile(localPath)) throw new ConfigError(message('config.local-in-stealth', { file: localConfigFile() }));
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
  return { data, overrides, hasCommitted: source !== null, hasLocal: isFile(localPath), source };
}

/** `raw` resolved; ConfigError naming the config file. */
export function resolveRaw(root: string, raw: RawConfig): LaConfig {
  try {
    return resolveConfig(raw.data);
  } catch (error) {
    const path = raw.source?.stealth ? raw.source.path : join(root, configFile());
    throw new ConfigError(`${path}: ${(error as Error).message}`);
  }
}

/** The private OpenSpec store's id: `la-` and the first 12 hex digits of the SHA-256 of la's stealth directory. */
export function openspecStoreId(directory: string): string {
  return `la-${createHash('sha256').update(directory).digest('hex').slice(0, 12)}`;
}

/** Whether HEAD tracks a path under `openspec/`. */
export function tracksOpenspec(root: string): boolean {
  const proc = spawnSync('git', ['ls-tree', '-r', '-z', '--name-only', 'HEAD', '--', 'openspec/'], { cwd: root, maxBuffer: 1 << 30 }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  return proc.status === 0 && proc.stdout.length > 0;
}

/** la's stealth directory when the private OpenSpec store applies, else null. */
export function privateStore(root: string, cfg: LaConfig, raw: RawConfig): string | null {
  if (!raw.source?.stealth || !cfg.openspec || tracksOpenspec(root)) return null;
  return stealthDir(root, 'la');
}

/** Where the /la:pr flow keeps its plans in stealth mode with openspec false. */
export function plansDir(directory: string): string {
  return join(directory, stealthPath('plans_dir'));
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
  if (!raw.source?.stealth) delete values.leaks;
  values.conventions.text_ratio_max = new PyFloat(config.conventions.text_ratio_max);
  const [stealthFile, derived] = stealthView(root, 'la');
  const store = privateStore(root, config, raw);
  return {
    values,
    overrides: raw.overrides,
    localFile: localConfigFile(),
    languages: languagesOf(config, raw),
    stealthFile,
    derived: { ...derived, openspec_store: store === null ? '' : openspecStoreId(store) },
  };
}

/** `command` of la's manifest run through trmv's command runner, checking la's config file. */
export function runCommand(
  command: string,
  argv: string[],
  handlers: Record<string, Handler>,
  shim?: (command: string, argv: string[]) => number,
): number {
  return trmvRunCommand(command, argv, handlers, { commands: manifest(), pkg: 'la', who: identity(), shim });
}
