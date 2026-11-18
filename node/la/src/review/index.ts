// Review shims: run a bundled contract script.
import { spawnSync } from 'node:child_process';
import { constants } from 'node:os';
import { manifest, scriptPath } from '../contract/index.js';

/** Run the command's bundled script with `argv` unchanged. */
export function runShim(command: string, argv: string[]): number {
  const proc = spawnSync('bash', [scriptPath(manifest()[command].script), ...argv], { stdio: 'inherit' }); // NOSONAR(S4036) — runs the user's own bash and tools from PATH by design
  if (proc.signal !== null) return 128 + (constants.signals[proc.signal] ?? 0);
  return proc.status ?? 1;
}
