// The config files: the root files and the stealth files in the git common directory, which one a package reads, and
// the refusal when more than one is present.
import { spawnSync } from 'node:child_process';
import { basename, dirname, join } from 'node:path';
import { configFiles, isOsError, isRegularFile, message, stealthFiles } from '../contract/index.js';
import { ConfigError } from './error.js';

/** A regular file, or an entry whose probe fails (reading it reports the OS error). */
function present(path: string): boolean {
  try {
    return isRegularFile(path);
  } catch (error) {
    if (isOsError(error)) return true;
    throw error;
  }
}

/** A config file a command reads, and whether it is a stealth one (in the git common directory). */
export interface ConfigFile {
  path: string;
  stealth: boolean;
}

/** How messages name a config file: a root file by its name, a stealth file by its absolute path. */
export function displayName(file: ConfigFile): string {
  return file.stealth ? file.path : basename(file.path);
}

/** The absolute git common directory of the working tree holding `start`; null outside git. */
export function commonDir(start: string): string | null {
  const proc = spawnSync('git', ['rev-parse', '--path-format=absolute', '--git-common-dir'], { cwd: start }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  const out = proc.stdout?.toString('utf8').replace(/\n$/, '') ?? '';
  return proc.status === 0 && out ? out : null;
}

/** `pkg`'s stealth directory under the git common directory of `start`; null outside git. */
export function stealthDir(start: string, pkg: string): string | null {
  const common = commonDir(start);
  const rel = stealthFiles().find(([owner]) => owner === pkg)?.[1];
  return common === null || rel === undefined ? null : dirname(join(common, rel));
}

/** Every config file present for `root`, in lookup order: the root files, then the stealth files. */
export function presentFiles(root: string): ConfigFile[] {
  const found = configFiles()
    .map((name) => ({ path: join(root, name), stealth: false }))
    .filter((f) => present(f.path));
  const common = commonDir(root);
  if (common !== null) {
    found.push(...stealthFiles().map(([, rel]) => ({ path: join(common, rel), stealth: true })).filter((f) => present(f.path)));
  }
  return found;
}

/** The refusal when more than one config file is present for `root`, else null. */
export function filesProblem(root: string): string | null {
  const found = presentFiles(root);
  if (found.length < 2) return null;
  if (!found.some((f) => f.stealth)) {
    const files = configFiles();
    return message('config.both-files', { first: files[0], second: files[1] });
  }
  return message('config.multiple-files', { files: found.map(displayName).join(', ') });
}

/** The config file `pkg`'s commands read at `start`: trmv reads the first present, la only its own file; ConfigError
 * when more than one is present. */
export function findConfig(start: string, pkg: string): ConfigFile | null {
  const problem = filesProblem(start);
  if (problem !== null) throw new ConfigError(problem);
  let found = presentFiles(start);
  if (pkg !== 'trmv') {
    const own = basename(stealthFiles().find(([owner]) => owner === pkg)?.[1] ?? '');
    found = found.filter((f) => basename(f.path) === own);
  }
  return found[0] ?? null;
}

/** Whether `pkg`'s commands at `root` read a stealth config file; ConfigError when several are present. */
export function isStealth(root: string, pkg = 'trmv'): boolean {
  return findConfig(root, pkg)?.stealth ?? false;
}

/** How messages name the config file `pkg` reads at `root`, null without one; ConfigError when several. */
export function configSource(root: string, pkg = 'trmv'): string | null {
  const found = findConfig(root, pkg);
  return found === null ? null : displayName(found);
}

/** trmv's own config file; the others carry trmv's keys among their package's. */
export function ownFile(): string {
  return configFiles()[0] as string;
}

/** ConfigError when stealth config file `name` sets what cannot stay private. */
export function stealthRefusal(data: unknown, name: string): void {
  if (data instanceof Map && data.get('architecture') === true) {
    throw new ConfigError(message('config.stealth-architecture', { path: name }));
  }
}
