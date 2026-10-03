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

/** Whether `name` is executable: as given when it has a directory part, else in a PATH directory ('' is the cwd). */
export function which(name: string, env: NodeJS.ProcessEnv = process.env): boolean {
  if (name.includes(sep)) return executable(name);
  const search = env.PATH ?? DEFAULT_PATH;
  if (search === '') return false;
  return [...new Set(search.split(delimiter))].some((dir) => executable(join(dir, name)));
}
