// Run a command through a CLI dispatcher in a temp repo, capturing its exit code and streams.
import { execFileSync } from 'node:child_process';
import { chmodSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { vi } from 'vitest';
import { dispatch } from '../src/cli/index.js';

export type Run = { code: number; out: string; err: string };

/** A temp git repo holding `files` (paths ending in `/bin/*` or `/.bin/*` are made executable). */
export function tempRepo(files: Record<string, string>): string {
  const root = mkdtempSync(join(tmpdir(), 'la-cli-'));
  execFileSync('git', ['init', '-q', '-b', 'main'], { cwd: root });
  for (const [rel, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, rel)), { recursive: true });
    writeFileSync(join(root, rel), text);
    if (/\/\.?bin\/[^/]+$/.test(rel)) chmodSync(join(root, rel), 0o755);
  }
  return root;
}

/** `command argv` through `dispatcher` (default: trmv's) from `root`, its exit code and captured streams. */
export function run(
  root: string,
  command: string,
  argv: string[],
  dispatcher: (command: string, argv: string[]) => number = dispatch,
): Run {
  const cwd = process.cwd();
  let out = '';
  let err = '';
  const stdout = vi.spyOn(process.stdout, 'write').mockImplementation((chunk) => ((out += String(chunk)), true));
  const stderr = vi.spyOn(process.stderr, 'write').mockImplementation((chunk) => ((err += String(chunk)), true));
  try {
    process.chdir(root);
    return { code: dispatcher(command, argv), out, err };
  } finally {
    process.chdir(cwd);
    stdout.mockRestore();
    stderr.mockRestore();
  }
}
