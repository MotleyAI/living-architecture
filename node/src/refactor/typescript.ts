// `dr-refactor` for TypeScript: rename, move-symbol and move-module through the bundled language service.
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmdirSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { basename, dirname, isAbsolute, join, relative, sep } from 'node:path';
import type * as TS from 'typescript';
import { sourceFiles } from '../config/index.js';
import { byCodePoint, language, manifest, message } from '../contract/index.js';
import { canonical, posix, stripSourceExtension, ts } from '../lang/index.js';
import { unifiedDiff } from './diff.js';
import { applyEdits, type Edit, mergeEdits, RefactorError } from './edits.js';
import { anyAccesses, type FormCall, formCalls, isAny, type MemberDeclaration, memberDeclarations, memberNameStart } from './members.js';
import { codeMarked, type Mention, mentions, type Owner, qualified, type Region, sourceRegions } from './mentions.js';
import { blindspotOutcome, formCallOutcome, literalOutcomes, mentionOutcome, type Outcome } from './outcomes.js';
import { CHECKER_OPTIONS } from './compliance.js';
import { Lines } from './lines.js';
import { languageFiles, realPath, under } from './routing.js';
import { Site, SiteError } from './sites.js';
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
  allow_blindspots?: boolean;
  with_stand_ins?: string[];
  without_stand_ins?: string[];
  keep?: string[];
  docs?: boolean;
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

class Refactor {
  readonly root: string;
  private readonly cwd = process.cwd();
  private workspaceCache: Workspace | null = null;

  constructor(readonly args: RefactorArgs) {
    this.root = realPath(under(this.cwd, args.project));
  }

  get workspace(): Workspace {
    this.workspaceCache ??= new Workspace(this.root);
    return this.workspaceCache;
  }

  rel(path: string): string {
    return posix(relative(this.root, path));
  }

