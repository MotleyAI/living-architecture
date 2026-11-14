// `PATH[:LINE]` sites of `rename --keep`, `--with` and `--without`.
import { existsSync, realpathSync } from 'node:fs';
import { isAbsolute, relative, resolve, sep } from 'node:path';

/** A site that matches nothing it must: its finding id and the site as given; exit 2. */
export class SiteError extends Error {
  constructor(
    readonly template: string,
    readonly site: string,
    readonly values: Record<string, unknown> = {},
  ) {
    super(site);
  }
}

/** A site as given, its real path's components under the project (null outside it or missing) and its line. */
export class Site {
  private constructor(
    readonly raw: string,
    readonly parts: string[] | null,
    readonly line: number | null,
  ) {}

  /** `raw` with its path resolved against `base` (the working directory by default). */
  static parse(raw: string, root: string, base: string = process.cwd()): Site {
    const m = /^(.*):(\d+)$/u.exec(raw);
    const path = m === null ? raw : (m[1] ?? '');
    const line = m === null ? null : Number(m[2]);
    const absolute = resolve(base, path);
    if (!existsSync(absolute)) return new Site(raw, null, line);
    const rel = relative(root, realpathSync(absolute));
    const inside = !isAbsolute(rel) && rel.split(sep)[0] !== '..';
    return new Site(raw, inside ? rel.split(sep).filter((p) => p !== '') : null, line);
  }

  /** `rel:line` is this site: the same line of the file, or anywhere in the file or under the directory. */
  covers(rel: string, line: number): boolean {
    if (this.parts === null) return false;
    const path = rel.split('/');
    return this.parts.every((part, i) => path[i] === part) && (this.line === null || this.line === line);
  }
}
