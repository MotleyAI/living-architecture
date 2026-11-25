// The TypeScript projects a refactor or check runs in: the reference graph, one language service per project.
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import type * as TS from 'typescript';
import {
  DuplicateKeyError,
  YAMLError,
  decodeUtf8OrNull,
  isOsError,
  isRegularFile,
  loadYaml,
  message,
  osErrorText,
  readFile,
  toPlain,
} from '../contract/index.js';
import { canonical, LangError, loadProjectsFrom, posix, type Project, type Projects, ts } from '../lang/index.js';
import { RefactorError } from './edits.js';
import { timed } from './timings.js';

/** The project's configuration cannot be read: a refusal of the run, not of one entry. */
export class WorkspaceError extends RefactorError {}

/** `typescript.tsconfig` of the root's architecture/index.yaml, else null; WorkspaceError when the index is unreadable. */
function namedConfig(root: string): string | null {
  const path = join(root, 'architecture', 'index.yaml');
  let bytes: Buffer;
  try {
    if (!isRegularFile(path)) return null;
    bytes = readFile(path);
  } catch (error) {
    if (isOsError(error)) throw new WorkspaceError(osErrorText(error, root, path));
    throw error;
  }
  const text = decodeUtf8OrNull(bytes);
  if (text === null) throw new WorkspaceError(message('c4.index-invalid-yaml'));
  let index: { typescript?: { tsconfig?: unknown } } | null;
  try {
    index = toPlain(loadYaml(text)) as typeof index;
  } catch (error) {
    if (error instanceof DuplicateKeyError) throw new WorkspaceError(message('c4.index-duplicate-key', { error: error.message }));
    if (error instanceof YAMLError) throw new WorkspaceError(message('c4.index-invalid-yaml'));
    throw error;
  }
  const named = index?.typescript?.tsconfig;
  return typeof named === 'string' ? join(root, named) : null;
}

/** The tsconfig.json files from `file`'s directory up to `root` that `exists`, outermost first. */
function ancestorConfigs(file: string, root: string, exists: (path: string) => boolean): string[] {
  const out: string[] = [];
  for (let dir = dirname(file); ; dir = dirname(dir)) {
    const rel = relative(root, dir);
    if (rel.split(sep)[0] === '..' || isAbsolute(rel)) break;
    if (exists(join(dir, 'tsconfig.json'))) out.unshift(join(dir, 'tsconfig.json'));
    if (rel === '') break;
  }
  return out;
}

/** The hook (internal in TypeScript's typings) that resolves a referenced project to its sources, not its outputs. */
interface Host extends TS.LanguageServiceHost {
  useSourceOfProjectReferenceRedirect(): boolean;
}

/** A file's text in place of the disk's: a string, null when the file is absent, undefined to read the disk. */
export type Overlay = (path: string) => string | null | undefined;

/** A directory's entries (names, not paths) in place of the disk's, as TypeScript's file matching walks them. */
export type Listing = (dir: string) => { files: string[]; directories: string[] };

/** A directory's files matching a tsconfig's extensions, excludes and includes, as TypeScript reads them. */
type ReadDirectory = (path: string, extensions?: readonly string[], excludes?: readonly string[], includes?: readonly string[], depth?: number) => string[];

/** TypeScript's internal `matchFiles`, its arguments as one labelled tuple. */
type MatchFiles = (
  ...args: [
    path: string,
    extensions: readonly string[] | undefined,
    excludes: readonly string[] | undefined,
    includes: readonly string[] | undefined,
    useCaseSensitiveFileNames: boolean,
    currentDirectory: string,
    depth: number | undefined,
    getFileSystemEntries: Listing,
    realpath: (path: string) => string,
  ]
) => string[];

/** `readDirectory` over `listing`, through TypeScript's own include and exclude matching (internal in its typings), so
 * a glob expands exactly as `sys.readDirectory` expands it over the disk. */
