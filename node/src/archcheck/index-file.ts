// Loading `architecture/index.yaml` and resolving where each language's code lives.
import { readFileSync, realpathSync, statSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, sep } from 'node:path';
import { YAMLError, decodeUtf8OrNull, languageIds, loadYaml, message, schema, toPlain, validate } from '../contract/index.js';

export const INDEX_REL = 'architecture/index.yaml';

/** The architecture setup is too broken to check. */
export class ArchCheckError extends Error {}

/** Architecture, docs and specs live under `repoRoot`; one language's code lives in disjoint roots under `sourceRoot`. */
export interface Layout {
  repoRoot: string;
  sourceRoot: string;
  rootPackages: string[];
}

export type Index = Map<unknown, unknown>;

/** The index's language sections, in language id order. */
export function declaredLanguages(index: Index): string[] {
  return languageIds().filter((id) => index.has(id));
}

function firstDuplicate(roots: string[]): string | undefined {
  return roots.find((root, index) => roots.indexOf(root) !== index);
}

/** The section's root key and roots; ArchCheckError, never a schema error, unless one well-formed form is set. */
function rootConfiguration(values: unknown): { key: string; roots: string[] } {
  const record = values !== null && typeof values === 'object' && !Array.isArray(values) ? (values as Record<string, unknown>) : {};
  const hasPackage = Object.hasOwn(record, 'root_package');
  const hasPackages = Object.hasOwn(record, 'root_packages');
  if (hasPackage && hasPackages) throw new ArchCheckError(message('arch-check.root-config-required'));
  if (!hasPackages) {
    const root = record.root_package;
    if (typeof root !== 'string' || !root) throw new ArchCheckError(message('arch-check.root-package-missing'));
    return { key: 'root_package', roots: [root] };
  }
  const roots = record.root_packages;
  if (!Array.isArray(roots) || roots.length === 0 || !roots.every((root) => typeof root === 'string' && root)) {
    throw new ArchCheckError(message('arch-check.root-packages-invalid'));
  }
  const duplicate = firstDuplicate(roots as string[]);
  if (duplicate !== undefined) {
    throw new ArchCheckError(message('arch-check.root-packages-overlap', { first: duplicate, second: duplicate }));
  }
  return { key: 'root_packages', roots: roots as string[] };
}

export function loadIndex(root: string): Index {
  const text = decodeUtf8OrNull(readFileSync(join(root, INDEX_REL)));
  if (text === null) throw new ArchCheckError(message('c4.index-invalid-yaml'));
  let index: unknown;
  try {
    index = loadYaml(text);
  } catch (error) {
    if (error instanceof YAMLError) throw new ArchCheckError(error.message);
    throw error;
  }
  if (!(index instanceof Map)) throw new ArchCheckError(message('arch-check.index-not-mapping'));
  const languages = declaredLanguages(index);
  if (languages.length === 0) throw new ArchCheckError(message('arch-check.no-language-section'));
  for (const language of languages) rootConfiguration(section(index, language));
  const errors = validate(schema('index'), index);
  if (errors.length > 0) throw new ArchCheckError(`${INDEX_REL}: ${errors.join('; ')}`);
  return index;
}

/** A plain view of one language section. */
export function section(index: Index, language: string): Record<string, unknown> {
  return toPlain(index.get(language));
}

/** pathlib's resolve(strict=False): the longest existing prefix realpath'd, the rest appended. */
function resolveLenient(path: string): string {
  let head = path;
  const tail: string[] = [];
  for (;;) {
    try {
      return join(realpathSync(head), ...tail);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ELOOP') throw error;
      const parent = dirname(head);
      if (parent === head) return path;
      tail.unshift(head.slice(parent.length + (parent.endsWith(sep) ? 0 : 1)));
      head = parent;
    }
  }
}

function isDir(path: string): boolean {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

/** `base/value`, which must stay under `base` (symlinks included); with `canonicalId`, no empty or `.` segments. */
function contained(
  base: string,
  key: string,
  value: string,
  escapesId: string,
  canonicalId: string | null,
  values: Record<string, unknown> = {},
): string {
  if (!value || isAbsolute(value)) throw new ArchCheckError(message('arch-check.layout-not-relative', { key, value }));
  if (value.split('/').includes('..')) throw new ArchCheckError(message('arch-check.layout-parent-segment', { key, value }));
  if (canonicalId !== null && value.split('/').some((s) => s === '' || s === '.')) {
    throw new ArchCheckError(message(canonicalId, { value }));
  }
  const joined = join(base, value);
  if (value.includes('\0')) return joined;
  let resolved: string;
  try {
    resolved = resolveLenient(joined);
  } catch {
    return joined;
  }
  const rel = relative(resolveLenient(base), resolved);
  if (rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel)) {
    throw new ArchCheckError(message(escapesId, { value, ...values }));
  }
  return joined;
}

function containsPath(parent: string, candidate: string): boolean {
  const rel = relative(parent, candidate);
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel));
}

function rootsOverlap(first: string, second: string): boolean {
  return containsPath(first, second) || containsPath(second, first);
}

/** One root's real directory; ArchCheckError, naming `key`, unless it is a directory under `sourceRoot`. */
function resolveRoot(sourceRoot: string, key: string, root: string, shown: string): string {
  const ids = `arch-check.${key.replaceAll('_', '-')}`;
  const packageDir = contained(sourceRoot, key, root, `${ids}-escapes`, `${ids}-not-canonical`, { source_root: shown });
  if (root.includes('\0') || !isDir(packageDir)) {
    throw new ArchCheckError(message(`${ids}-not-a-directory`, { value: root, source_root: shown }));
  }
  return resolveLenient(packageDir);
}

/** ArchCheckError unless every root resolves under `sourceRoot` and no two are equal or nested. */
function resolveRoots(sourceRoot: string, key: string, roots: string[], shown: string): void {
  const resolved: { root: string; path: string }[] = [];
  for (const root of roots) {
    const path = resolveRoot(sourceRoot, key, root, shown);
    const previous = resolved.find((entry) => rootsOverlap(entry.path, path));
    if (previous !== undefined) {
      throw new ArchCheckError(message('arch-check.root-packages-overlap', { first: previous.root, second: root }));
    }
    resolved.push({ root, path });
  }
}

/** Where one language's code lives; ArchCheckError unless its roots are disjoint directories under `source_root`. */
export function resolveLayout(repoRoot: string, sectionValues: Record<string, unknown>): Layout {
  const { key, roots } = rootConfiguration(sectionValues);
  const value = sectionValues.source_root as string | undefined;
  let sourceRoot = repoRoot;
  if (value !== undefined && value !== null) {
    sourceRoot = contained(repoRoot, 'source_root', value, 'arch-check.source-root-escapes', null);
    if (!isDir(sourceRoot)) throw new ArchCheckError(message('arch-check.source-root-not-a-directory', { value }));
  }
  const shown = value === undefined || value === null ? '.' : value;
  resolveRoots(sourceRoot, key, roots, shown);
  return { repoRoot, sourceRoot, rootPackages: roots };
}

/** The section's `tsconfig`, or null; ArchCheckError unless it stays in the repo. */
export function resolveTsconfig(repoRoot: string, rawValue: unknown): string | null {
  const value = typeof rawValue === 'string' ? rawValue : undefined;
  if (value === undefined) return null;
  contained(repoRoot, 'tsconfig', value, 'arch-check.tsconfig-escapes', null);
  return value;
}
