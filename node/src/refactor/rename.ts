// `dr-refactor rename`, `retarget` and `rename-map` for TypeScript: every entry resolved first, then each rename
// rule once per old name over one session, one refusal report and one change set.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type * as TS from 'typescript';
import { sourceFiles } from '../config/index.js';
import { byCodePoint, literalValueForbidden, manifest, message } from '../contract/index.js';
import { stripSourceExtension, ts } from '../lang/index.js';
import { isCompound } from './compound.js';
import { type Edit, mergeEdits, RefactorError } from './edits.js';
import { Lines } from './lines.js';
import { anyAccesses, type FormCall, formCalls, isAny, type MemberDeclaration, memberDeclarations, memberNameStart, walk } from './members.js';
import { codeMarked, type Mention, mentions, type Owner, qualified, type Region, sourceRegions } from './mentions.js';
import { blindspotOutcome, compoundOutcome, formCallOutcome, literalOutcomes, mentionOutcome, type Outcome } from './outcomes.js';
import { type Locator, locate, nodeAt, type ProjectSource, projectSources, type Refactor, UsageError } from './session.js';
import { Site, SiteError } from './sites.js';
import { locate as locateSymbol } from './symbols.js';

/** One rename or retarget to compute: its 1-based index, its file (absolute, and as given), locator and intent. */
export interface EntrySpec {
  index: number;
  file: string;
  shown: string;
  locator: Locator;
  newName?: string;
  retarget?: string;
}

/** An entry resolved against the code: its symbol, old and new name, and the language service's rename locations. */
interface Target {
  index: number;
  retarget: boolean;
  file: string;
  position: number;
  old: string;
  newName: string;
  key: string;
  literal: boolean;
  /** A retarget's target symbol; a rename's own. */
  intent: string;
  edits: Edit[];
  /** The alias's own declarations, which a retarget leaves. */
  own: Set<string>;
}

interface Finding {
  path: string;
  line: number;
  position: number;
  text: string;
}

/** An edit with the entry it comes from. */
interface Tagged extends Edit {
  entry: number;
}

const SENTINEL = '\0dr-refactor';
const keyOf = (path: string, start: number): string => `${path}\0${start}`;
const byPosition = (a: Finding, b: Finding): number => byCodePoint(a.path, b.path) || a.line - b.line || a.position - b.position;
const isString = (node: TS.Node): node is TS.StringLiteral | TS.NoSubstitutionTemplateLiteral =>
  ts().isStringLiteral(node) || ts().isNoSubstitutionTemplateLiteral(node);

/** Every service's rename locations of the symbol at `position` of `file`. */
/** The language services' rename edits. `stable` keeps a re-exported name as it is (`x as y`); a retarget passes false
 * so it reaches the importers of a re-export, a shorthand property still keeping its key (`old: new`). */
function renameLocations(services: TS.LanguageService[], file: string, position: number, newName: string, stable = true): Edit[] {
  const edits: Edit[] = [];
  for (const service of services) {
    for (const location of service.findRenameLocations(file, position, false, false, { providePrefixAndSuffixTextForRename: stable }) ?? []) {
      const source = service.getProgram()?.getSourceFile(location.fileName);
      const node = source === undefined ? undefined : nodeAt(source, location.textSpan.start);
      const shorthand = !stable && node !== undefined && ts().isShorthandPropertyAssignment(node.parent) && node.parent.name === node;
      const newText = shorthand ? `${node.getText()}: ${newName}` : `${location.prefixText ?? ''}${newName}${location.suffixText ?? ''}`;
      edits.push({ path: location.fileName, start: location.textSpan.start, length: location.textSpan.length, newText });
    }
  }
  return edits;
}

/** The symbol `node` names, an import binding followed to what it imports. */
function symbolOf(checker: TS.TypeChecker, node: TS.Node): TS.Symbol | undefined {
  const symbol = checker.getSymbolAtLocation(node);
  const aliased = symbol !== undefined && (symbol.flags & ts().SymbolFlags.Alias) !== 0; // NOSONAR(S1529) — SymbolFlags bitmask test
  return aliased ? checker.getAliasedSymbol(symbol) : symbol;
}

/** The name starts of a symbol's declarations, as keys. */
function declarationKeys(symbol: TS.Symbol | undefined, old: string): string[] {
  return (symbol?.declarations ?? []).flatMap((d) => {
    const file = d.getSourceFile();
    const name = ts().getNameOfDeclaration(d);
    return name === undefined ? [] : [keyOf(file.fileName, memberNameStart(name, old, file) ?? name.getStart(file))];
  });
}

/** The body, class or file that holds declaration `node`. */
function scopeOf(node: TS.Node): TS.Node {
  let scope = node.parent;
  while (!(ts().isFunctionLike(scope) || ts().isSourceFile(scope) || ts().isModuleBlock(scope) || ts().isClassLike(scope) || ts().isInterfaceDeclaration(scope) || ts().isTypeLiteralNode(scope) || ts().isEnumDeclaration(scope))) {
    scope = scope.parent;
  }
  return scope;
}

