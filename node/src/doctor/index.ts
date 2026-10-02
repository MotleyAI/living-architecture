// `la-doctor`: check the installed tools match the plugin and the repo config is valid.
import { existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { CONFIG_FILENAME, ConfigError, loadConfig } from '../config/index.js';
import { contractHash, message, which } from '../contract/index.js';
import { VERSION } from '../index.js';

const REQUIRED_EXECUTABLES = ['git', 'gh'];

/** Problems found; empty means healthy. */
export function runChecks(root: string, expect: string | null): string[] {
  const problems: string[] = [];
  if (expect !== null && expect !== VERSION) {
    problems.push(message('doctor.version-mismatch', { installed: VERSION, expected: expect }));
  }
  try {
    loadConfig(root);
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    problems.push(error.message);
  }
  for (const exe of REQUIRED_EXECUTABLES) {
    if (!which(exe)) problems.push(message('doctor.missing-executable', { exe }));
  }
  return problems;
}

export function run(root: string, expect: string | null, printHash: boolean): number {
  if (printHash) {
    process.stdout.write(`${contractHash()}\n`);
    return 0;
  }
  const problems = runChecks(root, expect);
  for (const problem of problems) process.stdout.write(`${message('doctor.fail', { problem })}\n`);
  if (problems.length === 0) {
    const configPath = join(root, CONFIG_FILENAME);
    const source = existsSync(configPath) && statSync(configPath).isFile() ? CONFIG_FILENAME : message('doctor.no-config-file');
    process.stdout.write(`${message('doctor.ok', { version: VERSION, source })}\n`);
  }
  return problems.length > 0 ? 1 : 0;
}
