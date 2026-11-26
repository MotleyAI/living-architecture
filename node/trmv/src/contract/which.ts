// Executable lookup with Python's `shutil.which` semantics on POSIX, so both twins find the same tools.
import { accessSync, constants, statSync } from 'node:fs';
import { delimiter, join, sep } from 'node:path';

/** `os.confstr('CS_PATH')`: the search path when PATH is unset. */
const DEFAULT_PATH = process.platform === 'darwin' ? '/usr/bin:/bin:/usr/sbin:/sbin' : '/bin:/usr/bin';

function executable(path: string): boolean {
  try {
    accessSync(path, constants.X_OK);
    return !statSync(path).isDirectory();
  } catch {
    return false;
  }
}

/** The executable `name`: as given when it has a directory part, else the first in a PATH directory ('' is the cwd). */
export function whichPath(name: string, env: NodeJS.ProcessEnv = process.env): string | null {
  if (name.includes(sep)) return executable(name) ? name : null;
  const search = env.PATH ?? DEFAULT_PATH;
  if (search === '') return null;
  return [...new Set(search.split(delimiter))].map((dir) => join(dir, name)).find(executable) ?? null;
}

/** Whether `name` is executable (see `whichPath`). */
export function which(name: string, env: NodeJS.ProcessEnv = process.env): boolean {
  return whichPath(name, env) !== null;
}
