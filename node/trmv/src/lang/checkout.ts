// A checker environment for another revision: a temporary linked worktree with the environment directories linked in.
import { spawnSync } from 'node:child_process';
import { existsSync, lstatSync, mkdtempSync, realpathSync, rmSync, statSync, symlinkSync, unlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

/** The temporary worktree could not be created. */
export class CheckoutError extends Error {}

function git(repo: string, ...args: string[]): { status: number | null; stderr: string } {
  const proc = spawnSync('git', args, { cwd: repo }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  return { status: proc.status, stderr: proc.stderr?.toString('utf8') ?? '' };
}

const isDir = (path: string): boolean => existsSync(path) && statSync(path).isDirectory();

const isLink = (path: string): boolean => {
  try {
    return lstatSync(path).isSymbolicLink();
  } catch {
    return false;
  }
};

/**
 * `fn` run on `commit` checked out in a temporary linked worktree outside `repo`, with each of `environmentDirs` that
 * exists in `repo` linked in; the worktree is removed and pruned on every exit path.
 */
export function withMergeBaseCheckout<T>(repo: string, commit: string, environmentDirs: string[], fn: (checkout: string) => T): T {
  const parent = realpathSync(mkdtempSync(join(tmpdir(), 'trmv-merge-base-')));
  const checkout = join(parent, 'checkout');
  try {
    const added = git(repo, 'worktree', 'add', '--detach', '--quiet', checkout, commit);
    if (added.status !== 0) throw new CheckoutError(added.stderr.trim());
    for (const name of environmentDirs) {
      const source = join(repo, name);
      if (isDir(source) && !existsSync(join(checkout, name))) symlinkSync(realpathSync(source), join(checkout, name), 'dir');
    }
    return fn(checkout);
  } finally {
    for (const name of environmentDirs) if (isLink(join(checkout, name))) unlinkSync(join(checkout, name));
    git(repo, 'worktree', 'remove', '--force', checkout);
    rmSync(parent, { recursive: true, force: true });
    git(repo, 'worktree', 'prune');
  }
}
