// tsconfig selection and parsing (read, never executed), project references and their declaration outputs.
import { existsSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import type * as TS from 'typescript';
import { canonical, DECLARATION_RE, isUnder, posix } from './files.js';
import { LangError, type TsLayout } from './types.js';
import { ts } from './ts.js';

const CONFIG_NAME = 'tsconfig.json';
/** "No inputs were found": harmless, sources are enumerated from root_package, not the config's file list. */
const NO_INPUTS = 18003;

export interface Project {
  options: TS.CompilerOptions;
  files: Set<string>;
  cache: TS.ModuleResolutionCache;
  /** The parsed tsconfig, or null for the default project of a repo without one. */
  parsed: TS.ParsedCommandLine | null;
  /** The tsconfig's real path, or null. */
  config: string | null;
}

export interface Projects {
  root: Project;
  /** Depth-first preorder from the root config. */
  ordered: Project[];
  /** Declaration output -> the source that emits it. */
  outputs: Map<string, string>;
  outputDirs: Set<string>;
  host: TS.ModuleResolutionHost;
}

/** The section's tsconfig, else the nearest tsconfig.json from root_package up to the repo root. */
function selectConfig(layout: TsLayout): string | undefined {
  if (layout.tsconfig !== null) return join(layout.repoRoot, layout.tsconfig);
  for (let dir = join(layout.sourceRoot, layout.rootPackage); isUnder(dir, layout.repoRoot); dir = dirname(dir)) {
    if (existsSync(join(dir, CONFIG_NAME))) return join(dir, CONFIG_NAME);
    if (dir === layout.repoRoot) break;
  }
  return undefined;
}

function diagnosticText(diagnostic: TS.Diagnostic): string {
  return ts().flattenDiagnosticMessageText(diagnostic.messageText, '\n');
}

function parseConfig(path: string, repoRoot: string): TS.ParsedCommandLine {
  const shown = posix(relative(repoRoot, path));
  const { config, error } = ts().readConfigFile(path, ts().sys.readFile);
  if (error !== undefined) throw new LangError(`${shown}: ${diagnosticText(error)}`);
  const parsed = ts().parseJsonConfigFileContent(config, ts().sys, dirname(path), undefined, path);
  const fatal = parsed.errors.find((diagnostic) => diagnostic.code !== NO_INPUTS);
  if (fatal !== undefined) throw new LangError(`${shown}: ${diagnosticText(fatal)}`);
  return parsed;
}

function project(parsed: TS.ParsedCommandLine | null, config: string | null, repoRoot: string): Project {
  const options = parsed?.options ?? { moduleResolution: ts().ModuleResolutionKind.Bundler };
  const resolutionOptions = { ...options, allowJs: true };
  return {
    options: resolutionOptions,
    files: new Set((parsed?.fileNames ?? []).map(canonical)),
    cache: ts().createModuleResolutionCache(repoRoot, (name) => name, resolutionOptions),
    parsed,
    config,
  };
}

export function loadProjects(layout: TsLayout): Projects {
  return loadProjectsFrom(selectConfig(layout), layout.repoRoot);
}

/** The project of `config` (else a default one) and every project it references, depth-first preorder. */
export function loadProjectsFrom(config: string | undefined, repoRoot: string): Projects {
  const ordered: Project[] = [];
  const outputs = new Map<string, string>();
  const outputDirs = new Set<string>();
  const seen = new Set<string>();

  const mapOutputs = (parsed: TS.ParsedCommandLine): void => {
    for (const input of parsed.fileNames) {
      let names: readonly string[] = [];
      try {
        names = ts().getOutputFileNames(parsed, input, false);
      } catch {
        continue;
      }
      for (const output of names.filter((name) => DECLARATION_RE.test(name))) {
        outputs.set(resolve(output), canonical(input));
        for (let dir = dirname(resolve(output)); !outputDirs.has(dir) && dir !== dirname(dir); dir = dirname(dir)) {
          outputDirs.add(dir);
        }
      }
    }
  };

  const visit = (path: string, referenced: boolean): void => {
    const key = canonical(path);
    if (seen.has(key)) return;
    seen.add(key);
    const parsed = parseConfig(path, repoRoot);
    ordered.push(project(parsed, key, repoRoot));
    if (referenced) mapOutputs(parsed);
    for (const ref of parsed.projectReferences ?? []) visit(ts().resolveProjectReferencePath(ref), true);
  };

  if (config === undefined) {
    ordered.push(project(null, null, repoRoot));
  } else {
    visit(config, false);
  }
  const host: TS.ModuleResolutionHost = {
    fileExists: (name) => ts().sys.fileExists(name) || outputs.has(resolve(name)),
    readFile: (name) => ts().sys.readFile(name),
    directoryExists: (name) => ts().sys.directoryExists(name) || outputDirs.has(resolve(name)),
    realpath: (name) => ts().sys.realpath?.(name) ?? name,
    getCurrentDirectory: () => repoRoot,
    getDirectories: (name) => ts().sys.getDirectories(name),
  };
  return { root: ordered[0] as Project, ordered, outputs, outputDirs, host };
}

/** The first project in reference order listing `file`, else the root config. */
export function owner(projects: Projects, file: string): Project {
  const key = canonical(file);
  return projects.ordered.find((p) => p.files.has(key)) ?? projects.root;
}