function listedReadDirectory(listing: Listing, currentDirectory: string): ReadDirectory {
  const matchFiles = (ts() as typeof TS & { matchFiles?: MatchFiles }).matchFiles;
  if (matchFiles === undefined) throw new Error('typescript no longer provides matchFiles');
  const sensitive = ts().sys.useCaseSensitiveFileNames;
  return (path, extensions, excludes, includes, depth) =>
    matchFiles(path, extensions, excludes, includes, sensitive, currentDirectory, depth, listing, (name) => name);
}

/** The entries of the repo-relative `paths` under `root`, by absolute directory. */
export function listingOf(root: string, paths: Iterable<string>): Listing {
  const entries = new Map<string, { files: Set<string>; directories: Set<string> }>();
  const at = (dir: string): { files: Set<string>; directories: Set<string> } => {
    const found = entries.get(dir) ?? { files: new Set<string>(), directories: new Set<string>() };
    entries.set(dir, found);
    return found;
  };
  const top = resolve(root);
  for (const path of paths) {
    const file = resolve(top, path);
    at(dirname(file)).files.add(basename(file));
    for (let dir = dirname(file); dir !== top && dirname(dir) !== dir; dir = dirname(dir)) at(dirname(dir)).directories.add(basename(dir));
  }
  return (dir) => {
    const found = entries.get(resolve(dir));
    return { files: [...(found?.files ?? [])], directories: [...(found?.directories ?? [])] };
  };
}

/** Each directory a moved file's new path lies under, by canonical path; none of them created on disk. */
function virtualDirectories(moved: Map<string, string>): Map<string, string> {
  const out = new Map<string, string>();
  for (const to of moved.values()) {
    for (let dir = dirname(to); !out.has(canonical(dir)); dir = dirname(dir)) {
      out.set(canonical(dir), dir);
      if (dirname(dir) === dir) break;
    }
  }
  return out;
}

function host(
  parsed: TS.ParsedCommandLine,
  options: TS.CompilerOptions,
  extra: string[],
  overlay: Overlay,
  moved: Map<string, string>,
  readDirectory: ReadDirectory,
  listing: Listing | null,
): Host {
  const sys = ts().sys;
  const names = [...parsed.fileNames.map((name) => moved.get(canonical(name)) ?? name), ...extra];
  const virtual = virtualDirectories(moved);
  const listed = (name: string): { files: string[]; directories: string[] } => listing?.(name) ?? { files: [], directories: [] };
  const directoryExists = (name: string): boolean => {
    const entries = listed(name);
    return virtual.has(canonical(name)) || entries.files.length > 0 || entries.directories.length > 0 || sys.directoryExists(name);
  };
  const getDirectories = (name: string): string[] => {
    const children = [...virtual.values()].filter((dir) => canonical(dirname(dir)) === canonical(name) && dirname(dir) !== dir).map((dir) => basename(dir));
    return [...new Set([...(sys.directoryExists(name) ? sys.getDirectories(name) : []), ...listed(name).directories, ...children])];
  };
  const fileExists = (name: string): boolean => {
    const text = overlay(name);
    return text === undefined ? sys.fileExists(name) : text !== null;
  };
  const readFile = (name: string): string | undefined => {
    const text = overlay(name);
    return text === undefined ? sys.readFile(name) : (text ?? undefined);
  };
  return {
    getScriptFileNames: () => names,
    getScriptVersion: (name) => {
      const text = overlay(name);
      return text == null ? '0' : createHash('sha256').update(text).digest('hex');
    },
    getScriptSnapshot: (name) => (fileExists(name) ? ts().ScriptSnapshot.fromString(readFile(name) ?? '') : undefined),
    getCurrentDirectory: () => dirname(parsed.options.configFilePath as string),
    getCompilationSettings: () => options,
    getDefaultLibFileName: (opts) => ts().getDefaultLibFilePath(opts),
    getProjectReferences: () => parsed.projectReferences,
    useSourceOfProjectReferenceRedirect: () => true,
    fileExists,
    readFile,
    readDirectory,
    directoryExists,
    getDirectories,
    realpath: sys.realpath,
  };
}

