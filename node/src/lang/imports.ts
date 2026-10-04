// Runtime import edges of every visible source, resolved under the repo's tsconfig and classified.
import { readFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import type * as TS from 'typescript';
import { canonical, DECLARATION_RE, isUnder, posix, stripSourceExtension, Tree } from './files.js';
import { loadProjects, owner, type Project, type Projects } from './projects.js';
import { runtimeSpecifiers } from './specifiers.js';
import type { ModuleImports, TsLayout } from './types.js';
import { ts } from './ts.js';

class Resolver {
  readonly projects: Projects;
  readonly realPackage: string;

  constructor(readonly tree: Tree) {
    this.projects = loadProjects(tree.layout);
    this.realPackage = canonical(tree.packageDir);
  }

  /** A resolved file under root_package as a module id; a declaration file not mapped to a source is none. */
  private resolved(fileName: string): string | undefined {
    const target = this.projects.outputs.get(resolve(fileName)) ?? fileName;
    if (DECLARATION_RE.test(target)) return undefined;
    const real = canonical(target);
    if (real.split(sep).includes('node_modules') || real === this.realPackage) return undefined;
    return isUnder(real, this.realPackage) ? this.tree.moduleId(real, this.tree.realSourceRoot) : undefined;
  }

  /** An unresolved relative specifier, attributed lexically unless it leaves root_package. */
  private lexical(spec: string, importer: string): string | undefined {
    const path = resolve(dirname(importer), spec.replace(/[?#][\s\S]*$/, ''));
    const rel = posix(relative(this.tree.layout.sourceRoot, path));
    return rel.startsWith(`${this.tree.layout.rootPackage}/`) ? stripSourceExtension(rel) : undefined;
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
    return [...targets].sort();
  }
}

export function moduleImports(layout: TsLayout): ModuleImports[] {
  const tree = new Tree(layout);
  const resolver = new Resolver(tree);
  return [...tree.files(join(layout.sourceRoot, layout.rootPackage))].map((file) => ({
    module: tree.moduleId(file),
    targets: resolver.targets(file),
  }));
}
