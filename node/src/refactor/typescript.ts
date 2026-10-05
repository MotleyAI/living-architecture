// `dr-refactor` for TypeScript: rename, move-symbol and move-module through the bundled language service.
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmdirSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, relative, resolve, sep } from 'node:path';
import type * as TS from 'typescript';
import { byCodePoint, language, message } from '../contract/index.js';
import { canonical, posix, stripSourceExtension, ts } from '../lang/index.js';
import { unifiedDiff } from './diff.js';
import { applyEdits, type Edit, mergeEdits, RefactorError } from './edits.js';
import { Workspace } from './workspace.js';

export interface RefactorArgs {
  project: string;
  apply: boolean;
  subcommand: 'rename' | 'move-symbol' | 'move-module';
  file?: string;
  offset?: number;
  line?: number;
  col?: number;
  name?: string;
  new_name?: string;
  in_hierarchy?: boolean;
  unsure?: string;
  dest?: string;
  module?: string;
}

interface Entry {
  path: string;
  text: string;
}

const MOVE_TO_FILE = 'Move to file';
const PREFERENCES: TS.UserPreferences = { allowTextChangesInNewFiles: true };
const formatSettings = (): TS.FormatCodeSettings => ts().getDefaultFormatCodeSettings('\n');
// The line terminators TypeScript recognizes.
const LINE_BREAK = /\r\n|[\n\r\u2028\u2029]/u;

class Refactor {
  readonly root: string;
  private readonly cwd = process.cwd();
  private workspaceCache: Workspace | null = null;

  constructor(readonly args: RefactorArgs) {
    this.root = resolve(args.project);
  }

  get workspace(): Workspace {
    this.workspaceCache ??= new Workspace(this.root);
    return this.workspaceCache;
  }

  rel(path: string): string {
    return posix(relative(this.root, path));
  }

  /** `raw` resolved from the working directory; RefactorError when it is outside the project. */
  inProject(raw: string): string {
    const path = resolve(this.cwd, raw);
    if (path !== this.root && !path.startsWith(this.root + sep)) throw new RefactorError(message('refactor.outside-project', { path: raw }));
    return path;
  }

  owner(file: string): void {
    if (this.workspace.owner(file) === null) throw new RefactorError(message('refactor.ts-outside-project', { path: this.rel(file) }));
  }

  /** The language services of the projects relevant to `file` whose program includes it, the owner's first. */
  services(file: string): TS.LanguageService[] {
    const owner = this.workspace.owner(file);
    return this.workspace
      .relevant(file)
      .sort((a, b) => Number(b === owner) - Number(a === owner))
      .map((project) => this.workspace.service(project))
      .filter((service) => service.getProgram()?.getSourceFile(file) !== undefined);
  }

  /** Header, one diff or rename pair per entry in path order, then the footer; writes only with --apply. */
  emit(header: string, edits: Map<string, Edit[]>, moves: [string, string][]): number {
    const entries: Entry[] = [];
    const written: [string, string][] = [];
    for (const [path, fileEdits] of edits) {
      const old = readFileSync(path, 'utf8');
      const text = applyEdits(old, fileEdits);
      if (text === old) continue;
      written.push([path, text]);
      entries.push({ path: this.rel(path), text: unifiedDiff(old, text, this.rel(path)) });
    }
    for (const [from, to] of moves) entries.push({ path: this.rel(from), text: message('refactor.ts-moved', { old: this.rel(from), new: this.rel(to) }) });
    entries.sort((a, b) => byCodePoint(a.path, b.path));
    const paths = [...new Set(entries.map((e) => e.path))];
    let out = `${header}\n\n\n${entries.map((e) => `${e.text}\n`).join('')}\n`;
    if (this.args.apply) {
      for (const [path, text] of written.sort((a, b) => byCodePoint(a[0], b[0]))) writeFileSync(path, text);
      for (const [from, to] of moves) {
        mkdirSync(dirname(to), { recursive: true });
        renameSync(from, to);
      }
      out += `${message('refactor.applied', { count: paths.length })}\n`;
      out += paths.map((path) => `${message('refactor.applied-file', { path })}\n`).join('');
    } else {
      out += `${message('refactor.dry-run', { count: paths.length })}\n`;
    }
    process.stdout.write(out);
    return 0;
  }
}

const codePoints = (text: string): string[] => [...text];

/** The UTF-16 offset of the code point offset `points` into `text`. */
const utf16 = (text: string, points: number): number => codePoints(text).slice(0, points).join('').length;

function sourceFile(path: string, text: string): TS.SourceFile {
  return ts().createSourceFile(path, text, ts().ScriptTarget.Latest, true);
}

