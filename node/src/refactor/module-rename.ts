// TypeScript module moves: a module's new name and the sibling taking it, and the specifier edits of moving files.
import { existsSync, readdirSync, statSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';
import type * as TS from 'typescript';
import { byCodePoint, language, readFile } from '../contract/index.js';
import { canonical, ts } from '../lang/index.js';
import { type Edit, splitBom } from './edits.js';
import { mockModulePaths } from './mocks.js';
import type { Refactor } from './session.js';
import { Workspace } from './workspace.js';

const FORMAT: TS.UserPreferences = { allowTextChangesInNewFiles: true };
/** A specifier's JavaScript or TypeScript extension. */
const SPECIFIER_EXTENSION = /\.(?:[cm]?[jt]s|[jt]sx)$/u;
const JS_SOURCE = /\.[cm]?jsx?$/u;

const sourceExtensions = (): string[] => language('typescript').source_extensions;
const declarationExtensions = (): string[] => language('typescript').declaration_globs.map((glob: string) => glob.replace('**/*', ''));

/** Every extension a TypeScript module file can have, longest first. */
const moduleExtensions = (): string[] => [...declarationExtensions(), ...sourceExtensions()].sort((a, b) => b.length - a.length);

/** `file`'s name split into its stem (the module's name) and its extension (a declaration file's whole one). */
export function moduleName(file: string): { stem: string; extension: string } {
  const name = basename(file);
  const extension = moduleExtensions().find((ext) => name.endsWith(ext) && name.length > ext.length) ?? '';
  return { stem: name.slice(0, name.length - extension.length), extension };
}

/** `name` can be a module's new stem: not empty, `.` or `..`, no path separator or NUL, no module extension. */
export function validModuleName(name: string): boolean {
  if (name === '' || name === '.' || name === '..' || /[/\\\0]/u.test(name)) return false;
  return !moduleExtensions().some((ext) => name.endsWith(ext));
}

/** Every file under `dir`, in path order. */
export function filesUnder(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true })
    .sort((a, b) => byCodePoint(a.name, b.name))
    .flatMap((entry) => (entry.isDirectory() ? filesUnder(join(dir, entry.name)) : [join(dir, entry.name)]));
}

/** `path` is `file` itself on disk, spelled in another case at most. */
function isSelf(file: string, path: string): boolean {
  if (path.toLowerCase() !== file.toLowerCase()) return false;
  const [a, b] = [statSync(file), statSync(path)];
  return a.dev === b.dev && a.ino === b.ino;
}

/** The file other than `file` that already takes `name` beside it: a module file of that stem, else a directory of that
 * name (its `index` source, else its first file by path, else itself); null when none does. */
export function takenBy(file: string, name: string): string | null {
  const dir = dirname(file);
  const siblings = moduleExtensions()
    .map((ext) => join(dir, `${name}${ext}`))
    .filter((path) => existsSync(path) && statSync(path).isFile() && !isSelf(file, path))
    .sort(byCodePoint);
  if (siblings[0] !== undefined) return siblings[0];
  const folder = join(dir, name);
  if (!existsSync(folder) || !statSync(folder).isDirectory()) return null;
  const inside = filesUnder(folder);
  const index = sourceExtensions().map((ext) => join(folder, `index${ext}`)).find((path) => inside.includes(path));
  return index ?? inside[0] ?? folder;
}

/** A mock module path or relative module augmentation naming a moved file, which the language service leaves. */
interface Probe {
  path: string;
  literal: TS.StringLiteral;
  augmentation: boolean;
}

