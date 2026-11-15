// `dr-refactor` for TypeScript: rename, rename-map, retarget, move-symbol and move-module through the bundled
// language service.
import { existsSync, readdirSync, rmdirSync, statSync } from 'node:fs';
import { basename, dirname, join, relative } from 'node:path';
import type * as TS from 'typescript';
import { byCodePoint, language, message } from '../contract/index.js';
import { canonical, posix, stripSourceExtension, ts } from '../lang/index.js';
import { type Edit, mergeEdits, RefactorError } from './edits.js';
import { loadMap, MapError } from './map.js';
import { type MovedSpan, movedOffsets } from './position.js';
import { type EntrySpec, runEntries } from './rename.js';
import { type Locator, locate, nodes, Refactor, type RefactorArgs, UsageError } from './session.js';
import { SiteError } from './sites.js';
import { LocatorError } from './symbols.js';

export type { RefactorArgs } from './session.js';

const MOVE_TO_FILE = 'Move to file';
const PREFERENCES: TS.UserPreferences = { allowTextChangesInNewFiles: true };
const formatSettings = (): TS.FormatCodeSettings => ts().getDefaultFormatCodeSettings('\n');

const locatorOf = (args: RefactorArgs): Locator => ({ offset: args.offset, line: args.line, col: args.col, symbol: args.symbol });

/** `rename` and `retarget` as their one-entry map. */
function single(r: Refactor): number {
  const { args } = r;
  const intent = args.subcommand === 'retarget' ? { retarget: args.target ?? '' } : { newName: args.new_name ?? '' };
  return runEntries(r, [{ index: 1, file: r.inProject(args.file ?? ''), shown: args.file ?? '', locator: locatorOf(args), ...intent }], '');
}

/** `rename-map MAP`: MAP from the working directory, its entries' files from --project. */
function renameMap(r: Refactor): number {
  const shown = r.args.map ?? '';
  const specs = loadMap(shown, shown).map((entry, i): EntrySpec => ({
    index: i + 1,
    file: r.inProject(entry.file, r.root),
    shown: entry.file,
    locator: { offset: entry.offset, line: entry.line, col: entry.col, symbol: entry.symbol },
    newName: entry.new_name,
    retarget: entry.retarget,
  }));
  return runEntries(r, specs, shown);
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

interface Reexport {
  from: string;
  to: string;
  names: string[];
  resolvesTo: (specifier: TS.Expression | undefined, target: string) => boolean;
}

/** The edits for one `export … from` of `source` that resolves to the moved symbol's file. */
function reexportStatementEdits(move: Reexport, source: TS.SourceFile, exports: TS.ExportDeclaration[], statement: TS.ExportDeclaration): Edit[] {
  const specifier = statement.moduleSpecifier as TS.StringLiteral;
  const quote = specifier.getText(source)[0] ?? "'";
  const target = respecify(specifier.text, move.from, move.to, source.fileName);
  const typeOnly = statement.isTypeOnly ? 'type ' : '';
  const line = (elements: string[]): string => `\nexport ${typeOnly}{ ${elements.join(', ')} } from ${quote}${target}${quote};`;
  const at = (start: number, length: number, newText: string): Edit => ({ path: source.fileName, start, length, newText });
  const clause = statement.exportClause;
  if (clause === undefined) {
    const named = move.names.filter((n) => n !== 'default');
    const covered = exports.some((s) => s.exportClause === undefined && move.resolvesTo(s.moduleSpecifier, move.to));
    return named.length > 0 && !covered ? [at(statement.end, 0, line(named))] : [];
  }
  if (!ts().isNamedExports(clause)) return [];
  const moved = clause.elements.filter((e) => move.names.includes((e.propertyName ?? e.name).text));
  if (moved.length === 0) return [];
  if (moved.length === clause.elements.length) return [at(specifier.getStart(source) + 1, specifier.text.length, target)];
  const kept = clause.elements.filter((e) => !moved.includes(e)).map((e) => e.getText(source));
  return [
    at(clause.getStart(source), clause.getWidth(source), `{ ${kept.join(', ')} }`),
    at(statement.end, 0, line(moved.map((e) => e.getText(source)))),
  ];
}

/** Edits that point every re-export of the moved names from `from` at `to` (an `export *` barrel gets an explicit one). */
function reexportEdits(program: TS.Program, from: string, to: string, names: string[]): Edit[] {
  const checker = program.getTypeChecker();
  const resolvesTo = (specifier: TS.Expression | undefined, target: string): boolean => {
    const declaration = specifier === undefined ? undefined : checker.getSymbolAtLocation(specifier)?.valueDeclaration;
    return declaration !== undefined && ts().isSourceFile(declaration) && canonical(declaration.fileName) === canonical(target);
  };
  const move: Reexport = { from, to, names, resolvesTo };
  return program
    .getSourceFiles()
    .filter((source) => !source.isDeclarationFile && !program.isSourceFileFromExternalLibrary(source))
    .flatMap((source) => {
      const exports = source.statements.filter(ts().isExportDeclaration);
      return exports.filter((s) => resolvesTo(s.moduleSpecifier, from)).flatMap((s) => reexportStatementEdits(move, source, exports, s));
    });
}

/** One project's "Move to file" edits for `range` of `file`, or null when it does not offer the refactor. */
function moveToFileEdits(service: TS.LanguageService, file: string, range: TS.TextRange, dest: string): Edit[] | null {
  const applicable = service.getApplicableRefactors(file, range, PREFERENCES, undefined, undefined, true);
  if (!applicable.some((a) => a.name === MOVE_TO_FILE && a.actions.some((x) => x.name === MOVE_TO_FILE))) return null;
  const result = service.getEditsForRefactor(file, formatSettings(), range, MOVE_TO_FILE, MOVE_TO_FILE, PREFERENCES, { targetFile: dest });
  if (result === undefined) return null;
  return result.edits.flatMap((change) =>
    change.textChanges.map((t) => ({ path: change.fileName, start: t.span.start, length: t.span.length, newText: t.newText })),
  );
}

function moveSymbol(r: Refactor): number {
  const file = r.inProject(r.args.file ?? '');
  const dest = r.inProject(r.args.dest ?? '');
  if (!existsSync(dest) || !statSync(dest).isFile()) throw new RefactorError(message('refactor.destination-missing', { path: r.args.dest }));
  const located = locate(r, file, r.args.file ?? '', locatorOf(r.args));
  const { position } = located;
  r.owner(file);
  const notMovable = (): RefactorError => new RefactorError(message('refactor.not-movable', { path: r.rel(file) }));
  if (r.args.symbol !== undefined && (!located.topLevel || located.file !== file)) throw notMovable();
  const services = r.services(file);
  const statement = services[0] === undefined ? null : topLevelStatement(services[0], file, position);
  if (statement === null) throw notMovable();
  const header = message('refactor.ts-move-symbol-header', { name: declaredName(statement) });
  if (dest === file) return r.emit([header], new Map(), []);
  const source = statement.getSourceFile();
  const range = { pos: statement.getStart(source), end: statement.end };
  const edits: Edit[] = [];
  for (const [i, service] of services.entries()) {
    const moved = moveToFileEdits(service, file, range, dest);
    if (moved === null && i === 0) throw notMovable();
    edits.push(...(moved ?? []));
    const program = service.getProgram();
    if (program !== undefined) edits.push(...reexportEdits(program, file, dest, exportedNames(statement)));
  }
  const merged = mergeEdits(edits);
  return r.emit([header], merged, [], movedSpans(file, range, source.text, dest, merged.get(dest) ?? []));
}

/** The moved statement's span, placed in the destination edit that inserts its text. */
function movedSpans(file: string, range: TS.TextRange, text: string, dest: string, inserted: Edit[]): MovedSpan[] {
  const moved = text.slice(range.pos, range.end);
  return inserted
    .map((edit) => ({ from: file, start: range.pos, end: range.end, to: dest, at: edit.start, offset: movedOffsets(moved, edit.newText) }))
    .filter((span) => span.offset(0) !== null)
    .slice(0, 1);
}

/** Every file under `dir`, in path order. */
function filesUnder(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true })
    .sort((a, b) => byCodePoint(a.name, b.name))
    .flatMap((entry) => (entry.isDirectory() ? filesUnder(join(dir, entry.name)) : [join(dir, entry.name)]));
}