function* nodes(node: TS.Node): Generator<TS.Node> {
  yield node;
  for (const child of node.getChildren()) yield* nodes(child);
}

const DECLARATIONS = new Set<number>();

function isNamedDeclaration(node: TS.Node, name: string): node is TS.NamedDeclaration & { name: TS.Identifier } {
  if (DECLARATIONS.size === 0) {
    const k = ts().SyntaxKind;
    for (const kind of [
      k.FunctionDeclaration,
      k.ClassDeclaration,
      k.InterfaceDeclaration,
      k.TypeAliasDeclaration,
      k.EnumDeclaration,
      k.VariableDeclaration,
      k.MethodDeclaration,
      k.PropertyDeclaration,
      k.MethodSignature,
      k.PropertySignature,
    ]) {
      DECLARATIONS.add(kind);
    }
  }
  const declared = (node as TS.NamedDeclaration).name;
  return DECLARATIONS.has(node.kind) && declared !== undefined && ts().isIdentifier(declared) && declared.text === name;
}

/** The UTF-16 position the locator names: --offset, --line/--col (code points), else --name's first declaration or use. */
function locate(args: RefactorArgs, path: string, text: string): number {
  if (args.offset !== undefined) {
    const count = codePoints(text).length;
    if (args.offset < 0 || args.offset > count) throw new RefactorError(message('refactor.offset-out-of-range', { offset: args.offset, count }));
    return utf16(text, args.offset);
  }
  if (args.line !== undefined) {
    const lines = text.split(LINE_BREAK);
    if (lines.length > 1 && lines[lines.length - 1] === '') lines.pop();
    const count = text === '' ? 0 : lines.length;
    if (args.line < 1 || args.line > count) throw new RefactorError(message('refactor.line-out-of-range', { line: args.line, count }));
    const col = args.col ?? 1;
    const lineText = lines[args.line - 1] ?? '';
    const width = codePoints(lineText).length;
    if (col < 1 || col > width + 1) throw new RefactorError(message('refactor.col-out-of-range', { col, line: args.line, count: width }));
    const start = lines.slice(0, args.line - 1).reduce((sum, l) => sum + l.length, 0);
    const breaks = [...text.matchAll(new RegExp(LINE_BREAK, 'gu'))].slice(0, args.line - 1).reduce((sum, m) => sum + m[0].length, 0);
    return start + breaks + utf16(lineText, col - 1);
  }
  if (args.name !== undefined) {
    const file = sourceFile(path, text);
    const all = [...nodes(file)];
    const name = args.name;
    const starts = (found: TS.Node[]): number[] => found.map((n) => n.getStart(file)).sort((a, b) => a - b);
    const [declared] = starts(all.filter((n) => isNamedDeclaration(n, name)).map((n) => (n as TS.NamedDeclaration).name as TS.Node));
    const [used] = starts(all.filter((n) => ts().isIdentifier(n) && n.text === name));
    const position = declared ?? used;
    if (position === undefined) throw new RefactorError(message('refactor.symbol-not-found', { name }));
    return position;
  }
  throw new RefactorError(message('refactor.no-locator'));
}

function rename(r: Refactor): number {
  if (r.args.in_hierarchy === false) throw new RefactorError(message('refactor.ts-not-supported', { option: '--no-in-hierarchy' }));
  if (r.args.unsure === 'include') throw new RefactorError(message('refactor.ts-not-supported', { option: '--unsure include' }));
  const file = r.inProject(r.args.file ?? '');
  const text = readFileSync(file, 'utf8');
  const position = locate(r.args, file, text);
  r.owner(file);
  const services = r.services(file);
  const info = services[0]?.getRenameInfo(file, position, { allowRenameOfImportPath: false });
  const named = info?.canRename === true && info.triggerSpan.start <= position && position <= info.triggerSpan.start + info.triggerSpan.length;
  if (info === undefined || !info.canRename || !named) throw new RefactorError(message('refactor.cannot-rename'));
  const newName = r.args.new_name ?? '';
  const edits: Edit[] = [];
  for (const service of services) {
    for (const location of service.findRenameLocations(file, position, false, false, { providePrefixAndSuffixTextForRename: true }) ?? []) {
      const newText = `${location.prefixText ?? ''}${newName}${location.suffixText ?? ''}`;
      edits.push({ path: location.fileName, start: location.textSpan.start, length: location.textSpan.length, newText });
    }
  }
  const old = text.slice(info.triggerSpan.start, info.triggerSpan.start + info.triggerSpan.length);
  return r.emit(message('refactor.ts-rename-header', { old, new: newName }), mergeEdits(edits), []);
}

