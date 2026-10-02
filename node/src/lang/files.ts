// Visible TypeScript source files, units and module ids under a section's source_root.
import { readdirSync, realpathSync, statSync, type Stats } from 'node:fs';
import { basename, dirname, join, relative, resolve, sep } from 'node:path';
import { globMatch, language } from '../contract/index.js';
import type { TsLayout, UnitStatus } from './types.js';

export const DECLARATION_RE = /\.d\.[cm]?ts$/;
const NODE_MODULES = 'node_modules';

export const posix = (path: string): string => path.split(sep).join('/');

function sourceExtensions(): string[] {
  return language('typescript').source_extensions;
}

/** The longest source extension `name` ends with, if any. */
export function sourceExtension(name: string): string | undefined {
  return sourceExtensions()
    .filter((ext) => name.endsWith(ext))
    .sort((a, b) => b.length - a.length)[0];
}

export function stripSourceExtension(path: string): string {
  const ext = sourceExtension(path);
  return ext === undefined ? path : path.slice(0, -ext.length);
}

function realpath(path: string): string | undefined {
  try {
    return realpathSync(path);
  } catch {
    return undefined;
  }
}

/** The real path, or the resolved path when it does not exist. */
export function canonical(path: string): string {
  return realpath(path) ?? resolve(path);
}

function stat(path: string): Stats | undefined {
  try {
    return statSync(path);
  } catch {
    return undefined;
  }
}

export function isUnder(path: string, root: string): boolean {
  return path === root || path.startsWith(root + sep);
}

/** Walks a layout's files: symlinks only while their real path stays under source_root. */
export class Tree {
  readonly realSourceRoot: string;

  constructor(readonly layout: TsLayout) {
    this.realSourceRoot = realpath(layout.sourceRoot) ?? layout.sourceRoot;
  }

  get packageDir(): string {
    return join(this.layout.sourceRoot, this.layout.rootPackage);
  }

  inside(path: string): boolean {
    const real = realpath(path);
    return real !== undefined && isUnder(real, this.realSourceRoot);
  }

  /** A source file the arch-check sees: a source extension, no `*.d.ts`, no test glob, no `node_modules`. */
  visible(path: string): boolean {
    const name = basename(path);
    if (sourceExtension(name) === undefined || DECLARATION_RE.test(name)) return false;
    const rel = posix(relative(this.layout.repoRoot, path));
    if (rel.split('/').includes(NODE_MODULES)) return false;
    const globs: string[] = language('typescript').test_globs;
    return !globs.some((glob) => globMatch(glob, rel)) && this.inside(path) && stat(path)?.isFile() === true;
  }

  /** A directory the walk may enter. */
  enterable(path: string): boolean {
    return basename(path) !== NODE_MODULES && stat(path)?.isDirectory() === true && this.inside(path);
  }

  /** Visible source files under `dir`, in name order; each real directory once. */
  *files(dir: string, visited = new Set<string>()): Generator<string> {
    const real = realpath(dir);
    if (real === undefined || visited.has(real)) return;
    visited.add(real);
    for (const name of readdirSync(dir).sort()) {
      const path = join(dir, name);
      if (this.enterable(path)) yield* this.files(path, visited);
      else if (this.visible(path)) yield path;
    }
  }

  hasSource(dir: string): boolean {
    return this.enterable(dir) && !this.files(dir).next().done;
  }

  /** Extensionless source_root-relative path; `<dir>/index.<ext>` is `<dir>`. */
  moduleId(path: string, root = this.layout.sourceRoot): string {
    const id = posix(stripSourceExtension(relative(root, path)));
    return basename(id) === 'index' ? posix(dirname(id)) : id;
  }

  unitStatus(unit: string): UnitStatus {
    const base = join(this.layout.sourceRoot, unit);
    const candidates = sourceExtensions()
      .filter((ext) => this.visible(base + ext))
      .map((ext) => unit + ext);
    if (this.hasSource(base)) candidates.push(`${unit}/`);
    candidates.sort();
    if (candidates.length > 1) return { status: 'ambiguous', candidates };
    return { status: candidates.length === 1 ? 'present' : 'missing', candidates: [] };
  }

  topLevelUnits(): string[] {
    const units = new Set<string>();
    for (const name of readdirSync(this.packageDir)) {
      const path = join(this.packageDir, name);
      const isBarrel = stripSourceExtension(name) === 'index';
      if ((this.visible(path) && !isBarrel) || this.hasSource(path)) {
        units.add(posix(join(this.layout.rootPackage, stripSourceExtension(name))));
      }
    }
    return [...units].sort();
  }
}