/** A relative `declare module` name of `source`. */
function augmentations(source: TS.SourceFile): TS.StringLiteral[] {
  return source.statements.flatMap((s) => (ts().isModuleDeclaration(s) && ts().isStringLiteral(s.name) && /^\.\.?\//u.test(s.name.text) ? [s.name] : []));
}

/** Each mock module path and relative module augmentation in `source` resolving to one of `moved`. */
function sourceProbes(program: TS.Program, source: TS.SourceFile, moved: Set<string>, host: TS.ModuleResolutionHost): Probe[] {
  const found = [
    ...augmentations(source).map((literal) => ({ literal, augmentation: true })),
    ...(source.isDeclarationFile ? [] : mockModulePaths(program.getTypeChecker(), source).map((literal) => ({ literal, augmentation: false }))),
  ];
  return found
    .filter(({ literal }) => {
      const resolved = ts().resolveModuleName(literal.text, source.fileName, program.getCompilerOptions(), host).resolvedModule;
      return resolved !== undefined && moved.has(canonical(resolved.resolvedFileName));
    })
    .map(({ literal, augmentation }) => ({ path: source.fileName, literal, augmentation }));
}

/** Each mock module path and relative module augmentation in `services`' programs resolving to one of `moved`. */
function probes(services: TS.LanguageService[], moved: Set<string>, host: TS.ModuleResolutionHost): Probe[] {
  const out = new Map<string, Probe>();
  for (const program of new Set(services.map((s) => s.getProgram()))) {
    if (program === undefined) continue;
    for (const source of program.getSourceFiles()) {
      if (program.isSourceFileFromExternalLibrary(source)) continue;
      for (const probe of sourceProbes(program, source, moved, host)) out.set(`${source.fileName}\0${probe.literal.getStart(source)}`, probe);
    }
  }
  return [...out.values()];
}

/** Where the literal's text starts, after its quote. */
const innerStart = (literal: TS.StringLiteral): number => literal.getStart() + 1;

/** Each probed file's text: augmentation names masked (same length), each probe appended as an import; and where. */
function probedTexts(probes: Probe[]): { texts: Map<string, string>; at: Map<Probe, number> } {
  const texts = new Map<string, string>();
  const at = new Map<Probe, number>();
  for (const path of new Set(probes.map((p) => p.path))) {
    const own = probes.filter((p) => p.path === path);
    let text = (own[0] as Probe).literal.getSourceFile().text;
    for (const { literal } of own.filter((p) => p.augmentation)) {
      const start = innerStart(literal);
      const end = literal.end - 1;
      text = `${text.slice(0, start)}${'#'.repeat(end - start)}${text.slice(end)}`;
    }
    for (const [i, probe] of own.entries()) {
      const raw = probe.literal.getText();
      const statement = JS_SOURCE.test(path) ? `\n;import(${raw});` : `\ntype __laProbe${i} = typeof import(${raw});`;
      at.set(probe, text.length + statement.indexOf(raw) + 1);
      text += statement;
    }
    texts.set(canonical(path), text);
  }
  return { texts, at };
}

/** The language service's edits for renaming `from` (a file or directory) to `to`. */
function serviceEdits(services: Iterable<TS.LanguageService>, from: string, to: string): Edit[] {
  const format = ts().getDefaultFormatCodeSettings('\n');
  return [...services].flatMap((service) =>
    service
      .getEditsForFileRename(from, to, format, FORMAT)
      .flatMap((change) => change.textChanges.map((t) => ({ path: change.fileName, start: t.span.start, length: t.span.length, newText: t.newText }))),
  );
}

/** `next` in `old`'s extension style: `old`'s extension, or none. */
function keepStyle(old: string, next: string): string {
  const extension = SPECIFIER_EXTENSION.exec(old.split('/').pop() ?? '')?.[0] ?? '';
  const parts = next.split('/');
  const last = parts.pop() ?? '';
  return [...parts, `${last.replace(SPECIFIER_EXTENSION, '')}${extension}`].join('/');
}

/** The edits of moving `from` to `to` (`files`: each moved file) in the projects of `sources`: imports, mock paths,
 * augmentations and tsconfig entries, each specifier in its own extension style. */
export function moveEdits(r: Refactor, from: string, to: string, files: [string, string][], sources: string[]): Edit[] {
  const holding = (workspace: Workspace): Set<TS.LanguageService> => new Set(sources.flatMap((f) => workspace.holding(f)));
  const found = probes([...holding(r.workspace)], new Set(files.map(([f]) => canonical(f))), r.workspace.resolutionHost());
  const texts = new Map<string, string>();
  const text = (path: string): string => {
    const known = texts.get(path) ?? splitBom(readFile(path, 'utf8'))[1];
    texts.set(path, known);
    return known;
  };
  let edits: Edit[];
  if (found.length === 0) {
    edits = serviceEdits(holding(r.workspace), from, to);
  } else {
    const probed = probedTexts(found);
    const workspace = new Workspace(r.root, (name) => probed.texts.get(canonical(name)));
    const back = new Map(found.map((p) => [`${canonical(p.path)}\0${probed.at.get(p)}`, p]));
    edits = serviceEdits(holding(workspace), from, to).flatMap((e) => {
      const probe = back.get(`${canonical(e.path)}\0${e.start}`);
      if (probe !== undefined) return [{ ...e, path: probe.path, start: innerStart(probe.literal) }];
      return e.start + e.length <= text(e.path).length ? [e] : [];
    });
  }
  return edits.map((e) => {
    if (!sourceExtensions().some((ext) => e.path.endsWith(ext)) || e.length === 0) return e;
    return { ...e, newText: keepStyle(text(e.path).slice(e.start, e.start + e.length), e.newText) };
  });
}
