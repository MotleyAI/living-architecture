// Loading `architecture/index.yaml` and resolving where each language's code lives.
import { readFileSync, realpathSync, statSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, sep } from 'node:path';
import { YAMLError, languageIds, loadYaml, message, schema, toPlain, validate } from '../contract/index.js';

export const INDEX_REL = 'architecture/index.yaml';

/** The architecture setup is too broken to check. */
export class ArchCheckError extends Error {}

/** Architecture, docs and specs live under `repoRoot`; one language's code lives under `sourceRoot`. */
export interface Layout {
  repoRoot: string;
  sourceRoot: string;
  rootPackage: string;
}

export type Index = Map<unknown, unknown>;

/** The index's language sections, in language id order. */
export function declaredLanguages(index: Index): string[] {
  return languageIds().filter((id) => index.has(id));
}

export function loadIndex(root: string): Index {
  let index: unknown;
  try {
    index = loadYaml(readFileSync(join(root, INDEX_REL), 'utf8'));
  } catch (error) {
    if (error instanceof YAMLError) throw new ArchCheckError(error.message);
    throw error;
  }
  if (!(index instanceof Map)) throw new ArchCheckError(message('arch-check.index-not-mapping'));
  const languages = declaredLanguages(index);
  if (languages.length === 0) throw new ArchCheckError(message('arch-check.no-language-section'));
  for (const language of languages) {
    const section = index.get(language);
    const pkg = section instanceof Map ? section.get('root_package') : undefined;
    if (typeof pkg !== 'string' || !pkg) throw new ArchCheckError(message('arch-check.root-package-missing'));
  }
  const errors = validate(schema('index'), index);
  if (errors.length > 0) throw new ArchCheckError(`${INDEX_REL}: ${errors.join('; ')}`);
  return index;
}

/** A plain view of one language section. */
export function section(index: Index, language: string): Record<string, string> {
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

/** Where one language's code lives; ArchCheckError unless `source_root` and `root_package` are dirs in the repo. */
export function resolveLayout(repoRoot: string, sectionValues: Record<string, string>): Layout {
  const rootPackage = sectionValues.root_package ?? '';
  const value = sectionValues.source_root;
  let sourceRoot = repoRoot;
  if (value !== undefined && value !== null) {
    sourceRoot = contained(repoRoot, 'source_root', value, 'arch-check.source-root-escapes', false);
    if (!isDir(sourceRoot)) throw new ArchCheckError(message('arch-check.source-root-not-a-directory', { value }));
  }
  const shown = value === undefined || value === null ? '.' : value;
  const packageDir = contained(sourceRoot, 'root_package', rootPackage, 'arch-check.root-package-escapes', true, {
    source_root: shown,
  });
  if (rootPackage.includes('\0') || !isDir(packageDir)) {
    throw new ArchCheckError(message('arch-check.root-package-not-a-directory', { value: rootPackage, source_root: shown }));
  }
  return { repoRoot, sourceRoot, rootPackage };
}
