// Review shims: run a bundled contract script.
import { spawnSync } from 'node:child_process';
import { constants } from 'node:os';
import { ConfigError, findRepoRoot, loadConfig, type LaConfig } from '../config/index.js';
import { manifest, message, scriptPath } from '../contract/index.js';

function config(prog: string): LaConfig | null {
  try {
    return loadConfig(findRepoRoot(process.cwd()));
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    process.stderr.write(`${message('review.config-error', { prog, error: error.message })}\n`);
    return null;
  }
}

/** Run the command's bundled script with `argv`; a `skip-coderabbit` gate (cli.yaml) reads the config. */
export function runShim(command: string, argv: string[]): number {
  const spec = manifest()[command];
  const args = [...argv];
  if (spec.gate === 'skip-coderabbit') {
    const loaded = config(command);
    if (loaded === null) return 2;
    if (!loaded.reviewers.coderabbit) args.push('--skip-coderabbit');
  }
  const proc = spawnSync('bash', [scriptPath(spec.script), ...args], { stdio: 'inherit' });
  if (proc.signal !== null) return 128 + (constants.signals[proc.signal] ?? 0);
  return proc.status ?? 1;
}
