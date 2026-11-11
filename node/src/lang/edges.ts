// Dependency edges between repo files for la-affected-tests: every import, resolved under each file's nearest tsconfig.
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import type * as TS from 'typescript';
import { byCodePoint, language } from '../contract/index.js';
import { isUnder, posix, stripSourceExtension } from './files.js';
import { loadProjectsFrom, owner, type Projects } from './projects.js';
import { allSpecifiers, withoutQuery } from './specifiers.js';
import { ts } from './ts.js';

const CONFIG_NAME = 'tsconfig.json';
const NODE_MODULES = 'node_modules';

function realpath(path: string): string | undefined {
  try {
    return realpathSync(path);
  } catch {
    return undefined;
  }
}

/** Resolves one repo's specifiers; deleted paths exist for the resolver. */
class EdgeResolver {
  private readonly realRoot: string;
  private readonly deleted: Set<string>;
  private readonly deletedDirs = new Set<string>();
  private readonly graph: Set<string>;
  private readonly configs = new Map<string, string | undefined>();
  private readonly projects = new Map<string, { projects: Projects; host: TS.ModuleResolutionHost }>();

  constructor(
    private readonly root: string,
    files: string[],
    deleted: string[],
  ) {
    this.realRoot = realpath(root) ?? root;
    this.deleted = new Set(deleted.map((rel) => resolve(root, rel)));
    for (const path of this.deleted) {
      for (let dir = dirname(path); isUnder(dir, root) && !this.deletedDirs.has(dir); dir = dirname(dir)) this.deletedDirs.add(dir);
    }
    this.graph = new Set([...files, ...deleted]);
  }

  /** The nearest tsconfig.json from `dir` up to the repo root. */
  private config(dir: string): string | undefined {
    if (this.configs.has(dir)) return this.configs.get(dir);
    let found: string | undefined;
    if (existsSync(join(dir, CONFIG_NAME))) found = join(dir, CONFIG_NAME);
    else if (dir !== this.root && isUnder(dirname(dir), this.root)) found = this.config(dirname(dir));
    this.configs.set(dir, found);
    return found;
  }

  private loaded(config: string | undefined): { projects: Projects; host: TS.ModuleResolutionHost } {
    const key = config ?? '';
    let entry = this.projects.get(key);
    if (entry === undefined) {
      const projects = loadProjectsFrom(config, this.root);
      const base = projects.host;
      const host: TS.ModuleResolutionHost = {
        ...base,
        fileExists: (name) => this.deleted.has(resolve(name)) || base.fileExists(name),
        directoryExists: (name) => this.deletedDirs.has(resolve(name)) || (base.directoryExists?.(name) ?? false),
        realpath: (name) => (this.deleted.has(resolve(name)) || this.deletedDirs.has(resolve(name)) ? name : (base.realpath?.(name) ?? name)),
      };
      entry = { projects, host };
      this.projects.set(key, entry);
    }
    return entry;
  }

  /** The repo-relative edge target of a resolved file: in the repo and outside node_modules, else its real path if so. */
  private target(fileName: string, projects: Projects): string | undefined {
    const path = projects.outputs.get(resolve(fileName)) ?? resolve(fileName);
    const inRepo = (abs: string, root: string): string | undefined => {
      if (!isUnder(abs, root)) return undefined;
      const rel = posix(relative(root, abs));
      return rel !== '' && !rel.split('/').includes(NODE_MODULES) ? rel : undefined;
    };
    if (this.deleted.has(path)) return inRepo(path, this.root);
    const lexical = inRepo(path, this.root);
    if (lexical !== undefined) return lexical;
    const real = realpath(path);
    return real === undefined ? undefined : (inRepo(real, this.realRoot) ?? inRepo(real, this.root));
  }

  /** Graph files at `path` with one source extension stripped and any added, or at `path/index.<ext>`. */
  private fallback(path: string): string[] {
    if (!isUnder(path, this.root)) return [];
    const rel = posix(relative(this.root, path));
    const stem = stripSourceExtension(rel);
    const extensions: string[] = language('typescript').source_extensions;
    return [...extensions.map((ext) => stem + ext), ...extensions.map((ext) => `${rel}/index${ext}`)].filter((c) => this.graph.has(c));
  }

  targets(rel: string): string[] {
    const file = resolve(this.root, rel);
    let text: string;
    try {
      if (!statSync(file).isFile()) return [];
      text = readFileSync(file, 'utf8');
    } catch {
      return [];
    }
    const { projects, host } = this.loaded(this.config(dirname(file)));
    const project = owner(projects, file);
    const format = ts().getImpliedNodeFormatForFile(file, project.cache.getPackageJsonInfoCache(), host, project.options);
    const source = ts().createSourceFile(
      file,
      text,
      { languageVersion: ts().ScriptTarget.Latest, impliedNodeFormat: format, jsDocParsingMode: ts().JSDocParsingMode.ParseNone },
      true,
    );
    const found = new Set<string>();
    const add = (target: string | undefined): void => {
      if (target !== undefined) found.add(target);
    };
    for (const literal of allSpecifiers(source)) {
      const spec = literal.text;
      const mode = ts().getModeForUsageLocation(source, literal, project.options);
      const { resolvedModule } = ts().resolveModuleName(spec, file, project.options, host, project.cache, undefined, mode);
      if (resolvedModule !== undefined) add(this.target(resolvedModule.resolvedFileName, projects));
      else if (ts().isExternalModuleNameRelative(spec)) this.fallback(resolve(dirname(file), withoutQuery(spec))).forEach(add);
    }
    for (const ref of source.referencedFiles) {
      const path = resolve(dirname(file), ref.fileName);
      if (host.fileExists(path)) add(this.target(path, projects));
      else this.fallback(path).forEach(add);
    }
    return [...found].sort(byCodePoint);
  }
}

/** Edges `[importer, target]` (repo-relative POSIX) from each of `files`; `deleted` paths resolve as if present. */
export function dependencyEdges(repoRoot: string, files: string[], deleted: string[]): [string, string][] {
  const resolver = new EdgeResolver(resolve(repoRoot), files, deleted);
  return files.flatMap((file) => resolver.targets(file).map((target): [string, string] => [file, target]));
}
