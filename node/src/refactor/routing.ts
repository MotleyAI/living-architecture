// Routing `dr-*` inputs by file language: own-language files run here, the other language's in its twin.
import { lstatSync, readdirSync, readlinkSync, realpathSync, statSync } from 'node:fs';
import { basename, dirname, isAbsolute, join, relative, sep } from 'node:path';
import { ConfigError, findRepoRoot, loadConfig, repoLanguages } from '../config/index.js';
import { byCodePoint, globMatch, language, languageIds, languageOf, message } from '../contract/index.js';
import * as twin from '../twin/index.js';

// The kernel's own symlink limit (Linux MAXSYMLINKS); past it every file call fails with ELOOP anyway.
const MAX_SYMLINK_HOPS = 40;

/** The inputs cannot be routed; the message is printed (exit 2 for dr-compliance/dr-mock-lint, 1 for dr-refactor). */
export class RoutingError extends Error {}

/** A path as Python's PurePosixPath prints it: no empty or `.` segments, `.` when nothing is left. */
export function purePath(raw: string): string {
  const segments = raw.split('/').filter((s) => s !== '' && s !== '.');
  return `${raw.startsWith('/') ? '/' : ''}${segments.join('/')}` || '.';
}

function stat(path: string): ReturnType<typeof statSync> | undefined {
  try {
    return statSync(path);
  } catch {
    return undefined;
  }
}

const isSymlink = (path: string): boolean => {
  try {
    return lstatSync(path).isSymbolicLink();
  } catch {
    return false;
  }
};

/** `rel` under `base` without collapsing `..`, so a symlink before it is followed first. */
export const under = (base: string, rel: string): string => (isAbsolute(rel) ? rel : `${base}${sep}${rel}`);

/** `path` with its symlinks resolved component by component as far as it exists, like `os.path.realpath`. */
export function realPath(path: string, hops = 0): string {
  try {
    return realpathSync.native(path);
  } catch {
    // missing, dangling or a loop: resolve what can be resolved
  }
  const parent = dirname(path);
  if (hops < MAX_SYMLINK_HOPS && isSymlink(path)) return realPath(under(parent, readlinkSync(path)), hops + 1);
  return parent === path ? path : join(realPath(parent, hops), basename(path));
}

const isDir = (path: string): boolean => stat(path)?.isDirectory() === true;

const declaration = (path: string, id: string): boolean => (language(id).declaration_globs as string[]).some((glob) => globMatch(glob, path));

/** Python's Path ordering: segment by segment, each by code point. */
function bySegments(a: string, b: string): number {
  const [x, y] = [a.split('/'), b.split('/')];
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const d = byCodePoint(x[i] ?? '', y[i] ?? '');
    if (d !== 0) return d;
  }
  return x.length - y.length;
}

/** Every file under `dir` (symlinked directories not entered, `pruned` directory names skipped), as `dir`-joined paths. */
function filesUnder(dir: string, pruned: Set<string> = new Set()): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = dir === '.' ? entry.name : `${dir}/${entry.name}`;
    if (entry.isDirectory()) return pruned.has(entry.name) ? [] : filesUnder(path, pruned);
    return stat(path)?.isFile() === true ? [path] : [];
  });
}

function expansionLanguages(root: string): string[] {
  try {
    const languages = repoLanguages(root, loadConfig(root));
    return languages.length > 0 ? languages : languageIds();
  } catch (error) {
    if (error instanceof ConfigError) throw new RoutingError(error.message);
    throw error;
  }
}

const excludedDirs = (id: string): string[] => language(id).excluded_dirs as string[];

/** `dir`'s directory names from the repo `root` down; none when it is outside the repo. */
function segmentsBelowRoot(dir: string, root: string): string[] {
  const rel = relative(root, realPath(under(process.cwd(), dir)));
  return rel === '' || rel.split(sep)[0] === '..' || isAbsolute(rel) ? [] : rel.split(sep);
}

/** (language, path) of each file under `dir` the languages check, in path order; excluded names count from `root` down. */
function expand(dir: string, languages: string[], root: string): [string, string][] {
  const prefix = segmentsBelowRoot(dir, root);
  const [first, ...rest] = languages;
  const pruned = new Set(first === undefined ? [] : excludedDirs(first).filter((d) => rest.every((id) => excludedDirs(id).includes(d))));
  const out: [string, string][] = [];
  for (const path of filesUnder(dir, pruned).sort(bySegments)) {
    const name = path.split('/').pop() ?? '';
    const id = languageOf(name);
    if (id === null || !languages.includes(id) || declaration(path, id)) continue;
    const below = (dir === '.' ? path : path.slice(dir.length + 1)).split('/').slice(0, -1);
    if ([...prefix, ...below].some((segment) => excludedDirs(id).includes(segment))) continue;
    out.push([id, path]);
  }
  return out;
}

