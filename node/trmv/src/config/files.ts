// The committed config files: which one trmv reads, and the refusal when they are all present.
import { join } from 'node:path';
import { configFiles, isOsError, isRegularFile, message } from '../contract/index.js';

/** A regular file, or an entry whose probe fails (reading it reports the OS error). */
function present(path: string): boolean {
  try {
    return isRegularFile(path);
  } catch (error) {
    if (isOsError(error)) return true;
    throw error;
  }
}

/** The refusal when every committed config file is at the repo root, else null. */
export function bothFilesProblem(root: string): string | null {
  const files = configFiles();
  return files.every((name) => present(join(root, name)))
    ? message('config.both-files', { first: files[0], second: files[1] })
    : null;
}

/** The committed config file trmv reads: the first of the contract's files at the repo root, else null. */
export function configSource(root: string): string | null {
  return configFiles().find((name) => present(join(root, name))) ?? null;
}

/** trmv's own config file; the others carry trmv's keys among their package's. */
export function ownFile(): string {
  return configFiles()[0] as string;
}
