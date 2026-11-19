// The committed config files: which one dr reads, and the refusal when they are all present.
import { join } from 'node:path';
import { configFiles, isRegularFile, message } from '../contract/index.js';

/** The refusal when every committed config file is at the repo root, else null. */
export function bothFilesProblem(root: string): string | null {
  const files = configFiles();
  return files.every((name) => isRegularFile(join(root, name)))
    ? message('config.both-files', { first: files[0], second: files[1] })
    : null;
}

/** The committed config file dr reads: the first of the contract's files at the repo root, else null. */
export function configSource(root: string): string | null {
  return configFiles().find((name) => isRegularFile(join(root, name))) ?? null;
}

/** dr's own config file; the others carry dr's keys among their package's. */
export function ownFile(): string {
  return configFiles()[0] as string;
}