/** The top-level statement of `file` that declares the symbol at `position`, else null. */
function topLevelStatement(service: TS.LanguageService, file: string, position: number): TS.Statement | null {
  const program = service.getProgram();
  const source = program?.getSourceFile(file);
  if (program === undefined || source === undefined) return null;
  const identifier = [...nodes(source)].find((n) => ts().isIdentifier(n) && n.getStart(source) <= position && position < n.end);
  const symbol = identifier === undefined ? undefined : program.getTypeChecker().getSymbolAtLocation(identifier);
  for (const declaration of symbol?.declarations ?? []) {
    const statement = ts().isVariableDeclaration(declaration) ? declaration.parent.parent : declaration;
    if (source.statements.includes(statement as TS.Statement)) return statement as TS.Statement;
  }
  return null;
}

const nameOf = (statement: TS.Statement): TS.DeclarationName | undefined =>
  ts().getNameOfDeclaration(statement as TS.Node as TS.Declaration);

/** The names the statement exports (`default` for a default export). */
function exportedNames(statement: TS.Statement): string[] {
  const modifiers = ts().canHaveModifiers(statement) ? (ts().getModifiers(statement) ?? []) : [];
  if (!modifiers.some((m) => m.kind === ts().SyntaxKind.ExportKeyword)) return [];
  if (modifiers.some((m) => m.kind === ts().SyntaxKind.DefaultKeyword)) return ['default'];
  if (ts().isVariableStatement(statement)) {
    return statement.declarationList.declarations.flatMap((d) => (ts().isIdentifier(d.name) ? [d.name.text] : []));
  }
  const name = nameOf(statement);
  return name !== undefined && ts().isIdentifier(name) ? [name.text] : [];
}

function declaredName(statement: TS.Statement): string {
  if (ts().isVariableStatement(statement)) return statement.declarationList.declarations.map((d) => d.name.getText()).join(', ');
  return nameOf(statement)?.getText() ?? 'default';
}

/** `specifier` re-pointed from `from` to `to`, as imported from `importer`, keeping its extension style. */
function respecify(specifier: string, from: string, to: string, importer: string): string {
  const fromStem = basename(stripSourceExtension(from));
  const last = specifier.split('/').pop() ?? '';
  const suffix = last.startsWith(fromStem) ? last.slice(fromStem.length) : '';
  let rel = posix(relative(dirname(importer), stripSourceExtension(to)));
  if (!rel.startsWith('.')) rel = `./${rel}`;
  return `${rel}${/^\.\w+$/.test(suffix) ? suffix : ''}`;
}

/** Edits that point every re-export of the moved names from `from` at `to` (an `export *` barrel gets an explicit one). */
function reexportEdits(program: TS.Program, from: string, to: string, names: string[]): Edit[] {
  const checker = program.getTypeChecker();
  const resolvesTo = (specifier: TS.Expression | undefined, target: string): boolean => {
    const declaration = specifier === undefined ? undefined : checker.getSymbolAtLocation(specifier)?.valueDeclaration;
    return declaration !== undefined && ts().isSourceFile(declaration) && canonical(declaration.fileName) === canonical(target);
  };
  const edits: Edit[] = [];
  for (const source of program.getSourceFiles()) {
    if (source.isDeclarationFile || program.isSourceFileFromExternalLibrary(source)) continue;
    const exports = source.statements.filter(ts().isExportDeclaration);
    for (const statement of exports.filter((s) => resolvesTo(s.moduleSpecifier, from))) {
      const specifier = statement.moduleSpecifier as TS.StringLiteral;
      const quote = specifier.getText(source)[0] ?? "'";
      const target = respecify(specifier.text, from, to, source.fileName);
      const typeOnly = statement.isTypeOnly ? 'type ' : '';
      const line = (elements: string[]): string => `\nexport ${typeOnly}{ ${elements.join(', ')} } from ${quote}${target}${quote};`;
      const clause = statement.exportClause;
      if (clause === undefined) {
        const named = names.filter((n) => n !== 'default');
        const covered = exports.some((s) => s.exportClause === undefined && resolvesTo(s.moduleSpecifier, to));
        if (named.length > 0 && !covered) edits.push({ path: source.fileName, start: statement.end, length: 0, newText: line(named) });
        continue;
      }
      if (!ts().isNamedExports(clause)) continue;
      const moved = clause.elements.filter((e) => names.includes((e.propertyName ?? e.name).text));
      if (moved.length === 0) continue;
      if (moved.length === clause.elements.length) {
        edits.push({ path: source.fileName, start: specifier.getStart(source) + 1, length: specifier.text.length, newText: target });
        continue;
      }
      const kept = clause.elements.filter((e) => !moved.includes(e)).map((e) => e.getText(source));
      edits.push({ path: source.fileName, start: clause.getStart(source), length: clause.getWidth(source), newText: `{ ${kept.join(', ')} }` });
      edits.push({ path: source.fileName, start: statement.end, length: 0, newText: line(moved.map((e) => e.getText(source))) });
    }
  }
  return edits;
}