/** The module path of a source for qualified mentions: its project-relative path without extension. */
const modulePath = (r: Refactor, path: string): string[] => r.rel(stripSourceExtension(path)).split('/');

/** The project's sources and their texts, read once for every rule of every entry. */
class Session {
  readonly sources: Map<string, ProjectSource>;
  private readonly texts = new Map<string, string>();
  private readonly lines = new Map<string, Lines>();

  constructor(
    readonly r: Refactor,
    files: string[],
  ) {
    this.sources = projectSources(r, [...new Set(files.flatMap((file) => r.services(file)))]);
  }

  /** `path`'s relevant services, else the one its source came from. */
  servicesFor(path: string): TS.LanguageService[] {
    const services = this.r.services(path);
    const own = this.sources.get(path)?.service;
    return services.length > 0 || own === undefined ? services : [own];
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

  finding(path: string, position: number, template: string, values: Record<string, unknown>): Finding {
    const rel = this.r.rel(path);
    const line = this.lineOf(path, position);
    return { path: rel, line, position, text: message(template, { ...values, path: rel, line }) };
  }
}

/** The entries renaming one old name: each rule runs once over all of them. */
class NameGroup {
  readonly edits: Tagged[] = [];
  /** Each renamed member declaration's new name. */
  readonly renamed = new Map<string, string>();
  readonly declaring = new Set<string>();
  blindspots: Finding[] = [];
  standIns: Finding[] = [];
  leftovers: Finding[] = [];
  /** The sources spelling OLD, or holding a unicode escape that may spell it: the only ones a reference, a string
   * form or a mention can be in. */
  private readonly holding: ProjectSource[];
  private readonly declarations: MemberDeclaration[];
  private readonly examined = new Map<string, [number, number][]>();
  private readonly literalSites = new Map<string, [number, number][]>();
  private readonly entry: number;
  /** The one new name of the group's entries, else null. */
  private readonly newName: string | null;

  constructor(
    readonly session: Session,
    readonly old: string,
    readonly targets: Target[],
  ) {
    const sources = [...session.sources.values()];
    this.entry = (targets[0] as Target).index;
    const names = new Set(targets.map((t) => t.newName));
    this.newName = names.size === 1 ? (targets[0] as Target).newName : null;
    this.holding = sources.filter(({ source }) => source.text.includes(old) || source.text.includes(String.raw`\u`));
    this.declarations = sources.flatMap(({ source, checker }) => memberDeclarations(checker, source, old, source.fileName));
    const declared = new Set(this.declarations.map((d) => keyOf(d.path, d.start)));
    for (const target of targets) {
      for (const e of target.edits) {
        this.edits.push({ ...e, entry: target.index });
        if (declared.has(keyOf(e.path, e.start))) this.renamed.set(keyOf(e.path, e.start), target.newName);
      }
    }
  }

  private get r(): Refactor {
    return this.session.r;
  }

  get member(): boolean {
    return this.renamed.size > 0;
  }

  get literal(): boolean {
    return this.targets.some((t) => t.literal);
  }

  /** Record an examined site and file what its rule decided. */
  private record(outcome: Outcome): void {
    this.examined.set(outcome.path, [...(this.examined.get(outcome.path) ?? []), [outcome.start, outcome.end]]);
    this.edits.push(...outcome.edits.map((e) => ({ ...e, entry: this.entry })));
    const pending = outcome.finding;
    if (pending === undefined) return;
    const found = this.session.finding(outcome.path, pending.position, pending.template, pending.values);
    if (outcome.kind === 'blindspot') this.blindspots.push(found);
    else this.leftovers.push(found);
  }

  private edited(path: string, start: number, end: number): boolean {
    return this.edits.some((e) => e.path === path && e.start < end && start < e.start + e.length);
  }

  /** `start`..`end` of `path` overlaps an examined site or an edit. */
  private covered(path: string, start: number, end: number): boolean {
    if ((this.examined.get(path) ?? []).some(([s, e]) => s < end && start < e)) return true;
    return this.edited(path, start, end);
  }

  /** Join every `--with` stand-in's rename; record the stand-ins left unclassified; the sites that matched one. */
  classify(withSites: string[], withoutSites: string[]): Set<string> {
    for (const d of this.declarations) this.examined.set(d.path, [...(this.examined.get(d.path) ?? []), [d.start, d.start + this.old.length]]);
    const declared = new Set(this.declarations.map((d) => keyOf(d.path, d.start)));
    const candidates = this.declarations.filter((d) => !this.renamed.has(keyOf(d.path, d.start)));
    const classified = new Set<string>();
    const matchedSites = new Set<string>();
    for (const [raw, joined] of [...withSites.map((s) => [s, true] as const), ...withoutSites.map((s) => [s, false] as const)]) {
      const site = Site.parse(raw, this.r.root, this.r.root);
      const matched = candidates.filter((d) => site.line !== null && site.covers(this.r.rel(d.path), d.line));
      if (matched.length > 0) matchedSites.add(raw);
      for (const d of matched) this.classifyStandIn(d, raw, joined, declared, classified);
    }
    this.standIns = candidates
      .filter((d) => !classified.has(keyOf(d.path, d.start)))
      .map((d) => this.session.finding(d.path, d.start, 'refactor.stand-in', { cls: d.owner, attr: this.old }));
    return matchedSites;
  }

