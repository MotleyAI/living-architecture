// `la-doctor`: check the installed tools match the plugin and the repo config is valid.
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { CONFIG_FILENAME, ConfigError, loadConfig } from '../config/index.js';
import { contractHash, message, which } from '../contract/index.js';
import { VERSION } from '../index.js';

const REQUIRED_EXECUTABLES = ['git', 'gh'];
const PLUGIN_MANIFEST = join('.claude-plugin', 'plugin.json');

function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

function versionProblem(expected: string): string | null {
  return expected === VERSION ? null : message('doctor.version-mismatch', { installed: VERSION, expected });
}

function manifestVersion(path: string): unknown {
  try {
    const data: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(readFileSync(path)));
    return data !== null && typeof data === 'object' && !Array.isArray(data) ? (data as Record<string, unknown>).version : null;
  } catch {
    return null;
  }
}

/** Check against the version in the nearest `.claude-plugin/plugin.json` at or above `plugin`. */
function pluginProblem(plugin: string): string | null {
  const start = resolve(plugin);
  for (let dir = start; ; dir = dirname(dir)) {
    const manifest = join(dir, PLUGIN_MANIFEST);
    if (isFile(manifest)) {
      const version = manifestVersion(manifest);
      const valid = typeof version === 'string' && !/\p{Surrogate}/u.test(version);
      return valid ? versionProblem(version) : message('doctor.plugin-invalid', { path: manifest });
    }
    if (dirname(dir) === dir) return message('doctor.plugin-not-found', { dir: start });
  }
}

/** Problems found; empty means healthy. */
export function runChecks(root: string, expect: string | null, plugin: string | null = null): string[] {
  const versions = [expect !== null ? versionProblem(expect) : null, plugin !== null ? pluginProblem(plugin) : null];
  const problems = versions.filter((problem): problem is string => problem !== null);
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

export function run(root: string, expect: string | null, plugin: string | null, printHash: boolean): number {
  if (printHash) {
    process.stdout.write(`${contractHash()}\n`);
    return 0;
  }
  const problems = runChecks(root, expect, plugin);
  for (const problem of problems) process.stdout.write(`${message('doctor.fail', { problem })}\n`);
  if (problems.length === 0) {
    const configPath = join(root, CONFIG_FILENAME);
    const source = existsSync(configPath) && statSync(configPath).isFile() ? CONFIG_FILENAME : message('doctor.no-config-file');
    process.stdout.write(`${message('doctor.ok', { version: VERSION, source })}\n`);
  }
  return problems.length > 0 ? 1 : 0;
}
