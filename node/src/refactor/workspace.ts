// The TypeScript projects a refactor or check runs in: the reference graph, one language service per project.
import { existsSync, readFileSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, sep } from 'node:path';
import type * as TS from 'typescript';
import { loadYaml, message, toPlain } from '../contract/index.js';
import { canonical, LangError, loadProjectsFrom, posix, type Project, type Projects, ts } from '../lang/index.js';
import { RefactorError } from './edits.js';

/** `typescript.tsconfig` of the root's architecture/index.yaml, else null. */
function namedConfig(root: string): string | null {
  let named: unknown;
  try {
    const index = toPlain(loadYaml(readFileSync(join(root, 'architecture', 'index.yaml'), 'utf8'))) as { typescript?: { tsconfig?: unknown } } | null;
    named = index?.typescript?.tsconfig;
  } catch {
    named = undefined;
  }
  return typeof named === 'string' ? join(root, named) : null;
}

/** The tsconfig.json files from `file`'s directory up to `root`, outermost first. */
function ancestorConfigs(file: string, root: string): string[] {
  const out: string[] = [];
  for (let dir = dirname(file); ; dir = dirname(dir)) {
    const rel = relative(root, dir);
    if (rel.split(sep)[0] === '..' || isAbsolute(rel)) break;
    if (existsSync(join(dir, 'tsconfig.json'))) out.unshift(join(dir, 'tsconfig.json'));
    if (rel === '') break;
  }
  return out;
}

/** The hook (internal in TypeScript's typings) that resolves a referenced project to its sources, not its outputs. */
interface Host extends TS.LanguageServiceHost {
  useSourceOfProjectReferenceRedirect(): boolean;
}

function host(parsed: TS.ParsedCommandLine, options: TS.CompilerOptions, extra: string[]): Host {
  const sys = ts().sys;
  const names = [...parsed.fileNames, ...extra];
  return {
    getScriptFileNames: () => names,
    getScriptVersion: () => '0',
    getScriptSnapshot: (name) => (sys.fileExists(name) ? ts().ScriptSnapshot.fromString(sys.readFile(name) ?? '') : undefined),
    getCurrentDirectory: () => dirname(parsed.options.configFilePath as string),
    getCompilationSettings: () => options,
    getDefaultLibFileName: (opts) => ts().getDefaultLibFilePath(opts),
    getProjectReferences: () => parsed.projectReferences,
    useSourceOfProjectReferenceRedirect: () => true,
    fileExists: sys.fileExists,
    readFile: sys.readFile,
    readDirectory: sys.readDirectory,
    directoryExists: sys.directoryExists,
    getDirectories: sys.getDirectories,
    realpath: sys.realpath,
  };
}

export class Workspace {
  private readonly services = new Map<Project, TS.LanguageService>();
  private readonly registry = ts().createDocumentRegistry();
  private readonly graphs = new Map<string, Projects>();
  private readonly named: string | null;

  /** The projects under `root` (a refactor's --project, or the repo root), loaded per file on first use. */
  constructor(readonly root: string) {
    this.named = namedConfig(root);
  }

  /** The reference graph from `config` (none: inferred defaults); RefactorError on an unreadable tsconfig. */
  private load(config: string | undefined): Projects {
    const key = config ?? '';
    let graph = this.graphs.get(key);
    if (graph === undefined) {
      try {
        graph = loadProjectsFrom(config, this.root);
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
    if (this.named !== null) {
      if (!existsSync(this.named)) throw new RefactorError(message('refactor.ts-tsconfig-missing', { path: posix(relative(this.root, this.named)) }));
      return this.load(this.named);
    }
    const key = canonical(file);
    const configs = ancestorConfigs(file, this.root);
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

  private parsed(project: Project): TS.ParsedCommandLine {
    const parsed = project.parsed ?? ts().parseJsonConfigFileContent({ files: [] }, ts().sys, this.root);
    parsed.options.configFilePath ??= join(this.root, 'tsconfig.json');
    return parsed;
  }

  /** The language service of `project` (its own tsconfig options), created on first use. */
  service(project: Project): TS.LanguageService {
    let service = this.services.get(project);
    if (service === undefined) {
      const parsed = this.parsed(project);
      service = ts().createLanguageService(host(parsed, parsed.options, []), this.registry);
      this.services.set(project, service);
    }
    return service;
  }

  /** Each file's program: one per governing project, over its files plus `files`, with `overrides` on its options. */
  programs(files: string[], overrides: TS.CompilerOptions): Map<string, TS.Program> {
    const groups = new Map<Project, string[]>();
    for (const file of files) groups.set(this.governing(file), [...(groups.get(this.governing(file)) ?? []), file]);
    const out = new Map<string, TS.Program>();
    for (const [project, group] of groups) {
      const parsed = this.parsed(project);
      const service = ts().createLanguageService(host(parsed, { ...parsed.options, ...overrides }, group), this.registry);
      for (const file of group) out.set(file, service.getProgram() as TS.Program);
    }
    return out;
  }
}
