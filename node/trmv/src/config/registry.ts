// The stealth path registries: which of a package's paths show in a stealth repo's working tree.
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { byCodePoint, message, stealthRegistry } from '../contract/index.js';
import { ConfigError } from './error.js';
import { presentFiles } from './files.js';

function listed(root: string, args: string[]): Set<string> {
  const proc = spawnSync('git', args, { cwd: root, maxBuffer: 1 << 30 }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  if (proc.status !== 0) throw new ConfigError(message('changes.git-failed', { args: args.join(' ') }));
  return new Set(proc.stdout.toString('utf8').split('\0').filter((p) => p));
}

/** Each of `paths`, then each path under one of `prefixes`, that is staged as an addition or present, untracked and
 * not ignored, in that order (a prefix's paths in code-point order), with whether it is staged. */
export function strayPaths(root: string, paths: string[], prefixes: string[] = []): [string, boolean][] {
  const staged = listed(root, ['diff', '--cached', '--name-only', '--diff-filter=A', '-z']);
  const untracked = listed(root, ['ls-files', '-z', '--others', '--exclude-standard']);
  const shown = new Set([...staged, ...untracked]);
  const found = paths.filter((p) => shown.has(p));
  for (const prefix of prefixes) {
    found.push(...[...shown].filter((p) => p.startsWith(prefix) && !found.includes(p)).toSorted(byCodePoint));
  }
  return found.map((p) => [p, staged.has(p)]);
}

/** The doctors' findings for `strayPaths`. */
export function strayFindings(root: string, paths: string[], prefixes: string[] = []): string[] {
  return strayPaths(root, paths, prefixes).map(([path, staged]) =>
    message(staged ? 'doctor.stealth-staged' : 'doctor.stealth-untracked', { path }),
  );
}

/** In a stealth repo, the findings for trmv's registry paths that show in the working tree. */
export function trmvStrayFindings(root: string): string[] {
  if (!existsSync(join(root, '.git')) || !presentFiles(root).some((f) => f.stealth)) return [];
  try {
    return strayFindings(root, stealthRegistry());
  } catch (error) {
    if (error instanceof ConfigError) return [error.message];
    throw error;
  }
}
