// `la-doctor`: check the installed tools match the plugin's minor series and the repo config is valid.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { ConfigError, type LaConfig, checkFormat, loadConfig, repoLanguages } from '../config/index.js';
import { configFile, contractHash, language, localConfigFile, message, renderTemplate, which } from '../contract/index.js';
import { NATIVE_LANGUAGE, VERSION } from '../index.js';

const REQUIRED_EXECUTABLES = ['git', 'gh'];
const PLUGIN_MANIFEST = join('.claude-plugin', 'plugin.json');
const VERSION_FORM = /^([0-9]+)\.([0-9]+)\..+$/s;

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

/** Major and minor of `<digits>.<digits>.<rest>` as written, or null. */
function series(version: string): [string, string] | null {
  const match = VERSION_FORM.exec(version);
  return match === null ? null : [match[1] ?? '', match[2] ?? ''];
}

const canonical = (parts: [string, string]): string => parts.map((part) => part.replace(/^0+/, '') || '0').join('.');

function versionProblem(expected: string, plugin: [string, string]): string | null {
  const installed = series(VERSION);
  if (installed !== null && canonical(installed) === canonical(plugin)) return null;
  const install = renderTemplate(language(NATIVE_LANGUAGE).install, { version: expected });
  return message('doctor.version-mismatch', { installed: VERSION, expected, series: plugin.join('.'), install });
}

function manifestProblem(manifest: string, raw: Buffer): string | null {
  let version: unknown = null;
  try {
    const data: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(raw));
    if (data !== null && typeof data === 'object' && !Array.isArray(data)) version = (data as Record<string, unknown>).version;
  } catch {
    version = null;
  }
  const parts = typeof version === 'string' && !/\p{Surrogate}/u.test(version) ? series(version) : null;
  if (typeof version !== 'string' || parts === null) return message('doctor.plugin-invalid', { path: manifest });
  return versionProblem(version, parts);
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
  const hasCommitted = isFile(join(root, configFile()));
  const missing = requireConfig && !hasCommitted ? [message('doctor.config-missing')] : [];
  if (!hasCommitted && !isFile(join(root, localConfigFile()))) return missing;
  let config: LaConfig;
  try {
    config = loadConfig(root);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    return [...missing, error.message];
  }
  return hasCommitted ? consistency(root, config) : missing;
}

/** A quiet git run's status and stdout; status null when git cannot start or is killed. */
function git(root: string, ...args: string[]): { status: number | null; stdout: Buffer } {
  const proc = spawnSync('git', args, { cwd: root }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  return { status: proc.error === undefined ? proc.status : null, stdout: proc.stdout ?? Buffer.alloc(0) };
}

/** A local file that git tracks or does not ignore; checked only inside git. */
function localProblem(root: string): string | null {
  const local = localConfigFile();
  if (!existsSync(join(root, '.git')) || !isFile(join(root, local))) return null;
  const listed = git(root, 'ls-files', '-z', '--', local);
  if (listed.status !== 0) return message('doctor.local-git-failed', { file: local });
  if (listed.stdout.length > 0) return message('doctor.local-tracked', { file: local });
  const { status } = git(root, 'check-ignore', '-q', '--', local);
  if (status === 1) return message('doctor.local-not-ignored', { file: local });
  return status === 0 ? null : message('doctor.local-git-failed', { file: local });
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

/** Problems found; empty means healthy. A format refusal replaces every check that reads the config. */
export function runChecks(root: string, plugin: string | null = null, requireConfig = false): string[] {
  const version = plugin !== null ? pluginProblem(plugin) : null;
  const problems = version !== null ? [version] : [];
  const refusal = checkFormat(root);
  problems.push(...(refusal !== null ? [refusal] : configProblems(root, requireConfig)));
  const local = localProblem(root);
  if (local !== null) problems.push(local);
  let executables: string[] = [...REQUIRED_EXECUTABLES];
  try {
    if (refusal === null) executables = [...executables, ...languageExecutables(root)];
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    problems.push(error.message);
  }
  for (const exe of executables) {
    if (!which(exe)) problems.push(message('doctor.missing-executable', { exe }));
  }
  return problems;
}

export function run(root: string, plugin: string | null, printHash: boolean, requireConfig = false): number {
  if (printHash) {
    process.stdout.write(`${contractHash()}\n`);
    return 0;
  }
  const problems = runChecks(root, plugin, requireConfig);
  for (const problem of problems) process.stdout.write(`${message('doctor.fail', { problem })}\n`);
  if (problems.length === 0) {
    let source = isFile(join(root, configFile())) ? configFile() : message('doctor.no-config-file');
    if (isFile(join(root, localConfigFile()))) source = message('doctor.local-source', { source, local: localConfigFile() });
    process.stdout.write(`${message('doctor.ok', { version: VERSION, source })}\n`);
  }
  return problems.length > 0 ? 1 : 0;
}
