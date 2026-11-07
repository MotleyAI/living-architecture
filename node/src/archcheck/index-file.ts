// Loading `architecture/index.yaml` and resolving where each language's code lives.
import { readFileSync, realpathSync, statSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, sep } from 'node:path';
import { YAMLError, decodeUtf8OrNull, languageIds, loadYaml, message, schema, toPlain, validate } from '../contract/index.js';

export const INDEX_REL = 'architecture/index.yaml';

/** The architecture setup is too broken to check. */
export class ArchCheckError extends Error {}

/** Architecture, docs and specs live under `repoRoot`; one language's code lives under `sourceRoot`. */
export interface Layout {
  repoRoot: string;
  sourceRoot: string;
  rootPackages: string[];
  /** First configured root, retained for consumers that operate on legacy single-root layouts. */
  rootPackage: string;
}

export type Index = Map<unknown, unknown>;

/** The index's language sections, in language id order. */
export function declaredLanguages(index: Index): string[] {
  return languageIds().filter((id) => index.has(id));
}

/** Requires one supported root form and validates the shape of `root_packages` before schema validation. */
function validateRootConfiguration(section: unknown): void {
  const hasPackage = section instanceof Map && section.has('root_package');
  const hasPackages = section instanceof Map && section.has('root_packages');
  if (!hasPackage && !hasPackages) throw new ArchCheckError(message('arch-check.root-package-missing'));
  if (hasPackage && hasPackages) throw new ArchCheckError(message('arch-check.root-config-required'));
  if (!hasPackages) return;
  const roots = (section as Map<unknown, unknown>).get('root_packages');
  if (!Array.isArray(roots) || roots.length === 0 || roots.some((root) => typeof root !== 'string')) {
    throw new ArchCheckError(message('arch-check.root-packages-invalid'));
  }
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
  for (const language of languages) validateRootConfiguration(index.get(language));
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

/** `base/value`, which must stay under `base` (symlinks included); `canonical`: no empty or `.` segments. */
function contained(
  base: string,
  key: string,
  value: string,
  escapesId: string,
  canonical: boolean,
  values: Record<string, unknown> = {},
): string {
  if (!value || isAbsolute(value)) throw new ArchCheckError(message('arch-check.layout-not-relative', { key, value }));
  if (value.split('/').includes('..')) throw new ArchCheckError(message('arch-check.layout-parent-segment', { key, value }));
  if (canonical && value.split('/').some((s) => s === '' || s === '.')) {
    throw new ArchCheckError(message('arch-check.root-package-not-canonical', { value }));
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

/** Returns whether `candidate` is the same path as, or nested beneath, `parent`. */
function containsPath(parent: string, candidate: string): boolean {
  const rel = relative(parent, candidate);
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel));
}

/** Returns whether two resolved roots share any directory path. */
function rootsOverlap(first: string, second: string): boolean {
  return containsPath(first, second) || containsPath(second, first);
}

/** Validates and resolves one configured package root under `sourceRoot`. */
function resolveRootPackage(
  sourceRoot: string,
  rootPackage: string,
  sourceRootDisplay: string,
  multiple: boolean,
): { value: string; path: string } {
  if (multiple && rootPackage.split('/').some((segment) => segment === '' || segment === '.')) {
    throw new ArchCheckError(message('arch-check.root-packages-not-canonical', { value: rootPackage }));
  }
  const key = multiple ? 'root_packages' : 'root_package';
  const escapedId = multiple ? 'arch-check.root-packages-escapes' : 'arch-check.root-package-escapes';
  const packageDir = contained(sourceRoot, key, rootPackage, escapedId, true, { source_root: sourceRootDisplay });
  if (rootPackage.includes('\0') || !isDir(packageDir)) {
    const id = multiple ? 'arch-check.root-packages-not-a-directory' : 'arch-check.root-package-not-a-directory';
    throw new ArchCheckError(message(id, { value: rootPackage, source_root: sourceRootDisplay }));
  }
  return { value: rootPackage, path: resolveLenient(packageDir) };
}

/** Resolves one language's code roots; configured roots must be disjoint directories under `source_root`. */
export function resolveLayout(repoRoot: string, sectionValues: Record<string, unknown>): Layout {
  const rawRoots = sectionValues.root_packages;
  const multiple = Object.hasOwn(sectionValues, 'root_packages');
  if (multiple && (!Array.isArray(rawRoots) || rawRoots.length === 0 || rawRoots.some((root) => typeof root !== 'string'))) {
    throw new ArchCheckError(message('arch-check.root-packages-invalid'));
  }
  const roots = multiple ? rawRoots as string[] : [sectionValues.root_package as string];
  const value = sectionValues.source_root as string | undefined;
  let sourceRoot = repoRoot;
  if (value !== undefined && value !== null) {
    sourceRoot = contained(repoRoot, 'source_root', value, 'arch-check.source-root-escapes', false);
    if (!isDir(sourceRoot)) throw new ArchCheckError(message('arch-check.source-root-not-a-directory', { value }));
  }
  const shown = value === undefined || value === null ? '.' : value;
  const resolvedRoots: { value: string; path: string }[] = [];
  for (const rootPackage of roots) {
    const current = resolveRootPackage(sourceRoot, rootPackage, shown, multiple);
    for (const previous of resolvedRoots) {
      if (rootsOverlap(previous.path, current.path)) {
        throw new ArchCheckError(message('arch-check.root-packages-overlap', { first: previous.value, second: rootPackage }));
      }
    }
    resolvedRoots.push(current);
  }
  return { repoRoot, sourceRoot, rootPackages: roots, rootPackage: roots[0] ?? '' };
}

/** The section's `tsconfig`, or null; ArchCheckError unless it stays in the repo. */
export function resolveTsconfig(repoRoot: string, rawValue: unknown): string | null {
  const value = typeof rawValue === 'string' ? rawValue : undefined;
  if (value === undefined) return null;
  contained(repoRoot, 'tsconfig', value, 'arch-check.tsconfig-escapes', false);
  return value;
}
