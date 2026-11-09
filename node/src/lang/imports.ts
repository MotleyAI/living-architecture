// Runtime import edges of every visible source, resolved under the repo's tsconfig and classified.
import { readFileSync } from 'node:fs';
import { dirname, relative, resolve, sep } from 'node:path';
import type * as TS from 'typescript';
import { byCodePoint } from '../contract/index.js';
import { canonical, DECLARATION_RE, isUnder, posix, stripSourceExtension, Tree } from './files.js';
import { loadProjects, owner, type Project, type Projects } from './projects.js';
import { runtimeSpecifiers } from './specifiers.js';
import type { ModuleImports, TsLayout } from './types.js';
import { ts } from './ts.js';

class Resolver {
  readonly realPackages: string[];

  constructor(
    readonly tree: Tree,
    readonly projects: Projects,
  ) {
    this.realPackages = tree.packageDirs.map(canonical);
  }

  /** A resolved file under any configured root as a module id; a declaration file not mapped to a source is none. */
  private resolved(fileName: string): string | undefined {
    const target = this.projects.outputs.get(resolve(fileName)) ?? fileName;
    if (DECLARATION_RE.test(target)) return undefined;
    const real = canonical(target);
    if (real.split(sep).includes('node_modules') || this.realPackages.includes(real)) return undefined;
    return this.realPackages.some((root) => isUnder(real, root)) ? this.tree.moduleId(real, this.tree.realSourceRoot) : undefined;
  }

  /** An unresolved relative specifier, attributed lexically unless it leaves every configured root. */
  private lexical(spec: string, importer: string): string | undefined {
    const path = resolve(dirname(importer), spec.replace(/[?#][\s\S]*$/, ''));
    const rel = posix(relative(this.tree.layout.sourceRoot, path));
    return this.tree.layout.rootPackages.some((root) => rel.startsWith(`${root}/`)) ? stripSourceExtension(rel) : undefined;
  }

  target(spec: string, importer: string, project: Project, mode: TS.ResolutionMode): string | undefined {
    const { resolvedModule } = ts().resolveModuleName(
      spec,
      importer,
      project.options,
      this.projects.host,
      project.cache,
      undefined,
      mode,
    );
    if (resolvedModule !== undefined) {
      return resolvedModule.isExternalLibraryImport ? undefined : this.resolved(resolvedModule.resolvedFileName);
    }
    return ts().isExternalModuleNameRelative(spec) ? this.lexical(spec, importer) : undefined;
  }

  targets(file: string): string[] {
    const project = owner(this.projects, file);
    const format = ts().getImpliedNodeFormatForFile(
      file,
      project.cache.getPackageJsonInfoCache(),
      this.projects.host,
      project.options,
    );
    const source = ts().createSourceFile(
      file,
      readFileSync(file, 'utf8'),
      { languageVersion: ts().ScriptTarget.Latest, impliedNodeFormat: format, jsDocParsingMode: ts().JSDocParsingMode.ParseNone },
      true,
    );
    const targets = new Set<string>();
    for (const literal of runtimeSpecifiers(source)) {
      const mode = ts().getModeForUsageLocation(source, literal, project.options);
      const target = this.target(literal.text, file, project, mode);
      if (target !== undefined) targets.add(target);
    }
    return [...targets].sort(byCodePoint);
  }
}

/** Each root's sources resolve under that root's projects. */
export function moduleImports(layout: TsLayout): ModuleImports[] {
  const tree = new Tree(layout);
  return loadProjects(layout).flatMap((projects, index) => {
    const resolver = new Resolver(tree, projects);
    return [...tree.files(tree.packageDirs[index]!)].map((file) => ({
      module: tree.moduleId(file),
      targets: resolver.targets(file),
    }));
  });
}