  /** Classify stand-in `d` and its hierarchy by site `raw`; with `joined` its rename joins this one, which a computed
   * name cannot. */
  private classifyStandIn(d: MemberDeclaration, raw: string, joined: boolean, declared: Set<string>, classified: Set<string>): void {
    if (joined && d.computed) {
      const values = { path: this.r.rel(d.path), line: d.line, cls: d.owner, attr: this.old };
      throw new SiteError('refactor.computed-stand-in', raw, values);
    }
    const newName = (this.targets[0] as Target).newName;
    const theirs = renameLocations(this.session.servicesFor(d.path), d.path, d.start, newName);
    const keys = [keyOf(d.path, d.start), ...theirs.map((e) => keyOf(e.path, e.start)).filter((k) => declared.has(k))];
    for (const k of keys) classified.add(k);
    if (!joined) return;
    this.edits.push(...theirs.map((e) => ({ ...e, entry: this.entry })));
    for (const k of keys) this.renamed.set(k, newName);
  }

  /** The new name of declaration `d` of OLD, null when it is unchanged. */
  private newNameOf(d: TS.Declaration): string | null {
    const file = d.getSourceFile();
    const name = ts().getNameOfDeclaration(d);
    if (name === undefined) return null;
    return this.renamed.get(keyOf(file.fileName, memberNameStart(name, this.old, file) ?? name.getStart(file))) ?? null;
  }

  /** Member strings landing only on declarations renamed to one name are rewritten; `any` receivers and strings
   * landing on renamed and unchanged declarations are blind spots. */
  scan(): void {
    for (const { source, checker } of this.holding) {
      const path = source.fileName;
      for (const { position, receiver, literal } of anyAccesses(checker, source, this.old)) this.record(blindspotOutcome(path, position, literal ?? null, receiver, this.old));
      for (const found of formCalls(checker, source, this.old)) {
        const receiver = found.object.getText(source);
        if (isAny(checker, found.object)) {
          this.record(blindspotOutcome(path, found.call.getStart(source), [found.start, found.end], receiver, this.old));
        } else {
          const names = this.landings(checker, found);
          const distinct = new Set(names.filter((n) => n !== null));
          const renamed = distinct.size > 1 ? [true, false] : names.map((n) => n !== null);
          this.record(formCallOutcome(path, found, renamed, receiver, this.old, [...distinct][0] ?? ''));
        }
      }
    }
  }

  /** The new name of each declaration a typed member form's lookup lands on, null for an unchanged one. */
  private landings(checker: TS.TypeChecker, found: FormCall): (string | null)[] {
    const type = checker.getApparentType(checker.getTypeAtLocation(found.object));
    return (type.getProperty(this.old)?.declarations ?? []).map((d) => this.newNameOf(d));
  }

  /** Each string literal exactly OLD that no rule examined, listed; every project file, as an escape can spell OLD. */
  literals(): void {
    for (const { source } of this.session.sources.values()) {
      for (const outcome of literalOutcomes(source.fileName, source, this.old, (s, e) => this.covered(source.fileName, s, e))) {
        this.literalSites.set(outcome.path, [...(this.literalSites.get(outcome.path) ?? []), [outcome.start, outcome.end]]);
        this.record(outcome);
      }
    }
  }

  /** A string the checker types by a literal type this rename leaves: OLD is accepted there and no other string
   * is, and its own rename does not reach a renamed member. */
  private typedByAnother(found: ProjectSource, node: TS.StringLiteral | TS.NoSubstitutionTemplateLiteral): boolean {
    if (ts().isLiteralTypeNode(node.parent)) return false;
    const { checker } = found;
    const contextual = checker.getContextualType(node);
    const accepts = (value: string): boolean => contextual !== undefined && checker.isTypeAssignableTo(checker.getStringLiteralType(value), contextual);
    if (!accepts(this.old) || accepts(SENTINEL)) return false;
    const reached = found.service.findRenameLocations(found.source.fileName, node.getStart(found.source) + 1, false, false, {}) ?? [];
    const renamedSpans = new Set(this.targets.flatMap((t) => t.edits.map((e) => keyOf(e.path, e.start))));
    return !reached.some((location) => renamedSpans.has(keyOf(location.fileName, location.textSpan.start)));
  }

  /** A literal member's other equal strings: one typed by another literal type is unrelated, the rest are listed. */
  equalStrings(): void {
    for (const found of this.session.sources.values()) {
      const { source } = found;
      if (!source.text.includes(this.old)) continue;
      for (const node of walk(source)) {
        if (!isString(node) || node.text !== this.old) continue;
        const [start, end] = [node.getStart(source), node.end];
        if (this.edited(source.fileName, start, end) || !this.typedByAnother(found, node)) continue;
        this.literalSites.set(source.fileName, [...(this.literalSites.get(source.fileName) ?? []), [start, end]]);
        this.record({ kind: 'unrelated', path: source.fileName, start, end, edits: [] });
      }
    }
    this.literals();
  }

