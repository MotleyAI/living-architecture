// The change set: base-ref resolution and the NUL-delimited git change listing.
import { spawnSync } from 'node:child_process';
import { ConfigError } from '../config/index.js';
import { byCodePoint, message } from '../contract/index.js';

export interface ListingOptions {
  baseRef: string;
  repoRoot: string;
  deletions: boolean;
  untracked: boolean;
}

/** git's stdout; ConfigError with git's stderr, else the shared text. */
function git(args: string[], cwd: string): Buffer {
  const proc = spawnSync('git', args, { cwd, maxBuffer: 1 << 30 }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  if (proc.status !== 0) {
    const detail = proc.stderr?.toString('utf8').trim() ?? '';
    throw new ConfigError(detail || message('changes.git-failed', { args: args.join(' ') }));
  }
  return proc.stdout;
}

function nulSplit(listing: Buffer): Buffer[] {
  const out: Buffer[] = [];
  let start = 0;
  for (let i = listing.indexOf(0); i !== -1; i = listing.indexOf(0, start)) {
    if (i > start) out.push(listing.subarray(start, i));
    start = i + 1;
  }
  if (start < listing.length) out.push(listing.subarray(start));
  return out;
}

function uniqueSorted(paths: Buffer[]): Buffer[] {
  const seen = new Map<string, Buffer>();
  for (const path of paths) seen.set(path.toString('hex'), path);
  return [...seen.values()].sort(Buffer.compare);
}

/** The base branch of PR `pr`; ConfigError when `gh` cannot tell. */
export function prBaseBranch(pr: string | null, repo: string | null, repoRoot: string): string {
  const cmd = ['pr', 'view', String(pr), '--json', 'baseRefName', '--jq', '.baseRefName', ...(repo ? ['--repo', repo] : [])];
  const proc = spawnSync('gh', cmd, { cwd: repoRoot, encoding: 'utf8' }); // NOSONAR(S4036) — runs the user's own gh from PATH by design
  const branch = (proc.stdout ?? '').trim();
  if (proc.status !== 0 || !branch) throw new ConfigError(message('changes.pr-base-unresolved', { pr }));
  return branch;
}

/** `origin/<base>` after a best-effort fetch; ConfigError when it does not resolve. */
export function resolveBaseRef(base: string, repoRoot: string): string {
  spawnSync('git', ['fetch', 'origin', base, '--quiet'], { cwd: repoRoot, stdio: 'ignore' }); // NOSONAR(S4036) — runs the user's own git from PATH by design
  const ref = `origin/${base}`;
  git(['rev-parse', '--verify', '--quiet', ref], repoRoot);
  return ref;
}

/** Changed paths as raw bytes in byte order: the merge-base diff, working-tree edits and optionally deletions and untracked files. */
export function changedPathBytes({ baseRef, repoRoot, deletions, untracked }: ListingOptions): Buffer[] {
  const filter = deletions ? [] : ['--diff-filter=ACMR'];
  const found: Buffer[] = [];
  for (const target of [`${baseRef}...HEAD`, 'HEAD']) {
    found.push(...nulSplit(git(['diff', '-z', '--name-only', '--no-renames', ...filter, target], repoRoot)));
  }
  if (untracked) found.push(...nulSplit(git(['ls-files', '-z', '--others', '--exclude-standard'], repoRoot)));
  return uniqueSorted(found);
}

/** `changedPathBytes` decoded, in code-point order. */
export function changedPaths(options: ListingOptions): string[] {
  return [...new Set(changedPathBytes(options).map((path) => path.toString('utf8')))].sort(byCodePoint);
}

/** Every tracked and untracked, not ignored path, as raw bytes in byte order. */
export function repoPathBytes(repoRoot: string): Buffer[] {
  return uniqueSorted(nulSplit(git(['ls-files', '-z', '--cached', '--others', '--exclude-standard'], repoRoot)));
}
