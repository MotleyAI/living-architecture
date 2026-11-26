// `la-doctor`: check the installed tools match the plugin's minor series and the repo config is valid.
import { spawnSync } from 'node:child_process';
import { existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { ConfigError, bothFilesProblem, checkFormat, repoLanguages } from 'type-rename-move/config';
import * as twin from 'type-rename-move/twin';
import { type LaConfig, languagesOf, loadConfig, loadRaw, resolveRaw } from '../config/index.js';
import {
  LA,
  configFile,
  contractHash,
  identity,
  isOsError,
  isRegularFile,
  language,
  localConfigFile,
  message,
  osErrorText,
  pluginProblem,
  which,
  whichPath,
} from '../contract/index.js';
import { NATIVE_LANGUAGE, VERSION } from '../index.js';

const REQUIRED_EXECUTABLES = ['git', 'gh'];

const pluginName = (): string => LA.yaml('cli.yaml').plugin;

const install = (version: string): string => twin.installCommand(NATIVE_LANGUAGE, identity(), version);

const isFile = (path: string): boolean => existsSync(path) && statSync(path).isFile();

/** The first `trmv-doctor` on PATH missing, or reporting another language, version or trmv contract than la runs with. */
export function trmvProblem(): string | null {
  const trmv = twin.trmvIdentity();
  const expected = twin.line({ ...trmv, version: VERSION }, NATIVE_LANGUAGE);
  const found = whichPath(trmv.doctor);
  if (!found) return message('doctor.trmv-missing', { install: install(VERSION) });
  const proc = spawnSync(found, ['--twin'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  const reported = proc.error === undefined && proc.status === 0 ? proc.stdout.trim() : '';
  if (reported === expected) return null;
  return message('doctor.trmv-mismatch', { reported, version: VERSION, expected, install: install(VERSION) });
}

/** Whether `path` is a regular file, or the OS error probing it. */
function probe(root: string, path: string): boolean | string {
  try {
    return isRegularFile(path);
  } catch (error) {
    if (isOsError(error)) return osErrorText(error, root);
    throw error;
  }
}

const isDir = (path: string): boolean => existsSync(path) && statSync(path).isDirectory();

/** The config's gate decisions that the disk contradicts, in a fixed order. */
function consistency(root: string, config: LaConfig, requirePlanStore: boolean): string[] {
  const problems: string[] = [];
  const hasOpenspec = isDir(join(root, 'openspec'));
  if (config.openspec !== hasOpenspec) {
    problems.push(message(config.openspec ? 'doctor.openspec-absent' : 'doctor.openspec-present'));
  }
  const hasArchitecture = probe(root, join(root, 'architecture', 'index.yaml'));
  if (typeof hasArchitecture === 'string') problems.push(hasArchitecture);
  else if (config.architecture !== hasArchitecture) {
    problems.push(message(config.architecture ? 'doctor.architecture-absent' : 'doctor.architecture-present'));
  }
  if (requirePlanStore && config.tracker === 'none' && !config.openspec) problems.push(message('doctor.no-plan-store'));
  return problems;
}

function configProblems(root: string, requireConfig: boolean, requirePlanStore: boolean): string[] {
  const hasCommitted = probe(root, join(root, configFile()));
  if (typeof hasCommitted === 'string') return [hasCommitted];
  const hasLocal = probe(root, join(root, localConfigFile()));
  if (typeof hasLocal === 'string') return [hasLocal];
  const missing = requireConfig && !hasCommitted ? [message('doctor.config-missing')] : [];
  if (!hasCommitted && !hasLocal) return missing;
  let config: LaConfig;
  try {
    config = loadConfig(root);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    return [...missing, error.message];
  }
  return hasCommitted ? consistency(root, config, requirePlanStore) : missing;
}

/** A quiet git run's status and stdout; status null when git cannot start or is killed. */
function git(root: string, ...args: string[]): { status: number | null; stdout: Buffer } {
  const proc = spawnSync('git', args, { cwd: root }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  return { status: proc.error === undefined ? proc.status : null, stdout: proc.stdout ?? Buffer.alloc(0) };
}

/** A local file that git tracks or does not ignore; checked only inside git. */
function localProblem(root: string): string | null {
  const local = localConfigFile();
  // An error probing the local file is reported by the config checks.
  if (!existsSync(join(root, '.git')) || probe(root, join(root, local)) !== true) return null;
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
  let settings;
  try {
    const raw = loadRaw(root);
    settings = languagesOf(resolveRaw(root, raw), raw);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    return [];
  }
  return repoLanguages(root, settings).flatMap((id) => language(id).executables as string[]);
}

/** Problems found; empty means healthy. Both config files present, or a format refusal, replace every check that reads the config. */
export function runChecks(
  root: string,
  plugin: string | null = null,
  requireConfig = false,
  requirePlanStore = false,
): string[] {
  const version = plugin !== null ? pluginProblem(plugin, pluginName(), VERSION, install) : null;
  const problems = version !== null ? [version] : [];
  const trmv = trmvProblem();
  if (trmv !== null) problems.push(trmv);
  const refusal = bothFilesProblem(root) ?? checkFormat(root, configFile());
  problems.push(...(refusal !== null ? [refusal] : configProblems(root, requireConfig, requirePlanStore)));
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

export function run(
  root: string,
  plugin: string | null,
  printHash: boolean,
  requireConfig = false,
  requirePlanStore = false,
): number {
  if (printHash) {
    process.stdout.write(`${contractHash()}\n`);
    return 0;
  }
  const problems = runChecks(root, plugin, requireConfig, requirePlanStore);
  for (const problem of problems) process.stdout.write(`${message('doctor.fail', { problem })}\n`);
  if (problems.length === 0) {
    let source = isFile(join(root, configFile())) ? configFile() : message('doctor.no-config-file');
    if (isFile(join(root, localConfigFile()))) source = message('doctor.local-source', { source, local: localConfigFile() });
    process.stdout.write(`${message('doctor.ok', { package: pluginName(), version: VERSION, source })}\n`);
  }
  return problems.length > 0 ? 1 : 0;
}
