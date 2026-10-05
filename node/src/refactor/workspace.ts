// The TypeScript projects a refactor or check runs in: the reference graph, one language service per project.
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import type * as TS from 'typescript';
import { loadYaml, toPlain } from '../contract/index.js';
import { canonical, LangError, loadProjectsFrom, type Project, type Projects, ts } from '../lang/index.js';
import { RefactorError } from './edits.js';

/** `typescript.tsconfig` of the root's architecture/index.yaml, else `<root>/tsconfig.json`, if it exists. */
function rootConfig(root: string): string | undefined {
  let named: unknown;
  try {
    named = (toPlain(loadYaml(readFileSync(join(root, 'architecture', 'index.yaml'), 'utf8'))) as any)?.typescript?.tsconfig;
  } catch {
    named = undefined;
  }
  const config = typeof named === 'string' ? join(root, named) : join(root, 'tsconfig.json');
  return existsSync(config) ? config : undefined;
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
  private readonly projects: Projects;

  /** The projects of `root` (a refactor's --project, or the repo root); RefactorError on an unreadable tsconfig. */
  constructor(readonly root: string) {
    try {
      this.projects = loadProjectsFrom(rootConfig(root), root);
    } catch (error) {
      if (error instanceof LangError) throw new RefactorError(error.message);
      throw error;
    }
  }

  /** The first project in depth-first preorder that includes `file`, else null. */
  owner(file: string): Project | null {
    const key = canonical(file);
    return this.projects.ordered.find((p) => p.files.has(key)) ?? null;
  }

  /** The project that governs `file`: its owner, else the root project. */
  governing(file: string): Project {
    return this.owner(file) ?? this.projects.root;
  }

  private references(project: Project): Project[] {
    const configs = new Set((project.parsed?.projectReferences ?? []).map((ref) => canonical(ts().resolveProjectReferencePath(ref))));
    return this.projects.ordered.filter((p) => p.config !== null && configs.has(p.config));
  }

  /** The owner of `file` and every project that includes it or references the owner, in preorder. */
  relevant(file: string): Project[] {
    const owner = this.owner(file);
    if (owner === null) return [];
    const reach = new Set<Project>([owner]);
    let size = 0;
    while (size !== reach.size) {
      size = reach.size;
      for (const p of this.projects.ordered) if (this.references(p).some((ref) => reach.has(ref))) reach.add(p);
    }
    const key = canonical(file);
    return this.projects.ordered.filter((p) => reach.has(p) || p.files.has(key));
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