  private owners(): Owner[] {
    if (!this.member) {
      for (const target of this.targets) {
        const declarations = this.r.services(target.file)[0]?.getDefinitionAtPosition(target.file, target.position) ?? [];
        for (const d of declarations) this.declaring.add(d.fileName);
      }
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
      const text = this.session.text(path);
      if (text.includes(this.old)) files.push([path, mentions(text, this.old, [{ start: 0, end: text.length, where: 'prose', opens: false }]), false]);
    }
    return files;
  }

  /** `--docs`: qualified and code-marked mentions rewritten (when the group has one new name), the rest listed. */
  docs(): void {
    const owners = this.owners();
    const colliding = this.declarations
      .filter((d) => !this.renamed.has(keyOf(d.path, d.start)))
      .map((d) => [...modulePath(this.r, d.path), d.owner]);
    for (const [path, found, declaring] of this.mentionFiles()) {
      const text = this.session.text(path);
      for (const m of found) {
        if (this.edits.some((e) => e.path === path && e.start <= m.start && m.start < e.start + e.length)) continue;
        if ((this.literalSites.get(path) ?? []).some(([s, e]) => s <= m.start && m.start < e)) continue;
        const rewritten = this.newName !== null && (qualified(text, m.start, owners, colliding) || (declaring && codeMarked(text, m)));
        this.record(mentionOutcome(path, m, rewritten, this.old, this.newName ?? ''));
      }
    }
  }

  /** `--docs`: each declaration whose name holds OLD as a word sequence, listed; `renamedNames` are never listed. */
  compounds(renamedNames: Set<string>): void {
    for (const { source, checker } of this.session.sources.values()) {
      const seen = new Set<TS.Symbol>();
      for (const node of walk(source)) {
        const name = this.compoundName(node, renamedNames);
        if (name === null) continue;
        const symbol = checker.getSymbolAtLocation(name);
        if (symbol !== undefined && seen.has(symbol)) continue;
        if (symbol !== undefined) seen.add(symbol);
        this.record(compoundOutcome(source.fileName, name.getStart(source), name.end, name.text, this.old));
      }
    }
  }

  private compoundName(node: TS.Node, renamedNames: Set<string>): TS.Identifier | null {
    const name = isDeclaration(node) ? node.name : undefined;
    if (name === undefined || !ts().isIdentifier(name)) return null;
    return renamedNames.has(name.text) || !isCompound(name.text, this.old) ? null : name;
  }

  /** Without `--docs`, comments stay: drop the language service's edits inside them (JSDoc links and tags). */
  dropCommentEdits(): void {
    const comments = new Map<string, Region[]>();
    const inComment = (e: Edit): boolean => {
      const source = this.session.sources.get(e.path)?.source;
      if (source === undefined) return false;
      if (!comments.has(e.path)) comments.set(e.path, sourceRegions(source).filter((region) => region.where === 'comment'));
      return (comments.get(e.path) ?? []).some((region) => region.start <= e.start && e.start < region.end);
    };
    const kept = this.edits.filter((e) => !inComment(e));
    this.edits.splice(0, this.edits.length, ...kept);
  }

