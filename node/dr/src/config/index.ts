// Per-repo config: the committed file dr reads, validated and completed by dr's schema; the shared loading, format
// check, language detection and config-command machinery la's config builds on.
import { spawnSync } from 'node:child_process';
import { existsSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import {
  PyFloat,
  capturingGroups,
  fnmatch,
  isPortableRegex,
  language,
  languageIds,
  languageKeys,
  materializeDefaults,
  message,
  pyJson,
  reprFloat,
  schema,
  schemaOrdered,
  validate,
} from '../contract/index.js';
import { ConfigError } from './error.js';
import { configSource, ownFile } from './files.js';
import { parseConfig, readConfigText } from './read.js';

export { type Handler, commandRoot, optional, runCommand } from './command.js';
export { ConfigError } from './error.js';
export {
  type Committed,
  FORMAT_KEY,
  checkFormat,
  compareVersions,
  currentFormat,
  formatProblem,
  isVersion,
  readCommitted,
  releasedFormats,
  stampFormat,
} from './format.js';
export { parseConfig, readConfigText } from './read.js';
export { bothFilesProblem, configSource, ownFile } from './files.js';

const DR_SCHEMA = 'deterministic-refactor';

export interface TypecheckConfig {
  python: string | null;
  typescript: string | null;
}

export interface RefactorConfig {
  python: { moved_module_stub: string | null };
  string_forms: string[];
}

/** dr's resolved config; built only by `resolveConfig`, so every default comes from the schema. */
export interface DrConfig {
  format: string | null;
  exempt: string[];
  commands: { test: string | null; typecheck: TypecheckConfig };
  refactor: RefactorConfig;
}

/** What repo-language detection reads from a config: exempt paths, checker commands, the ones set explicitly. */
export interface LanguageSettings {
  exempt: string[];
  typecheck: TypecheckConfig;
  explicit: Set<string>;
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

/** Config file `name` parsed, null when it does not exist; ConfigError when unreadable or not YAML. */
export function readConfig(root: string, name: string): unknown {
  const text = readConfigText(root, name);
  return text === null ? null : parseConfig(text, name);
}

/** `data` with only the keys `sub` defines, recursively through the objects that list their keys. */
function project(sub: Record<string, any>, data: unknown): unknown {
  if (!(data instanceof Map) || sub.properties === undefined) return data;
  const out = new Map();
  for (const [key, value] of data) if (Object.hasOwn(sub.properties, String(key))) out.set(key, project(sub.properties[String(key)], value));
  return out;
}

/** The dr keys of config file `name`'s data: all of dr's own file, and dr's share of another package's file. */
export function drData(data: unknown, name: string): unknown {
  return name === ownFile() || !(data instanceof Map) ? data : project(schema(DR_SCHEMA), data);
}

/** Error unless every pattern is portable and holds exactly one capturing group. */
export function checkStringForms(patterns: string[]): void {
  for (const pattern of patterns) {
    if (!isPortableRegex(pattern)) throw new Error(`refactor.string_forms pattern ${pattern} is not in the portable regex subset`);
    if (capturingGroups(pattern) !== 1) throw new Error(`refactor.string_forms pattern ${pattern} must hold exactly one capturing group`);
  }
}

/** Validate dr's config data (null = no file) and fill the schema defaults; Error if invalid. */
export function resolveConfig(data: unknown): DrConfig {
  const drSchema = schema(DR_SCHEMA);
  if (data !== null && !(data instanceof Map)) throw new Error('top level must be a mapping');
  const errors = validate(drSchema, data === null ? new Map() : data);
  if (errors.length > 0) throw new Error(errors.join('; '));
  const resolved = materializeDefaults(drSchema, data) as DrConfig;
  checkStringForms(resolved.refactor.string_forms);
  return resolved;
}

/** dr's share of the config file it reads, and that file's name; [null, null] without one. */
export function loadDrData(root: string): [unknown, string | null] {
  const name = configSource(root);
  return name === null ? [null, null] : [drData(readConfig(root, name), name), name];
}

function resolved(root: string, data: unknown, name: string | null): DrConfig {
  try {
    return resolveConfig(data);
  } catch (error) {
    throw new ConfigError(`${join(root, String(name))}: ${(error as Error).message}`);
  }
}

/** dr's config at `root`; defaults without a config file. ConfigError naming the faulty file. */
export function loadConfig(root: string): DrConfig {
  return resolved(root, ...loadDrData(root));
}

/** The languages config `data` sets `commands.typecheck` for explicitly (to a command or null). */
export function explicitTypecheck(data: unknown): Set<string> {
  const commands = data instanceof Map ? data.get('commands') : undefined;
  const typecheck = commands instanceof Map ? commands.get('typecheck') : undefined;
  return new Set(typecheck instanceof Map ? [...typecheck.keys()].map(String) : []);
}

/** dr's config at `root`, and that config as language detection reads it, from one read of the file. */
export function loadWithLanguages(root: string): [DrConfig, LanguageSettings] {
  const [data, name] = loadDrData(root);
  const config = resolved(root, data, name);
  return [config, { exempt: config.exempt, typecheck: config.commands.typecheck, explicit: explicitTypecheck(data) }];
}

/** dr's config at `root` as language detection reads it. */
export function languageSettings(root: string): LanguageSettings {
  return loadWithLanguages(root)[1];
}

/** Tracked and untracked-but-not-ignored files, minus the exempt globs; none outside git. ConfigError when git fails inside a repo. */
export function sourceFiles(root: string, exempt: string[]): string[] {
  const proc = spawnSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard'], { cwd: root, maxBuffer: 1 << 30 }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  if (proc.status !== 0 && existsSync(join(root, '.git'))) throw new ConfigError(message('config.git-failed'));
  const paths = (proc.stdout?.toString('utf8') ?? '').split('\0');
  return paths.filter((p) => p && !exempt.some((pattern) => fnmatch(p, pattern)));
}

/** Languages with an explicit typecheck command, or with a root marker and a counted file; registry order. */
export function repoLanguages(root: string, settings: LanguageSettings): string[] {
  let files: string[] | null = null;
  const out: string[] = [];
  for (const id of languageIds()) {
    if (settings.explicit.has(id) && settings.typecheck[id as keyof TypecheckConfig] !== null) {
      out.push(id);
      continue;
    }
    const entry = language(id);
    if (!(entry.markers as string[]).some((marker) => isFile(join(root, marker)))) continue;
    files ??= sourceFiles(root, settings.exempt);
    const extensions = entry.source_extensions as string[];
    if (files.some((f) => extensions.some((ext) => f.endsWith(ext)))) out.push(id);
  }
  return out;
}

/** A public fact of a registered language; RangeError for any other language or key. */
export function languageFact(id: string, key: string): unknown {
  if (!languageIds().includes(id) || !languageKeys().includes(key)) throw new RangeError(key);
  const entry = language(id);
  if (key === 'source_globs') return (entry.source_extensions as string[]).map((ext) => `**/*${ext}`);
  if (key === 'waiver') return message('config.waiver', { prefix: entry.comment_prefix });
  return entry[key];
}

/** A resolved config as a config command prints it: its dumpable values, the keys a local file overrides (in
 * `localFile`), and what language detection reads. */
export interface ConfigView {
  values: unknown;
  overrides: string[];
  localFile: string | null;
  languages: LanguageSettings;
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

function withView(prog: string, root: string, load: (root: string) => ConfigView, action: (view: ConfigView) => number): number {
  let view: ConfigView;
  try {
    view = load(root);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    process.stderr.write(`${message('config.error', { prog, error: error.message })}\n`);
    return 1;
  }
  return action(view);
}

/** `show`: the resolved config as JSON, then one stderr note per key a local file overrides. */
export function runShow(prog: string, root: string, load: (root: string) => ConfigView): number {
  return withView(prog, root, load, (view) => {
    process.stdout.write(`${pyJson(view.values, 2)}\n`);
    for (const key of view.overrides) {
      process.stderr.write(`${message('config.local-override', { prog, key, file: view.localFile })}\n`);
    }
    return 0;
  });
}

function printLanguages(prog: string, root: string, view: ConfigView): number {
  if (!existsSync(join(root, '.git'))) {
    process.stderr.write(`${message('config.not-git', { prog })}\n`);
    return 2;
  }
  let languages: string[];
  try {
    languages = repoLanguages(root, view.languages);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    process.stderr.write(`${message('config.error', { prog, error: error.message })}\n`);
    return 2;
  }
  process.stdout.write(`${formatValue(languages)}\n`);
  return 0;
}

function value(view: ConfigView, key: string): unknown {
  const parts = key.split('.');
  if (parts[0] === 'lang' && parts.length === 3) return languageFact(parts[1] ?? '', parts[2] ?? '');
  if (parts[0] === 'lang') throw new RangeError(key);
  return lookup(view.values, key);
}

/** `get KEY`: one value by dotted key; `languages` the repo languages, `lang.<language>.<key>` a language fact. */
export function runGet(prog: string, root: string, key: string, load: (root: string) => ConfigView): number {
  return withView(prog, root, load, (view) => {
    if (key === 'languages') return printLanguages(prog, root, view);
    let found: unknown;
    try {
      found = value(view, key);
    } catch (error) {
      if (!(error instanceof RangeError)) throw error;
      process.stderr.write(`${message('config.unknown-key', { prog, key })}\n`);
      return 2;
    }
    process.stdout.write(`${formatValue(found)}\n`);
    return 0;
  });
}

/** dr's config at `root`, as `dr-config` prints it. */
export function drView(root: string): ConfigView {
  const [config, languages] = loadWithLanguages(root);
  return { values: schemaOrdered(schema(DR_SCHEMA), config), overrides: [], localFile: null, languages };
}