function moveSymbol(r: Refactor): number {
  const file = r.inProject(r.args.file ?? '');
  const dest = r.inProject(r.args.dest ?? '');
  if (!existsSync(dest) || !statSync(dest).isFile()) throw new RefactorError(message('refactor.destination-missing', { path: r.args.dest }));
  const text = readFileSync(file, 'utf8');
  const position = locate(r.args, file, text);
  r.owner(file);
  const notMovable = (): RefactorError => new RefactorError(message('refactor.not-movable', { path: r.rel(file) }));
  const services = r.services(file);
  const statement = services[0] === undefined ? null : topLevelStatement(services[0], file, position);
  if (statement === null) throw notMovable();
  const source = statement.getSourceFile();
  const range = { pos: statement.getStart(source), end: statement.end };
  const edits: Edit[] = [];
  for (const [i, service] of services.entries()) {
    const applicable = service.getApplicableRefactors(file, range, PREFERENCES, undefined, undefined, true);
    const result = applicable.some((a) => a.name === MOVE_TO_FILE && a.actions.some((x) => x.name === MOVE_TO_FILE))
      ? service.getEditsForRefactor(file, formatSettings(), range, MOVE_TO_FILE, MOVE_TO_FILE, PREFERENCES, { targetFile: dest })
      : undefined;
    if (result === undefined && i === 0) throw notMovable();
    for (const change of result?.edits ?? []) {
      for (const t of change.textChanges) edits.push({ path: change.fileName, start: t.span.start, length: t.span.length, newText: t.newText });
    }
    const program = service.getProgram();
    if (program !== undefined) edits.push(...reexportEdits(program, file, dest, exportedNames(statement)));
  }
  return r.emit(message('refactor.ts-move-symbol-header', { name: declaredName(statement) }), mergeEdits(edits), []);
}

/** Every file under `dir`, in path order. */
function filesUnder(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true })
    .sort((a, b) => byCodePoint(a.name, b.name))
    .flatMap((entry) => (entry.isDirectory() ? filesUnder(join(dir, entry.name)) : [join(dir, entry.name)]));
}

function moveModule(r: Refactor): number {
  const module = r.inProject(r.args.module ?? '');
  const destDir = r.inProject(r.args.dest ?? '');
  if (!existsSync(destDir) || !statSync(destDir).isDirectory()) throw new RefactorError(message('refactor.destination-missing', { path: r.args.dest }));
  const target = join(destDir, basename(module));
  const isDir = existsSync(module) && statSync(module).isDirectory();
  const files = isDir ? filesUnder(module) : [module];
  const extensions: string[] = language('typescript').source_extensions;
  const sources = files.filter((f) => extensions.some((ext) => f.endsWith(ext)) && r.workspace.owner(f) !== null);
  if (sources.length === 0) r.owner(module);
  const moves = files.map((f): [string, string] => [f, join(target, relative(module, f))]);
  for (const [, to] of moves) if (existsSync(to)) throw new RefactorError(message('refactor.destination-exists', { path: r.rel(to) }));
  const edits: Edit[] = [];
  const services = new Set(sources.flatMap((f) => r.services(f)));
  for (const service of services) {
    for (const change of service.getEditsForFileRename(module, target, formatSettings(), PREFERENCES)) {
      for (const t of change.textChanges) edits.push({ path: change.fileName, start: t.span.start, length: t.span.length, newText: t.newText });
    }
  }
  const header = message('refactor.ts-move-module-header', { name: isDir ? basename(module) : basename(stripSourceExtension(module)) });
  const code = r.emit(header, mergeEdits(edits), moves);
  if (r.args.apply && isDir) removeEmptyDirs(module);
  return code;
}

function removeEmptyDirs(dir: string): void {
  if (!existsSync(dir)) return;
  for (const entry of readdirSync(dir, { withFileTypes: true })) if (entry.isDirectory()) removeEmptyDirs(join(dir, entry.name));
  if (readdirSync(dir).length === 0) rmdirSync(dir);
}

/** `dr-refactor` on a TypeScript source: 0, or 1 with the finding on stderr. */
export function runTypescriptRefactor(args: RefactorArgs): number {
  try {
    const r = new Refactor(args);
    if (args.subcommand === 'rename') return rename(r);
    if (args.subcommand === 'move-symbol') return moveSymbol(r);
    return moveModule(r);
  } catch (error) {
    if (!(error instanceof RefactorError)) throw error;
    process.stderr.write(`${error.message}\n`);
    return 1;
  }
}