  /** Drop the edits at a retargeted alias's own declarations. */
  dropOwnDeclarations(): void {
    const own = new Set(this.targets.flatMap((t) => [...t.own]));
    const kept = this.edits.filter((e) => !own.has(keyOf(e.path, e.start)));
    this.edits.splice(0, this.edits.length, ...kept);
  }
}

type Named = TS.Node & { name?: TS.Node };

/** A node declaring its `name`: a variable, function, class, type, member, parameter or binding. */
function isDeclaration(node: TS.Node): node is Named {
  return (
    ts().isVariableDeclaration(node) ||
    ts().isBindingElement(node) ||
    ts().isParameter(node) ||
    ts().isFunctionDeclaration(node) ||
    ts().isFunctionExpression(node) ||
    ts().isClassLike(node) ||
    ts().isInterfaceDeclaration(node) ||
    ts().isTypeAliasDeclaration(node) ||
    ts().isEnumDeclaration(node) ||
    ts().isEnumMember(node) ||
    ts().isModuleDeclaration(node) ||
    ts().isTypeParameterDeclaration(node) ||
    ts().isClassElement(node) ||
    ts().isTypeElement(node)
  );
}

/** The first rename location of the symbol at `position`, as a key: one symbol's locators share it. */
function firstLocation(services: TS.LanguageService[], file: string, position: number): string | undefined {
  const first = renameLocations(services, file, position, '').toSorted((a, b) => byCodePoint(a.path, b.path) || a.start - b.start)[0];
  return first === undefined ? undefined : keyOf(first.path, first.start);
}

/** `spec` resolved: the symbol its locator names, and what can be renamed there. */
function resolve(r: Refactor, spec: EntrySpec): Target {
  const located = locate(r, spec.file, spec.shown, spec.locator);
  const { file, position } = located;
  r.owner(file);
  const services = r.services(file);
  const info = services[0]?.getRenameInfo(file, position, { allowRenameOfImportPath: false });
  const named = info?.canRename === true && info.triggerSpan.start <= position && position <= info.triggerSpan.start + info.triggerSpan.length;
  const program = services[0]?.getProgram();
  const source = program?.getSourceFile(file);
  if (info === undefined || !info.canRename || !named || program === undefined || source === undefined) throw new RefactorError(message('refactor.cannot-rename'));
  const old = source.text.slice(info.triggerSpan.start, info.triggerSpan.start + info.triggerSpan.length);
  const node = nodeAt(source, position);
  const literal = isString(node);
  const symbol = literal ? undefined : symbolOf(program.getTypeChecker(), node);
  const key = declarationKeys(symbol, old)[0] ?? firstLocation(services, file, position) ?? keyOf(file, info.triggerSpan.start);
  return { index: spec.index, retarget: spec.retarget !== undefined, file, position, old, newName: spec.newName ?? '', key, literal, intent: key, edits: [], own: new Set() };
}

/** A retarget's target resolved: declared beside the alias, else UsageError; the alias's own declarations recorded. */
function resolveRetarget(r: Refactor, spec: EntrySpec, target: Target, raw: string): { key: string; name: string } {
  const program = r.services(target.file)[0]?.getProgram();
  const source = program?.getSourceFile(spec.file);
  const aliasSource = program?.getSourceFile(target.file);
  if (program === undefined || source === undefined || aliasSource === undefined) throw new RefactorError(message('refactor.ts-outside-project', { path: r.rel(spec.file) }));
  const checker = program.getTypeChecker();
  const located = locateSymbol(checker, source, raw, spec.shown);
  const targetSource = program.getSourceFile(located.file);
  const alias = symbolOf(checker, nodeAt(aliasSource, target.position));
  const symbol = targetSource === undefined ? undefined : symbolOf(checker, nodeAt(targetSource, located.position));
  const scopes = (s: TS.Symbol | undefined): TS.Node[] => (s?.declarations ?? []).map(scopeOf);
  const beside = scopes(alias).some((scope) => scopes(symbol).includes(scope));
  if (alias === undefined || symbol === undefined || !beside) {
    throw new UsageError(message('refactor.retarget-scope', { target: raw, alias: spec.locator.symbol ?? target.old }));
  }
  for (const key of declarationKeys(alias, target.old)) target.own.add(key);
  return { key: declarationKeys(symbol, symbol.name)[0] ?? keyOf(located.file, located.position), name: symbol.name };
}

/** RefactorError when a renamed local, parameter or top-level name meets its new name, at a site the rename
 * rewrites, declared in the scope that declares the renamed symbol. */
function checkNameConflict(r: Refactor, session: Session, target: Target): void {
  if (target.literal || target.retarget) return;
  const program = r.services(target.file)[0]?.getProgram();
  const source = program?.getSourceFile(target.file);
  if (program === undefined || source === undefined) return;
  const all = ts().SymbolFlags.Value | ts().SymbolFlags.Type | ts().SymbolFlags.Namespace; // NOSONAR(S1529) — SymbolFlags bitmask
  const declarations = symbolOf(program.getTypeChecker(), nodeAt(source, target.position))?.declarations ?? [];
  const scopes = new Set(declarations.filter((d) => !d.getSourceFile().isDeclarationFile).map(scopeOf));
  for (const scope of scopes) if (ts().isClassLike(scope) || ts().isInterfaceDeclaration(scope) || ts().isTypeLiteralNode(scope) || ts().isEnumDeclaration(scope)) return;
  for (const edit of target.edits) {
    const found = session.sources.get(edit.path);
    if (found === undefined) continue;
    const taken = found.checker.resolveName(target.newName, nodeAt(found.source, edit.start), all, false);
    const clash = (taken?.declarations ?? []).find((other) => !other.getSourceFile().isDeclarationFile && scopes.has(scopeOf(other)));
    if (clash === undefined) continue;
    const path = clash.getSourceFile().fileName;
    const line = session.lineOf(path, (ts().getNameOfDeclaration(clash) ?? clash).getStart(clash.getSourceFile()));
    throw new RefactorError(message('refactor.name-conflict', { name: target.newName, path: r.rel(path), line }));
  }
}

/** An identifier read as a bare name: not a member name, an import or export specifier, or a declaration's name. */
function bareReference(node: TS.Node): boolean {
  const parent = node.parent;
  if (!ts().isIdentifier(node)) return false;
  if (ts().isPropertyAccessExpression(parent) && parent.name === node) return false;
  if (ts().isQualifiedName(parent) && parent.right === node) return false;
  if (ts().isImportSpecifier(parent) || ts().isExportSpecifier(parent) || ts().isImportClause(parent) || ts().isNamespaceImport(parent)) return false;
  return ts().isShorthandPropertyAssignment(parent) || (parent as { name?: TS.Node }).name !== node;
}

const isTypeOnly = (specifier: TS.ImportSpecifier): boolean => specifier.isTypeOnly || specifier.parent.parent.isTypeOnly;

/** The removal of `specifier` from its list, or of its whole import declaration (and its line) when it binds nothing else. */
function removeSpecifier(source: TS.SourceFile, specifier: TS.ImportSpecifier): Edit {
  const elements = specifier.parent.elements;
  const declaration = specifier.parent.parent.parent;
  if (elements.length === 1 && specifier.parent.parent.name === undefined) {
    const text = source.text;
    const [start, end] = [declaration.getStart(source), declaration.end];
    const lineStart = text.lastIndexOf('\n', start - 1) + 1;
    const newline = text.indexOf('\n', end);
    const lineEnd = newline === -1 ? text.length : newline + 1;
    const alone = text.slice(lineStart, start).trim() === '' && text.slice(end, lineEnd).trim() === '';
    return alone ? { path: source.fileName, start: lineStart, length: lineEnd - lineStart, newText: '' } : { path: source.fileName, start, length: end - start, newText: '' };
  }
  const index = elements.indexOf(specifier);
  const previous = elements[index - 1];
  const next = elements[index + 1];
  const [start, end] = previous === undefined ? [specifier.getStart(source), next?.getStart(source) ?? specifier.end] : [previous.end, specifier.end];
  return { path: source.fileName, start, length: end - start, newText: '' };
}

/** The file's other import specifiers of `module`'s export `name` under that name. */
function importsOf(checker: TS.TypeChecker, source: TS.SourceFile, module: TS.ImportDeclaration, name: string, skip: TS.ImportSpecifier): TS.ImportSpecifier[] {
  const target = checker.getSymbolAtLocation(module.moduleSpecifier);
  const same = (d: TS.ImportDeclaration): boolean =>
    target !== undefined ? checker.getSymbolAtLocation(d.moduleSpecifier) === target : d.moduleSpecifier.getText(source) === module.moduleSpecifier.getText(source);
  return source.statements
    .filter((s): s is TS.ImportDeclaration => ts().isImportDeclaration(s) && same(s))
    .flatMap((d) => {
      const bindings = d.importClause?.namedBindings;
      return bindings !== undefined && ts().isNamedImports(bindings) ? [...bindings.elements] : [];
    })
    .filter((e) => e !== skip && e.name.text === name && (e.propertyName ?? e.name).text === name);
}

/** The edits replacing a retarget's rename of import specifier `node`: its removal when the module is already imported
 * under the target's name with a value import, its rename plus the removal of type-only imports of the target, else null. */
function duplicateImport(source: TS.SourceFile, checker: TS.TypeChecker, node: TS.Node, edit: Edit, name: string): Edit[] | null {
  const specifier = node.parent;
  if (!ts().isImportSpecifier(specifier) || specifier.propertyName !== undefined) return null;
  const declaration = specifier.parent.parent.parent;
  if (!ts().isImportDeclaration(declaration)) return null;
  const twins = importsOf(checker, source, declaration, name, specifier);
  if (twins.some((t) => !isTypeOnly(t)) || (twins.length > 0 && isTypeOnly(specifier))) return [removeSpecifier(source, specifier)];
  return twins.length === 0 ? null : [edit, ...twins.map((t) => removeSpecifier(source, t))];
}

/** A retarget's rename locations checked and adjusted: overrides and shadowed uses as findings, duplicate imports removed. */
/** Where a module re-exports `name` (`export { name }`, `export { local as name }`, `export { name } from`): those
 * specifiers and its imports binding the exported locals. */
function reexportSpans(source: TS.SourceFile, name: string): [number, number][] {
  const exported = source.statements.flatMap((s) =>
    ts().isExportDeclaration(s) && s.exportClause !== undefined && ts().isNamedExports(s.exportClause) ? s.exportClause.elements.filter((e) => e.name.text === name) : [],
  );
  if (exported.length === 0) return [];
  const local = exported.filter((e) => e.parent.parent.moduleSpecifier === undefined);
  const locals = new Set(local.map((e) => (e.propertyName ?? e.name).text));
  const imported = source.statements.flatMap((s): TS.Node[] => {
    const clause = ts().isImportDeclaration(s) ? s.importClause : undefined;
    const bindings = clause?.namedBindings;
    const named = bindings !== undefined && ts().isNamedImports(bindings) ? bindings.elements.filter((e) => locals.has(e.name.text)) : [];
    const namespace = bindings !== undefined && ts().isNamespaceImport(bindings) && locals.has(bindings.name.text) ? [bindings] : [];
    const own = clause?.name !== undefined && locals.has(clause.name.text) ? [clause.name] : [];
    return [...own, ...namespace, ...named];
  });
  return [...exported, ...imported].map((node) => [node.getStart(source), node.end]);
}

function retargetEdits(session: Session, target: Target, targetKey: string): Finding[] {
  const findings: Finding[] = [];
  const members = [...session.sources.values()].flatMap(({ source, checker }) => memberDeclarations(checker, source, target.old, source.fileName));
  const located = new Set(target.edits.map((e) => keyOf(e.path, e.start)));
  for (const d of members) {
    if (located.has(keyOf(d.path, d.start)) && !target.own.has(keyOf(d.path, d.start))) {
      findings.push(session.finding(d.path, d.start, 'refactor.retarget-override', { cls: d.owner, name: target.old }));
    }
  }
  const all = ts().SymbolFlags.Value | ts().SymbolFlags.Type | ts().SymbolFlags.Namespace; // NOSONAR(S1529) — SymbolFlags bitmask
  const kept = new Map<string, [number, number][]>();
  const reexport = (path: string, source: TS.SourceFile, at: number): boolean => {
    if (!kept.has(path)) kept.set(path, reexportSpans(source, target.old));
    return (kept.get(path) ?? []).some(([start, end]) => start <= at && at < end);
  };
  target.edits = target.edits.flatMap((edit) => {
    const found = session.sources.get(edit.path);
    if (found !== undefined && reexport(edit.path, found.source, edit.start)) return [];
    if (found === undefined || target.own.has(keyOf(edit.path, edit.start))) return [edit];
    const node = nodeAt(found.source, edit.start);
    const imports = duplicateImport(found.source, found.checker, node, edit, target.newName);
    if (imports !== null) return imports;
    if (!bareReference(node)) return [edit];
    const bound = found.checker.resolveName(target.newName, node, all, false);
    const resolved = bound !== undefined && (bound.flags & ts().SymbolFlags.Alias) !== 0 ? found.checker.getAliasedSymbol(bound) : bound; // NOSONAR(S1529) — SymbolFlags bitmask test
    if (resolved !== undefined && !declarationKeys(resolved, resolved.name).includes(targetKey)) {
      findings.push(session.finding(edit.path, edit.start, 'refactor.retarget-shadowed', { name: target.newName }));
    }
    return [edit];
  });
  return findings;
}

/** The first site two entries rewrite differently, as a RefactorError; identical edits are one. */
function checkConflicts(session: Session, edits: Tagged[]): void {
  const sorted = edits.toSorted((a, b) => byCodePoint(a.path, b.path) || a.start - b.start);
  for (const [i, a] of sorted.entries()) {
    for (let j = i + 1; j < sorted.length; j += 1) {
      const b = sorted[j] as Tagged;
      if (b.path !== a.path || b.start >= a.start + Math.max(a.length, 1)) break;
      const same = b.start === a.start && b.length === a.length && b.newText === a.newText;
      if (same || a.entry === b.entry) continue;
      const [first, second] = [Math.min(a.entry, b.entry), Math.max(a.entry, b.entry)];
      const line = session.lineOf(a.path, a.start);
      throw new RefactorError(message('refactor.map-conflict', { path: session.r.rel(a.path), line, first, second }));
    }
  }
}

/** Drop every edit, blind spot and leftover at a kept site; SiteError for a keep that matches no edit or blind spot. */
function keep(session: Session, groups: NameGroup[], raws: string[]): Tagged[] {
  const r = session.r;
  const sites = raws.map((raw) => Site.parse(raw, r.root));
  const matched = new Set<number>();
  const kept = (rel: string, line: number, mark = true): boolean => {
    const hits = sites.flatMap((site, i) => (site.covers(rel, line) ? [i] : []));
    if (mark) for (const i of hits) matched.add(i);
    return hits.length > 0;
  };
  const edits = groups.flatMap((g) => g.edits).filter((e) => !kept(r.rel(e.path), session.lineOf(e.path, e.start)));
  for (const group of groups) {
    group.blindspots = group.blindspots.filter((b) => !kept(b.path, b.line));
    group.leftovers = group.leftovers.filter((f) => !kept(f.path, f.line, false));
  }
  const unmatched = sites.find((_, i) => !matched.has(i));
  if (unmatched !== undefined) throw new SiteError('refactor.keep-unmatched', unmatched.raw);
  return edits;
}

/** The targets of `specs`, each symbol once: equal intents merge, different ones are a UsageError naming both. */
function resolveAll(r: Refactor, specs: EntrySpec[], map: string): Target[] {
  const targets: Target[] = [];
  for (const spec of specs) {
    const target = resolve(r, spec);
    if (target.literal && literalValueForbidden().some((part) => target.newName.includes(part))) throw new UsageError(message('refactor.literal-value', { value: target.newName }));
    if (spec.retarget !== undefined) {
      const found = resolveRetarget(r, spec, target, spec.retarget);
      target.intent = found.key;
      target.newName = found.name;
    }
    const same = targets.find((t) => t.key === target.key);
    if (same === undefined) targets.push(target);
    else if (same.retarget !== target.retarget || (target.retarget ? same.intent !== target.intent : same.newName !== target.newName)) {
      throw new UsageError(message('refactor.map-duplicate', { map, first: same.index, second: target.index }));
    }
  }
  for (const target of targets.filter((t) => t.retarget)) {
    target.newName = targets.find((t) => !t.retarget && t.key === target.intent)?.newName ?? target.newName;
  }
  return targets;
}

/** A rename target's own declarations; none for a literal member or a retarget. */
function targetDeclarations(r: Refactor, target: Target): TS.Declaration[] {
  const program = r.services(target.file)[0]?.getProgram();
  const source = program?.getSourceFile(target.file);
  if (target.literal || target.retarget || program === undefined || source === undefined) return [];
  const declarations = symbolOf(program.getTypeChecker(), nodeAt(source, target.position))?.declarations ?? [];
  return declarations.filter((d) => !d.getSourceFile().isDeclarationFile);
}

/** RefactorError where two targets give declarations of one scope the same new name, naming the earlier one's
 * first declaration. */
function checkConvergence(r: Refactor, session: Session, targets: Target[]): void {
  const scoped = targets.map((t) => {
    const declarations = targetDeclarations(r, t);
    return { target: t, first: declarations[0], scopes: new Set(declarations.map(scopeOf)) };
  });
  for (const [i, { target, first, scopes }] of scoped.entries()) {
    const converges = scoped.slice(i + 1).some((o) => o.target.newName === target.newName && [...o.scopes].some((s) => scopes.has(s)));
    if (!converges || first === undefined) continue;
    const path = first.getSourceFile().fileName;
    const line = session.lineOf(path, (ts().getNameOfDeclaration(first) ?? first).getStart(first.getSourceFile()));
    throw new RefactorError(message('refactor.name-conflict', { name: target.newName, path: r.rel(path), line }));
  }
}

const print = (lines: string[]): void => {
  process.stderr.write(lines.map((line) => `${line}\n`).join(''));
};

function checkSupported(r: Refactor): void {
  if (r.args.in_hierarchy === false) throw new RefactorError(message('refactor.ts-not-supported', { option: '--no-in-hierarchy' }));
  if (r.args.unsure === 'include') throw new RefactorError(message('refactor.ts-not-supported', { option: '--unsure include' }));
}

/** Each target's language-service edits; the retarget refusals, in position order. */
function targetEdits(r: Refactor, session: Session, targets: Target[]): Finding[] {
  const refusals: Finding[] = [];
  for (const target of targets) {
    target.edits = renameLocations(r.services(target.file), target.file, target.position, target.newName, !target.retarget);
    checkNameConflict(r, session, target);
    if (target.retarget) refusals.push(...retargetEdits(session, target, target.intent));
  }
  return refusals.toSorted(byPosition);
}

/** `SiteError` for the first `--with` or `--without` site no member group's stand-ins hold. */
function classifySites(r: Refactor, groups: NameGroup[]): void {
  const withSites = r.args.with_stand_ins ?? [];
  const withoutSites = r.args.without_stand_ins ?? [];
  const matched = new Set(groups.filter((g) => g.member).flatMap((g) => [...g.classify(withSites, withoutSites)]));
  const stray = [...withSites, ...withoutSites].find((site) => !matched.has(site));
  if (stray !== undefined) throw new SiteError('refactor.not-stand-in', stray);
}

function runRules(groups: NameGroup[], docs: boolean, renamedNames: Set<string>): void {
  for (const group of groups) {
    if (group.member) group.scan();
    if (group.literal) group.equalStrings();
    if (docs) group.docs();
    else group.dropCommentEdits();
    if (group.member && !docs && !group.literal) group.literals();
    if (docs) group.compounds(renamedNames);
    group.dropOwnDeclarations();
  }
}

/** The refusal's lines: blind spots unless allowed, and stand-ins; null when the refactor goes ahead. */
function refusal(groups: NameGroup[], blindspots: Finding[], allowed: boolean): string[] | null {
  const standIns = groups.flatMap((g) => g.standIns).sort(byPosition);
  if ((blindspots.length === 0 || allowed) && standIns.length === 0) return null;
  const attr = groups.filter((g) => g.blindspots.length > 0).map((g) => g.old).join(', .');
  const closing = allowed || blindspots.length === 0 ? [] : [message('refactor.blindspots', { count: blindspots.length, attr })];
  return [...blindspots.map((f) => f.text), ...standIns.map((f) => f.text), ...closing];
}

/** Run `specs` (a rename, a retarget, or a map's entries; `map` in messages) as one refactor: 0, or 1 with the refusal. */
export function runEntries(r: Refactor, specs: EntrySpec[], map: string): number {
  checkSupported(r);
  const targets = resolveAll(r, specs, map);
  const session = new Session(r, targets.map((t) => t.file));
  checkConvergence(r, session, targets);
  const refusals = targetEdits(r, session, targets);
  if (refusals.length > 0) {
    print(refusals.map((f) => f.text));
    return 1;
  }
  checkConflicts(session, targets.flatMap((t) => t.edits.map((e) => ({ ...e, entry: t.index }))));
  const groups = [...new Set(targets.map((t) => t.old))].map((old) => new NameGroup(session, old, targets.filter((t) => t.old === old)));
  classifySites(r, groups);
  runRules(groups, r.args.docs === true, new Set(targets.map((t) => t.old)));
  const edits = keep(session, groups, r.args.keep ?? []);
  const blindspots = groups.flatMap((g) => g.blindspots).sort(byPosition);
  const leftovers = groups.flatMap((g) => g.leftovers).sort(byPosition);
  const refused = refusal(groups, blindspots, r.args.allow_blindspots === true);
  if (refused !== null) {
    print(refused);
    return 1;
  }
  print([...blindspots, ...leftovers].map((f) => f.text));
  checkConflicts(session, edits);
  const headers = targets.map((t) => message(t.retarget ? 'refactor.retarget-header' : 'refactor.rename-header', { old: t.old, new: t.newName }));
  return r.emit(headers, mergeEdits(edits), []);
}