/** Every project's edits for renaming `module` (a file or directory) to `target`. */
function fileRenameEdits(services: Iterable<TS.LanguageService>, module: string, target: string): Edit[] {
  return [...services].flatMap((service) =>
    service
      .getEditsForFileRename(module, target, formatSettings(), PREFERENCES)
      .flatMap((change) => change.textChanges.map((t) => ({ path: change.fileName, start: t.span.start, length: t.span.length, newText: t.newText }))),
  );
}

function moveModule(r: Refactor): number {
  const module = r.inProject(r.args.module ?? '');
  const destDir = r.inProject(r.args.dest ?? '');
  if (!existsSync(destDir) || !statSync(destDir).isDirectory()) throw new RefactorError(message('refactor.destination-missing', { path: r.args.dest }));
  const target = join(destDir, basename(module));
  const isDir = statSync(module).isDirectory();
  const files = isDir ? filesUnder(module) : [module];
  const extensions: string[] = language('typescript').source_extensions;
  const sources = files.filter((f) => extensions.some((ext) => f.endsWith(ext)) && r.workspace.owner(f) !== null);
  if (sources.length === 0) r.owner(module);
  const moves = files.map((f): [string, string] => [f, join(target, relative(module, f))]);
  for (const [, to] of moves) if (existsSync(to)) throw new RefactorError(message('refactor.destination-exists', { path: r.rel(to) }));
  const edits = fileRenameEdits(new Set(sources.flatMap((f) => r.services(f))), module, target);
  const name = isDir ? basename(module) : basename(stripSourceExtension(module));
  const header = message('refactor.ts-move-module-header', { name });
  const code = r.emit([header], mergeEdits(edits), moves);
  if (r.args.apply && isDir) removeEmptyDirs(module);
  return code;
}

function removeEmptyDirs(dir: string): void {
  if (!existsSync(dir)) return;
  for (const entry of readdirSync(dir, { withFileTypes: true })) if (entry.isDirectory()) removeEmptyDirs(join(dir, entry.name));
  if (readdirSync(dir).length === 0) rmdirSync(dir);
}

/** `dr-refactor` on a TypeScript source: 0, 1 with the finding or refusal on stderr, 2 for a site matching nothing. */
export function runTypescriptRefactor(args: RefactorArgs): number {
  try {
    const r = new Refactor(args);
    if (args.subcommand === 'rename' || args.subcommand === 'retarget') return single(r);
    if (args.subcommand === 'rename-map') return renameMap(r);
    if (args.subcommand === 'move-symbol') return moveSymbol(r);
    return moveModule(r);
  } catch (error) {
    if (error instanceof SiteError) {
      process.stderr.write(`${message(error.template, { site: error.site, ...error.values })}\n`);
      return 2;
    }
    if (error instanceof LocatorError || error instanceof UsageError || error instanceof MapError) {
      process.stderr.write(`${error.message}\n`);
      return 2;
    }
    if (!(error instanceof RefactorError)) throw error;
    process.stderr.write(`${error.message}\n`);
    return 1;
  }
}