/** Paths grouped by language; directories expanded, non-source files skipped with a warning. */
export function split(prog: string, rawPaths: string[]): Map<string, string[]> {
  const groups = new Map<string, string[]>();
  const add = (id: string, path: string): void => {
    groups.set(id, [...(groups.get(id) ?? []), path]);
  };
  let languages: string[] | null = null;
  const root = realPath(findRepoRoot(process.cwd()));
  for (const raw of rawPaths) {
    const path = purePath(raw);
    if (isDir(raw)) {
      languages ??= expansionLanguages(root);
      for (const [id, file] of expand(path, languages, root)) add(id, file);
      continue;
    }
    const id = languageOf(raw);
    if (id === null || declaration(path, id)) {
      process.stderr.write(`${message('refactor.skipped', { prog, path })}\n`);
      continue;
    }
    add(id, path);
  }
  return groups;
}

/** The other language's block from its twin (captured first), then every block in registry order; exit max. */
export function runSplit(
  prog: string,
  groups: Map<string, string[]>,
  otherArgs: (files: string[]) => string[],
  native: (files: string[]) => number,
): number {
  const captured = new Map<string, Buffer>();
  const codes: number[] = [];
  for (const id of languageIds().filter((l) => groups.has(l) && l !== twin.NATIVE_LANGUAGE)) {
    let result: [number, Buffer];
    try {
      result = twin.runCaptured(prog, id, otherArgs(groups.get(id) ?? []), findRepoRoot(process.cwd()));
    } catch (error) {
      if (!(error instanceof twin.TwinError)) throw error;
      process.stderr.write(`${message('twin.error', { prog, error: error.message })}\n`);
      return 2;
    }
    const [code, out] = result;
    if (code !== 0 && code !== 1) return 2;
    captured.set(id, out);
    codes.push(code);
  }
  for (const id of languageIds().filter((l) => groups.has(l))) {
    if (id === twin.NATIVE_LANGUAGE) codes.push(native(groups.get(id) ?? []));
    else process.stdout.write(captured.get(id) ?? Buffer.alloc(0));
  }
  return Math.max(0, ...codes);
}

/**
 * A file's language by extension; a directory's is its expansion's one language, else the first language with a
 * source file under it. The expansion takes the languages of `project`'s repo; RoutingError when it holds more than one.
 */
function sourceLanguage(path: string, project: string): string | null {
  if (!isDir(path)) return languageOf(path);
  const root = realPath(findRepoRoot(realPath(under(process.cwd(), project))));
  const ids = new Set(expand(purePath(path), expansionLanguages(root), root).map(([id]) => id));
  const expanded = languageIds().filter((id) => ids.has(id));
  if (expanded.length > 1) throw new RoutingError(message('refactor.mixed-languages', { path, languages: expanded.join(', ') }));
  if (expanded.length === 1) return expanded[0] ?? null;
  const found = new Set(filesUnder(purePath(path)).map((f) => languageOf(f.split('/').pop() ?? '')));
  return languageIds().find((id) => found.has(id)) ?? null;
}

/** RoutingError unless `source` is in `project` and a file (or a directory when `allowDir`). */
function checkSource(source: string, project: string, allowDir: boolean): void {
  const cwd = process.cwd();
  const path = realPath(under(cwd, source));
  const rel = relative(realPath(under(cwd, project)), path);
  if (rel.split(sep)[0] === '..' || isAbsolute(rel)) throw new RoutingError(message('refactor.outside-project', { path: source }));
  const found = stat(path);
  if (found?.isFile() !== true && !(allowDir && found?.isDirectory() === true)) {
    throw new RoutingError(message('refactor.source-missing', { path: source }));
  }
}

/** The language `dr-refactor` runs in; RoutingError for a bad or unsupported source or a cross-language dest. */
export function refactorLanguage(subcommand: string, source: string, dest: string, project: string): string {
  checkSource(source, project, subcommand === 'move-module');
  const id = sourceLanguage(source, project);
  if (id === null) throw new RoutingError(message('refactor.unsupported-extension', { path: source }));
  if (subcommand === 'move-symbol' && languageOf(dest) !== id) {
    throw new RoutingError(message('refactor.cross-language-dest', { dest, language: id }));
  }
  return id;
}

/** The selected check ids (null: every check); RoutingError naming ids no language lists. */
export function complianceSelection(select: string | null): Set<string> | null {
  if (select === null) return null;
  const selected = new Set(select.split(',').map((c) => c.trim()).filter(Boolean));
  const known = new Set(languageIds().flatMap((id) => language(id).compliance_checks as string[]));
  const unknown = [...selected].filter((c) => !known.has(c)).sort(byCodePoint);
  if (unknown.length > 0) throw new RoutingError(message('compliance.unknown-checks', { checks: unknown.join(', ') }));
  return selected;
}