/** `service`, its program's first build timed as `load` on whichever call makes it. */
function firstBuildTimed(service: TS.LanguageService): TS.LanguageService {
  let built = false;
  const build = (): void => {
    if (built) return;
    built = true;
    timed('load', () => service.getProgram());
  };
  return new Proxy(service, {
    get(target, key, receiver): unknown {
      const value: unknown = Reflect.get(target, key, receiver);
      if (typeof value !== 'function') return value;
      return (...args: unknown[]): unknown => {
        build();
        return Reflect.apply(value, target, args);
      };
    },
  });
}

export class Workspace {
  private readonly services = new Map<Project, TS.LanguageService>();
  private readonly graphs = new Map<string, Projects>();
  private named: string | null | undefined;

  private readonly readDirectory: ReadDirectory;
  private readonly listing: Listing | null;

  /** The projects under `root` (a refactor's --project, or the repo root), loaded per file on first use; programs
   * and services read files through `overlay`, each project file under its `moved` path (by canonical old path), and
   * expand tsconfig globs over `listing` (none: the disk); `registry` shares another workspace's parsed files. */
  constructor(
    readonly root: string,
    private readonly overlay: Overlay = () => undefined,
    private readonly moved: Map<string, string> = new Map(),
    listing: Listing | null = null,
    readonly registry: TS.DocumentRegistry = ts().createDocumentRegistry(),
  ) {
    this.listing = listing;
    this.readDirectory = listing === null ? (...args) => ts().sys.readDirectory(...args) : listedReadDirectory(listing, root);
  }

  /** A file exists through the overlay, else on disk. */
  private readonly exists = (name: string): boolean => {
    const text = this.overlay(name);
    return text === undefined ? existsSync(name) : text !== null;
  };

  /** A file's text through the overlay, else from disk; undefined when absent. */
  private readonly read = (name: string): string | undefined => {
    const text = this.overlay(name);
    return text === undefined ? ts().sys.readFile(name) : (text ?? undefined);
  };

  /** A module-resolution host that sees files through the overlay. */
  resolutionHost(): TS.ModuleResolutionHost {
    return {
      fileExists: (name) => {
        const text = this.overlay(name);
        return text === undefined ? ts().sys.fileExists(name) : text !== null;
      },
      readFile: this.read,
      realpath: ts().sys.realpath,
      getCurrentDirectory: () => this.root,
    };
  }

  /** The reference graph from `config` (none: inferred defaults), its tsconfigs read through the overlay; RefactorError
   * on an unreadable tsconfig. */
  private load(config: string | undefined): Projects {
    const key = config ?? '';
    let graph = this.graphs.get(key);
    if (graph === undefined) {
      try {
        graph = loadProjectsFrom(config, this.root, this.read, this.readDirectory);
      } catch (error) {
        if (error instanceof LangError) throw new RefactorError(error.message);
        throw error;
      }
      this.graphs.set(key, graph);
    }
    return graph;
  }

  /** `file`'s graph: index.yaml's tsconfig; else the outermost ancestor tsconfig.json whose graph contains it, else the nearest. */
  private graph(file: string): Projects {
    if (this.named === undefined) this.named = namedConfig(this.root);
    if (this.named !== null) {
      if (!this.exists(this.named)) throw new WorkspaceError(message('refactor.ts-tsconfig-missing', { path: posix(relative(this.root, this.named)) }));
      return this.load(this.named);
    }
    const key = canonical(file);
    const configs = ancestorConfigs(file, this.root, this.exists);
    const owning = configs.find((config) => this.load(config).ordered.some((p) => p.files.has(key)));
    return this.load(owning ?? configs.at(-1));
  }

  /** The first project of `file`'s graph in depth-first preorder that includes it, else null. */
  owner(file: string): Project | null {
    const key = canonical(file);
    return this.graph(file).ordered.find((p) => p.files.has(key)) ?? null;
  }

