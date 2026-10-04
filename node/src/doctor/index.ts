// `la-doctor`: check the installed tools match the plugin and the repo config is valid.
import { existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { CONFIG_FILENAME, ConfigError, type LaConfig, loadConfig } from '../config/index.js';
import { contractHash, message, which } from '../contract/index.js';
import { VERSION } from '../index.js';

const REQUIRED_EXECUTABLES = ['git', 'gh'];

const isFile = (path: string): boolean => existsSync(path) && statSync(path).isFile();
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

/** Problems found; empty means healthy. Config-vs-disk checks run only when the config file exists. */
export function runChecks(root: string, expect: string | null, requireConfig = false): string[] {
  const problems: string[] = [];
  if (expect !== null && expect !== VERSION) {
    problems.push(message('doctor.version-mismatch', { installed: VERSION, expected: expect }));
  }
  problems.push(...configProblems(root, requireConfig));
  for (const exe of REQUIRED_EXECUTABLES) {
    if (!which(exe)) problems.push(message('doctor.missing-executable', { exe }));
  }
  return problems;
}

export function run(root: string, expect: string | null, printHash: boolean, requireConfig = false): number {
  if (printHash) {
    process.stdout.write(`${contractHash()}\n`);
    return 0;
  }
  const problems = runChecks(root, expect, requireConfig);
  for (const problem of problems) process.stdout.write(`${message('doctor.fail', { problem })}\n`);
  if (problems.length === 0) {
    const source = isFile(join(root, CONFIG_FILENAME)) ? CONFIG_FILENAME : message('doctor.no-config-file');
    process.stdout.write(`${message('doctor.ok', { version: VERSION, source })}\n`);
  }
  return problems.length > 0 ? 1 : 0;
}