  /** `raw` from the working directory with symlinks resolved; RefactorError when outside the project. */
  inProject(raw: string): string {
    const path = realPath(under(this.cwd, raw));
    const rel = relative(this.root, path);
    if (rel.split(sep)[0] === '..' || isAbsolute(rel)) throw new RefactorError(message('refactor.outside-project', { path: raw }));
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
    const body = entries.map((e) => `${e.text}\n`).join('');
    let out = `${header}\n\n\n${body}\n`;
    if (this.args.apply) {
      for (const [path, text] of written.toSorted((a, b) => byCodePoint(a[0], b[0]))) writeFileSync(path, text);
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
  if (args.offset !== undefined) return locateOffset(text, args.offset);
  if (args.line !== undefined) return locateLine(text, args.line, args.col ?? 1);
  if (args.name !== undefined) return locateName(path, text, args.name);
  throw new RefactorError(message('refactor.no-locator'));
}

function locateOffset(text: string, offset: number): number {
  const count = codePoints(text).length;
  if (offset < 0 || offset > count) throw new RefactorError(message('refactor.offset-out-of-range', { offset, count }));
  return utf16(text, offset);
}

function locateLine(text: string, line: number, col: number): number {
  const lines = new Lines(text);
  if (line < 1 || line > lines.count) throw new RefactorError(message('refactor.line-out-of-range', { line, count: lines.count }));
  const lineText = lines.lineText(line);
  const width = codePoints(lineText).length;
  if (col < 1 || col > width + 1) throw new RefactorError(message('refactor.col-out-of-range', { col, line, count: width }));
  return lines.start(line) + utf16(lineText, col - 1);
}

function locateName(path: string, text: string, name: string): number {
  const file = sourceFile(path, text);
  const all = [...nodes(file)];
  const starts = (found: TS.Node[]): number[] => found.map((n) => n.getStart(file)).sort((a, b) => a - b);
  const [declared] = starts(all.filter((n) => isNamedDeclaration(n, name)).map((n) => (n as TS.NamedDeclaration).name as TS.Node));
  const [used] = starts(all.filter((n) => ts().isIdentifier(n) && n.text === name));
  const position = declared ?? used;
  if (position === undefined) throw new RefactorError(message('refactor.symbol-not-found', { name }));
  return position;
}

interface Finding {
  path: string;
  line: number;
  position: number;
  text: string;
}

/** A source of the rename's projects with the service and checker of the first program holding it. */
interface ProjectSource {
  source: TS.SourceFile;
  service: TS.LanguageService;
  checker: TS.TypeChecker;
}

const keyOf = (path: string, start: number): string => `${path}\0${start}`;
const byPosition = (a: Finding, b: Finding): number => byCodePoint(a.path, b.path) || a.line - b.line || a.position - b.position;

/** Every service's rename locations of the symbol at `position` of `file`. */
function renameLocations(services: TS.LanguageService[], file: string, position: number, newName: string): Edit[] {
  const edits: Edit[] = [];
  for (const service of services) {
    for (const location of service.findRenameLocations(file, position, false, false, { providePrefixAndSuffixTextForRename: true }) ?? []) {
      const newText = `${location.prefixText ?? ''}${newName}${location.suffixText ?? ''}`;
      edits.push({ path: location.fileName, start: location.textSpan.start, length: location.textSpan.length, newText });
    }
  }
  return edits;
}

/** The project's TypeScript files (the files `dr-compliance` expands the project to), each from the first of
 * `services`' programs holding it, else from its governing project's program. */
function projectSources(r: Refactor, services: TS.LanguageService[]): Map<string, ProjectSource> {
  const out = new Map<string, ProjectSource>();
  const rest: string[] = [];
  for (const path of languageFiles(r.root, 'typescript')) {
    const found = services.find((service) => service.getProgram()?.getSourceFile(path) !== undefined);
    const program = found?.getProgram();
    const source = program?.getSourceFile(path);
    if (found === undefined || program === undefined || source === undefined) rest.push(path);
    else out.set(source.fileName, { source, service: found, checker: program.getTypeChecker() });
  }
  for (const [path, service] of r.workspace.servicesOf(rest, CHECKER_OPTIONS)) {
    const program = service.getProgram();
    const source = program?.getSourceFile(path);
    if (program !== undefined && source !== undefined) out.set(source.fileName, { source, service, checker: program.getTypeChecker() });
  }
  return out;
}

/** The module path of a source for qualified mentions: its project-relative path without extension. */
const modulePath = (r: Refactor, path: string): string[] => r.rel(stripSourceExtension(path)).split('/');

class TypescriptRename {
  readonly edits: Edit[];
  readonly renamed = new Set<string>();
  readonly declaring = new Set<string>();
  blindspots: Finding[] = [];
  standIns: Finding[] = [];
  leftovers: Finding[] = [];
  private readonly sources: Map<string, ProjectSource>;
  /** The sources spelling OLD, or holding a unicode escape that may spell it: the only ones a reference, a string
   * form or a mention can be in. */
  private readonly holding: ProjectSource[];
  private readonly declarations: MemberDeclaration[];
  private readonly texts = new Map<string, string>();
  private readonly lines = new Map<string, Lines>();
  private readonly examined = new Map<string, [number, number][]>();

  constructor(
    readonly r: Refactor,
    readonly file: string,
    readonly position: number,
    readonly old: string,
    readonly newName: string,
  ) {
    this.edits = renameLocations(r.services(file), file, position, newName);
    this.sources = projectSources(r, r.services(file));
    this.holding = [...this.sources.values()].filter(({ source }) => source.text.includes(old) || source.text.includes(String.raw`\u`));
    this.declarations = [...this.sources.values()].flatMap(({ source, checker }) => memberDeclarations(checker, source, old, source.fileName));
    const declared = new Set(this.declarations.map((d) => keyOf(d.path, d.start)));
    for (const e of this.edits) if (declared.has(keyOf(e.path, e.start))) this.renamed.add(keyOf(e.path, e.start));
  }

  /** `path`'s relevant services, else the one its source came from. */
  private servicesFor(path: string): TS.LanguageService[] {
    const services = this.r.services(path);
    const own = this.sources.get(path)?.service;
    return services.length > 0 || own === undefined ? services : [own];
  }

  get member(): boolean {
    return this.renamed.size > 0;
  }

  text(path: string): string {
    let text = this.texts.get(path);
    if (text === undefined) {
      text = this.sources.get(path)?.source.text ?? readFileSync(path, 'utf8');
      this.texts.set(path, text);
    }
    return text;
  }

  /** The 1-based line of `position` in the file at `path`. */
  lineOf(path: string, position: number): number {
    let lines = this.lines.get(path);
    if (lines === undefined) {
      lines = new Lines(this.text(path));
      this.lines.set(path, lines);
    }
    return lines.lineOf(position);
  }

  private finding(path: string, position: number, template: string, values: Record<string, unknown>): Finding {
    const rel = this.r.rel(path);
    const line = this.lineOf(path, position);
    return { path: rel, line, position, text: message(template, { ...values, path: rel, line }) };
  }

  /** Record an examined site and file what its rule decided. */
  private record(outcome: Outcome): void {
    this.examined.set(outcome.path, [...(this.examined.get(outcome.path) ?? []), [outcome.start, outcome.end]]);
    this.edits.push(...outcome.edits);
    const pending = outcome.finding;
    if (pending === undefined) return;
    const found = this.finding(outcome.path, pending.position, pending.template, pending.values);
    if (outcome.kind === 'blindspot') this.blindspots.push(found);
    else this.leftovers.push(found);
  }

  /** `start`..`end` of `path` overlaps an examined site or an edit. */
  private covered(path: string, start: number, end: number): boolean {
    if ((this.examined.get(path) ?? []).some(([s, e]) => s < end && start < e)) return true;
    return this.edits.some((e) => e.path === path && e.start < end && start < e.start + e.length);
  }

  /** Join every `--with` stand-in's rename; record the stand-ins left unclassified. */
  classify(withSites: string[], withoutSites: string[]): void {
    for (const d of this.declarations) this.examined.set(d.path, [...(this.examined.get(d.path) ?? []), [d.start, d.start + this.old.length]]);
    const declared = new Set(this.declarations.map((d) => keyOf(d.path, d.start)));
    const candidates = this.declarations.filter((d) => !this.renamed.has(keyOf(d.path, d.start)));
    const classified = new Set<string>();
    for (const [raw, joined] of [...withSites.map((s) => [s, true] as const), ...withoutSites.map((s) => [s, false] as const)]) {
      const site = Site.parse(raw, this.r.root, this.r.root);
      const matched = candidates.filter((d) => site.line !== null && site.covers(this.r.rel(d.path), d.line));
      if (matched.length === 0) throw new SiteError('refactor.not-stand-in', raw);
      for (const d of matched) this.classifyStandIn(d, raw, joined, declared, classified);
    }
    this.standIns = candidates
      .filter((d) => !classified.has(keyOf(d.path, d.start)))
      .map((d) => this.finding(d.path, d.start, 'refactor.stand-in', { cls: d.owner, attr: this.old }));
  }

  /** Classify stand-in `d` and its hierarchy by site `raw`; with `joined` its rename joins this one, which a computed
   * name cannot. */
  private classifyStandIn(d: MemberDeclaration, raw: string, joined: boolean, declared: Set<string>, classified: Set<string>): void {
    if (joined && d.computed) {
      const values = { path: this.r.rel(d.path), line: d.line, cls: d.owner, attr: this.old };
      throw new SiteError('refactor.computed-stand-in', raw, values);
    }
    const theirs = renameLocations(this.servicesFor(d.path), d.path, d.start, this.newName);
    const keys = [keyOf(d.path, d.start), ...theirs.map((e) => keyOf(e.path, e.start)).filter((k) => declared.has(k))];
    for (const k of keys) classified.add(k);
    if (!joined) return;
    this.edits.push(...theirs);
    for (const k of keys) this.renamed.add(k);
  }

  /** Whether declaration `d` of OLD is renamed. */
  private isRenamed(d: TS.Declaration): boolean {
    const file = d.getSourceFile();
    const name = ts().getNameOfDeclaration(d);
    if (name === undefined) return false;
    return this.renamed.has(keyOf(file.fileName, memberNameStart(name, this.old, file) ?? name.getStart(file)));
  }

  /** Member strings landing only on renamed declarations are rewritten; `any` receivers and strings landing on
   * renamed and unchanged declarations are blind spots. */
  scan(): void {
    for (const { source, checker } of this.holding) {
      const path = source.fileName;
      for (const { position, receiver, literal } of anyAccesses(checker, source, this.old)) this.record(blindspotOutcome(path, position, literal ?? null, receiver, this.old));
      for (const found of formCalls(checker, source, this.old)) {
        const receiver = found.object.getText(source);
        if (isAny(checker, found.object)) {
          this.record(blindspotOutcome(path, found.call.getStart(source), [found.start, found.end], receiver, this.old));
        } else {
          this.record(formCallOutcome(path, found, this.landings(checker, found), receiver, this.old, this.newName));
        }
      }
    }
  }

  /** Whether each declaration a typed member form's lookup lands on is renamed. */
  private landings(checker: TS.TypeChecker, found: FormCall): boolean[] {
    const type = checker.getApparentType(checker.getTypeAtLocation(found.object));
    return (type.getProperty(this.old)?.declarations ?? []).map((d) => this.isRenamed(d));
  }

  /** Without `--docs`: each string literal exactly OLD that no rule examined, listed; every project file, as an
   * escape can spell OLD. */
  literals(): void {
    for (const { source } of this.sources.values()) {
      for (const outcome of literalOutcomes(source.fileName, source, this.old, (s, e) => this.covered(source.fileName, s, e))) this.record(outcome);
    }
  }

  private owners(): Owner[] {
    if (!this.member) {
      const declarations = this.r.services(this.file)[0]?.getDefinitionAtPosition(this.file, this.position) ?? [];
      for (const d of declarations) this.declaring.add(d.fileName);
      return [...this.declaring].map((path) => ({ path: modulePath(this.r, path), member: false }));
    }
    return this.declarations
      .filter((d) => this.renamed.has(keyOf(d.path, d.start)))
      .map((d) => {
        this.declaring.add(d.path);
        return { path: [...modulePath(this.r, d.path), d.owner], member: true };
      });
  }

  /** Each scanned file's mentions of OLD, and whether it declares the rename: sources, then prose files. */
  private mentionFiles(): [string, Mention[], boolean][] {
    const files: [string, Mention[], boolean][] = [];
    for (const { source } of this.holding) {
      files.push([source.fileName, mentions(source.text, this.old, sourceRegions(source)), this.declaring.has(source.fileName)]);
    }
    const extensions: string[] = manifest()['dr-refactor'].prose_extensions;
    for (const rel of sourceFiles(this.r.root, []).sort(byCodePoint)) {
      const path = join(this.r.root, rel);
      if (!extensions.some((ext) => rel.endsWith(ext)) || !existsSync(path)) continue;
      const text = this.text(path);
      if (text.includes(this.old)) files.push([path, mentions(text, this.old, [{ start: 0, end: text.length, where: 'prose', opens: false }]), false]);
    }
    return files;
  }

  /** `--docs`: qualified and code-marked mentions rewritten, the rest listed. */
  docs(): void {
    const owners = this.owners();
    const colliding = this.declarations
      .filter((d) => !this.renamed.has(keyOf(d.path, d.start)))
      .map((d) => [...modulePath(this.r, d.path), d.owner]);
    for (const [path, found, declaring] of this.mentionFiles()) {
      const text = this.text(path);
      for (const m of found) {
        if (this.edits.some((e) => e.path === path && e.start <= m.start && m.start < e.start + e.length)) continue;
        const rewritten = qualified(text, m.start, owners, colliding) || (declaring && codeMarked(text, m));
        this.record(mentionOutcome(path, m, rewritten, this.old, this.newName));
      }
    }
  }

  /** Without `--docs`, comments stay: drop the language service's edits inside them (JSDoc links and tags). */
  dropCommentEdits(): void {
    const comments = new Map<string, Region[]>();
    const inComment = (e: Edit): boolean => {
      const source = this.sources.get(e.path)?.source;
      if (source === undefined) return false;
      if (!comments.has(e.path)) comments.set(e.path, sourceRegions(source).filter((region) => region.where === 'comment'));
      return (comments.get(e.path) ?? []).some((region) => region.start <= e.start && e.start < region.end);
    };
    const kept = this.edits.filter((e) => !inComment(e));
    this.edits.splice(0, this.edits.length, ...kept);
  }

  /** Drop every edit and blind spot at a kept site; SiteError for a keep that matches neither. */
  keep(raws: string[]): Edit[] {
    const sites = raws.map((raw) => Site.parse(raw, this.r.root));
    const matched = new Set<number>();
    const kept = (rel: string, line: number, mark = true): boolean => {
      const hits = sites.flatMap((site, i) => (site.covers(rel, line) ? [i] : []));
      if (mark) for (const i of hits) matched.add(i);
      return hits.length > 0;
    };
    const edits = this.edits.filter((e) => !kept(this.r.rel(e.path), this.lineOf(e.path, e.start)));
    this.blindspots = this.blindspots.filter((b) => !kept(b.path, b.line)).sort(byPosition);
    this.leftovers = this.leftovers.filter((f) => !kept(f.path, f.line, false)).sort(byPosition);
    this.standIns.sort(byPosition);
    const unmatched = sites.find((_, i) => !matched.has(i));
    if (unmatched !== undefined) throw new SiteError('refactor.keep-unmatched', unmatched.raw);
    return edits;
  }
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
  const old = text.slice(info.triggerSpan.start, info.triggerSpan.start + info.triggerSpan.length);
  const symbol = new TypescriptRename(r, file, position, old, newName);
  const withSites = r.args.with_stand_ins ?? [];
  const withoutSites = r.args.without_stand_ins ?? [];
  if (symbol.member) {
    symbol.classify(withSites, withoutSites);
    symbol.scan();
  } else if (withSites.length > 0 || withoutSites.length > 0) {
    throw new SiteError('refactor.not-stand-in', [...withSites, ...withoutSites][0] ?? '');
  }
  if (r.args.docs === true) symbol.docs();
  else symbol.dropCommentEdits();
  if (symbol.member && r.args.docs !== true) symbol.literals();
  const edits = symbol.keep(r.args.keep ?? []);
  const allowed = r.args.allow_blindspots === true;
  if ((symbol.blindspots.length > 0 && !allowed) || symbol.standIns.length > 0) {
    const closing = allowed || symbol.blindspots.length === 0 ? [] : [message('refactor.blindspots', { count: symbol.blindspots.length, attr: old })];
    const lines = [...symbol.blindspots.map((f) => f.text), ...symbol.standIns.map((f) => f.text), ...closing];
    process.stderr.write(lines.map((line) => `${line}\n`).join(''));
    return 1;
  }
  process.stderr.write([...symbol.blindspots, ...symbol.leftovers].map((f) => `${f.text}\n`).join(''));
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
  const text = readFileSync(file, 'utf8');
  const position = locate(r.args, file, text);
  r.owner(file);
  const notMovable = (): RefactorError => new RefactorError(message('refactor.not-movable', { path: r.rel(file) }));
  const services = r.services(file);
  const statement = services[0] === undefined ? null : topLevelStatement(services[0], file, position);
  if (statement === null) throw notMovable();
  const header = message('refactor.ts-move-symbol-header', { name: declaredName(statement) });
  if (dest === file) return r.emit(header, new Map(), []);
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
  return r.emit(header, mergeEdits(edits), []);
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
  const code = r.emit(header, mergeEdits(edits), moves);
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
    if (args.subcommand === 'rename') return rename(r);
    if (args.subcommand === 'move-symbol') return moveSymbol(r);
    return moveModule(r);
  } catch (error) {
    if (error instanceof SiteError) {
      process.stderr.write(`${message(error.template, { site: error.site, ...error.values })}\n`);
      return 2;
    }
    if (!(error instanceof RefactorError)) throw error;
    process.stderr.write(`${error.message}\n`);
    return 1;
  }
}