  /** The project that governs `file`: its owner, else its graph's root project. */
  governing(file: string): Project {
    return this.owner(file) ?? this.graph(file).root;
  }

  private static references(graph: Projects, project: Project): Project[] {
    const configs = new Set((project.parsed?.projectReferences ?? []).map((ref) => canonical(ts().resolveProjectReferencePath(ref))));
    return graph.ordered.filter((p) => p.config !== null && configs.has(p.config));
  }

  /** The owner of `file` and every project that includes it or references the owner, in preorder. */
  relevant(file: string): Project[] {
    const owner = this.owner(file);
    if (owner === null) return [];
    const graph = this.graph(file);
    const reach = new Set<Project>([owner]);
    let size = 0;
    while (size !== reach.size) {
      size = reach.size;
      for (const p of graph.ordered) if (Workspace.references(graph, p).some((ref) => reach.has(ref))) reach.add(p);
    }
    const key = canonical(file);
    return graph.ordered.filter((p) => reach.has(p) || p.files.has(key));
  }

  /** The services of the projects relevant to `file` whose program includes `as` (`file` after a move), the owner's first. */
  holding(file: string, as: string = file): TS.LanguageService[] {
    const owner = this.owner(file);
    return this.relevant(file)
      .sort((a, b) => Number(b === owner) - Number(a === owner))
      .map((project) => this.service(project))
      .filter((service) => service.getProgram()?.getSourceFile(as) !== undefined);
  }

  private parsed(project: Project): TS.ParsedCommandLine {
    const parsed = project.parsed ?? ts().parseJsonConfigFileContent({ files: [] }, ts().sys, this.root);
    parsed.options.configFilePath ??= join(this.root, 'tsconfig.json');
    return parsed;
  }

  /** `project`'s options with `overrides`, its tsconfig given as a parsed JSON source, so a file rename edits its entries. */
  private options(project: Project, parsed: TS.ParsedCommandLine, overrides: TS.CompilerOptions = {}): TS.CompilerOptions {
    const text = project.config === null ? undefined : this.read(project.config);
    const configFile = project.config === null || text === undefined ? undefined : ts().parseJsonText(project.config, text);
    return { ...parsed.options, ...overrides, ...(configFile === undefined ? {} : { configFile }) };
  }

  /** The language service of `project` (its own tsconfig options), created on first use. */
  service(project: Project): TS.LanguageService {
    let service = this.services.get(project);
    if (service === undefined) {
      const parsed = this.parsed(project);
      const serviceHost = host(parsed, this.options(project, parsed), [], this.overlay, this.moved, this.readDirectory, this.listing);
      service = firstBuildTimed(ts().createLanguageService(serviceHost, this.registry));
      this.services.set(project, service);
    }
    return service;
  }

  /** Each file's language service: one per governing project, over its files plus `files`, with `overrides` on its options. */
  servicesOf(files: string[], overrides: TS.CompilerOptions): Map<string, TS.LanguageService> {
    const groups = new Map<Project, string[]>();
    for (const file of files) groups.set(this.governing(file), [...(groups.get(this.governing(file)) ?? []), file]);
    const out = new Map<string, TS.LanguageService>();
    for (const [project, group] of groups) {
      const parsed = this.parsed(project);
      const serviceHost = host(parsed, this.options(project, parsed, overrides), group, this.overlay, this.moved, this.readDirectory, this.listing);
      const service = firstBuildTimed(ts().createLanguageService(serviceHost, this.registry));
      for (const file of group) out.set(file, service);
    }
    return out;
  }

  /** Each file's program, from `servicesOf`. */
  programs(files: string[], overrides: TS.CompilerOptions): Map<string, TS.Program> {
    return new Map([...this.servicesOf(files, overrides)].map(([file, service]) => [file, service.getProgram() as TS.Program]));
  }
}
