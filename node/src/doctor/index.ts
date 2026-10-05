// `la-doctor`: check the installed tools match the plugin and the repo config is valid.
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { CONFIG_FILENAME, ConfigError, type LaConfig, loadConfig, repoLanguages } from '../config/index.js';
import { contractHash, language, message, which } from '../contract/index.js';
import { VERSION } from '../index.js';

const REQUIRED_EXECUTABLES = ['git', 'gh'];
const PLUGIN_MANIFEST = join('.claude-plugin', 'plugin.json');

/** A missing entry is absent; other stat errors propagate. */
function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === 'ENOENT' || code === 'ENOTDIR') return false;
    throw error;
  }
}

function versionProblem(expected: string): string | null {
  return expected === VERSION ? null : message('doctor.version-mismatch', { installed: VERSION, expected });
}

function manifestProblem(manifest: string, raw: Buffer): string | null {
  let version: unknown = null;
  try {
    const data: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(raw));
    if (data !== null && typeof data === 'object' && !Array.isArray(data)) version = (data as Record<string, unknown>).version;
  } catch {
    version = null;
  }
  if (typeof version !== 'string' || /\p{Surrogate}/u.test(version)) return message('doctor.plugin-invalid', { path: manifest });
  return versionProblem(version);
}

/** Check against the version in the nearest `.claude-plugin/plugin.json` at or above `plugin`. */
function pluginProblem(plugin: string): string | null {
  const start = resolve(plugin);
  for (let dir = start; ; dir = dirname(dir)) {
    const manifest = join(dir, PLUGIN_MANIFEST);
    let raw: Buffer | null;
    try {
      raw = isFile(manifest) ? readFileSync(manifest) : null;
    } catch {
      return message('doctor.plugin-unreadable', { path: manifest });
    }
    if (raw !== null) return manifestProblem(manifest, raw);
    if (dirname(dir) === dir) return message('doctor.plugin-not-found', { dir: start });
  }
}

const isDir = (path: string): boolean => existsSync(path) && statSync(path).isDirectory();

/** The config's gate decisions that the disk contradicts, in a fixed order. */
function consistency(root: string, config: LaConfig): string[] {
  const problems: string[] = [];
  const hasOpenspec = isDir(join(root, 'openspec'));
  const hasArchitecture = isFile(join(root, 'architecture', 'index.yaml'));
  if (config.openspec !== hasOpenspec) {
    problems.push(message(config.openspec ? 'doctor.openspec-absent' : 'doctor.openspec-present'));
  }
  if (config.architecture !== hasArchitecture) {
    problems.push(message(config.architecture ? 'doctor.architecture-absent' : 'doctor.architecture-present'));
  }
  if (config.tracker === 'none' && !config.openspec) problems.push(message('doctor.no-plan-store'));
  return problems;
}

function configProblems(root: string, requireConfig: boolean): string[] {
  if (!isFile(join(root, CONFIG_FILENAME))) return requireConfig ? [message('doctor.config-missing')] : [];
  let config: LaConfig;
  try {
    config = loadConfig(root);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    return [error.message];
  }
  return consistency(root, config);
}

/** What the repo languages need on PATH; none outside git or with an invalid config. */
function languageExecutables(root: string): string[] {
  if (!existsSync(join(root, '.git'))) return [];
  let config: LaConfig;
  try {
    config = loadConfig(root);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    return [];
  }
  return repoLanguages(root, config).flatMap((id) => language(id).executables as string[]);
}

/** Problems found; empty means healthy. Config-vs-disk checks run only when the config file exists. */
export function runChecks(root: string, expect: string | null, plugin: string | null = null, requireConfig = false): string[] {
  const versions = [expect !== null ? versionProblem(expect) : null, plugin !== null ? pluginProblem(plugin) : null];
  const problems = versions.filter((problem): problem is string => problem !== null);
  problems.push(...configProblems(root, requireConfig));
  for (const exe of [...REQUIRED_EXECUTABLES, ...languageExecutables(root)]) {
    if (!which(exe)) problems.push(message('doctor.missing-executable', { exe }));
  }
  return problems;
}

export function run(root: string, expect: string | null, plugin: string | null, printHash: boolean, requireConfig = false): number {
  if (printHash) {
    process.stdout.write(`${contractHash()}\n`);
    return 0;
  }
  const problems = runChecks(root, expect, plugin, requireConfig);
  for (const problem of problems) process.stdout.write(`${message('doctor.fail', { problem })}\n`);
  if (problems.length === 0) {
    const source = isFile(join(root, CONFIG_FILENAME)) ? CONFIG_FILENAME : message('doctor.no-config-file');
    process.stdout.write(`${message('doctor.ok', { version: VERSION, source })}\n`);
  }
  return problems.length > 0 ? 1 : 0;
}
