// `dr-refactor rename`, `retarget` and `rename-map` for TypeScript: every entry resolved first, then each rename
// rule once per old name over one session, one refusal report and one change set.
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import type * as TS from 'typescript';
import { ConfigError, findRepoRoot, loadConfig, sourceFiles } from '../config/index.js';
import { byCodePoint, literalValueForbidden, manifest, message, readFile } from '../contract/index.js';
import { canonical, stripSourceExtension, ts } from '../lang/index.js';
import { configFailures } from './baseline.js';
import { type CheckEntry, identifierText, NameChecks } from './bindings.js';
import { isCompound } from './compound.js';
import { type Edit, mergeEdits, RefactorError, splitBom } from './edits.js';
import { MapError } from './map.js';
import { Lines } from './lines.js';
import { moduleName, moveEdits, takenBy, validModuleName } from './module-rename.js';
import { anyAccesses, type FormCall, formCalls, isAny, type MemberDeclaration, memberDeclarations, memberNameStart, walk } from './members.js';
import { compileForms, formSites, lookup, type OwnerSpan, ownerSpans, topDeclarations } from './mention-scope.js';
import { codeMarked, type Mention, mentions, type Owner, qualified, type Region, sourceRegions } from './mentions.js';
import { blindspotOutcome, compoundOutcome, formCallOutcome, literalOutcomes, mentionOutcome, type Outcome } from './outcomes.js';
import { declarationKeys, type Finding, type Home, keyOf, type Need, planImports, rename, resolveTarget, retargetSites, symbolOf } from './retarget.js';
import { type Progress, type Refusal, refusal, Refused, unique } from './progress.js';
import { languageFiles } from './routing.js';
import { type Locator, locate, nodeAt, type ProjectSource, projectSources, type Refactor, UsageError } from './session.js';
import { keepSpells, LiteralKeeps, literalSpans, Pick, resolveKeeps, Site } from './sites.js';
import { LocatorError } from './symbols.js';
import { timed } from './timings.js';

/** One rename or retarget to compute: its 1-based index, its file (absolute, and as given), locator and intent; a
 * module rename names its module by `file` and has no locator. */
export interface EntrySpec {
  index: number;
  file: string;
  shown: string;
  locator: Locator;
  newName?: string;
  retarget?: string;
  module?: boolean;
}

/** A module rename's file move. */
interface Move {
  from: string;
  to: string;
}

/** An entry resolved against the code: its symbol, old and new name, and the language service's rename locations. */
interface Target {
  index: number;
  /** Every map index merged into this entry. */
  indexes: number[];
  /** A retarget's refusals. */
  refusals: Finding[];
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
  home: Home | null;
  identity: Set<string>;
  original: string;
  /** A module rename's move, else null. */
  move: Move | null;
}

/** An edit with the entry it comes from. */
interface Tagged extends Edit {
  entry: number;
}

const SENTINEL = '\0dr-refactor';
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

/** The module path of a source for qualified mentions: its project-relative path without extension. */
const modulePath = (r: Refactor, path: string): string[] => r.rel(stripSourceExtension(path)).split('/');

/** The project's sources and their texts, read once for every rule of every entry. */
class Session {
  private loaded: Map<string, ProjectSource> | null = null;
  private readonly texts = new Map<string, string>();
  private readonly lines = new Map<string, Lines>();

  constructor(
    readonly r: Refactor,
    private readonly files: string[],
  ) {}

  /** The project's sources, loaded on first use. */
  get sources(): Map<string, ProjectSource> {
    this.loaded ??= timed('load', () => projectSources(this.r, [...new Set(this.files.flatMap((file) => this.r.services(file)))]));
    return this.loaded;
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
      text = this.loaded?.get(path)?.source.text ?? splitBom(readFile(path, 'utf8'))[1];
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

/** An owner of qualified mentions with the new name its declaration takes. */
interface NamedOwner extends Owner {
  newName: string;
}

/** A listed mention, before any keep, with the finding listing it. */
interface Listed {
  path: string;
  start: number;
  end: number;
  finding: Finding;
}

/** The entries renaming one old name: each rule runs once over all of them. */
class NameGroup {
  readonly edits: Tagged[] = [];
  /** Each renamed member declaration's new name. */
  readonly renamed = new Map<string, string>();
  /** Each declaring file with the new names its renamed declarations take. */
  readonly declaring = new Map<string, Set<string>>();
  readonly listed: Listed[] = [];
  /** `--with` sites naming a stand-in declared by a computed name. */
  readonly computed: Refusal[] = [];
  blindspots: Finding[] = [];
  standIns: Finding[] = [];
  leftovers: Finding[] = [];
  /** The sources spelling OLD, or holding a unicode escape that may spell it: the only ones a reference, a string
   * form or a mention can be in. */
  private readonly holding: ProjectSource[];
  private readonly declarations: MemberDeclaration[];
  private readonly examined = new Map<string, [number, number][]>();
  private readonly literalSites = new Map<string, [number, number][]>();
  private readonly owned = new Map<string, OwnerSpan[]>();
  private readonly fileNames = new Map<string, string | null>();
  private readonly entry: number;

  constructor(
    readonly session: Session,
    readonly old: string,
    readonly targets: Target[],
  ) {
    const sources = [...session.sources.values()];
    this.entry = (targets[0] as Target).index;
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

  /** Record an examined site and file what its rule decided, its edits as entry `entry`'s; the finding filed. */
  private record(outcome: Outcome, entry: number = this.entry): Finding | null {
    this.examined.set(outcome.path, [...(this.examined.get(outcome.path) ?? []), [outcome.start, outcome.end]]);
    this.edits.push(...outcome.edits.map((e) => ({ ...e, entry })));
    const pending = outcome.finding;
    if (pending === undefined) return null;
    const found = this.session.finding(outcome.path, pending.position, pending.template, pending.values);
    if (outcome.kind === 'blindspot') this.blindspots.push(found);
    else this.leftovers.push(found);
    return found;
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
      this.computed.push(refusal(message('refactor.computed-stand-in', { ...values, site: raw }), 2));
      classified.add(keyOf(d.path, d.start));
      return;
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
      for (const { position, receiver, literal } of timed('blindspot-scan', () => anyAccesses(checker, source, this.old))) {
        this.record(blindspotOutcome(path, position, literal ?? null, receiver, this.old));
      }
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

  private declares(path: string, newName: string): void {
    this.declaring.set(path, (this.declaring.get(path) ?? new Set()).add(newName));
  }

  private owners(): NamedOwner[] {
    if (!this.member) {
      return this.targets.flatMap((target) => {
        const declarations = this.r.services(target.file)[0]?.getDefinitionAtPosition(target.file, target.position) ?? [];
        const paths = [...new Set(declarations.map((d) => d.fileName))];
        for (const path of paths) this.declares(path, target.newName);
        return paths.map((path) => ({ path: modulePath(this.r, path), member: false, newName: target.newName }));
      });
    }
    return this.declarations.flatMap((d) => {
      const newName = this.renamed.get(keyOf(d.path, d.start));
      if (newName === undefined) return [];
      this.declares(d.path, newName);
      return [{ path: [...modulePath(this.r, d.path), d.owner], member: true, newName }];
    });
  }

  /** The new names the entries give the declaration whose name starts at `start` of `path`. */
  private namesAt(path: string, start: number): Set<string> {
    const names = new Map(this.targets.map((t) => [t.index, t.newName]));
    const found = this.edits.filter((e) => e.path === path && e.start === start).map((e) => names.get(e.entry) ?? '');
    return new Set([...found, ...[this.renamed.get(keyOf(path, start))].filter((n) => n !== undefined)]);
  }

  /** The one new name every one of `sites` (a path and a name start) is renamed to, else null. */
  private oneName(sites: [string, number][]): string | null {
    const all = new Set<string>();
    for (const [path, start] of sites) {
      const names = this.namesAt(path, start);
      if (names.size === 0) return null;
      for (const name of names) all.add(name);
    }
    return all.size === 1 ? ([...all][0] ?? null) : null;
  }

  private siteOf(d: TS.Declaration): [string, number] {
    const file = d.getSourceFile();
    const name = ts().getNameOfDeclaration(d);
    return [file.fileName, name === undefined ? d.getStart(file) : (memberNameStart(name, this.old, file) ?? name.getStart(file))];
  }

  /** The one name every module-level and member declaration of OLD in `source` is renamed to; with no such
   * declaration, the one name of the entries declaring in it. */
  private fileName(source: TS.SourceFile): string | null {
    const path = source.fileName;
    if (!this.fileNames.has(path)) {
      const sites: [string, number][] = [
        ...topDeclarations(source, this.old).map((start): [string, number] => [path, start]),
        ...this.declarations.filter((d) => d.path === path).map((d): [string, number] => [path, d.start]),
      ];
      const declared = this.declaring.get(path) ?? new Set();
      const fallback = declared.size === 1 ? ([...declared][0] ?? null) : null;
      this.fileNames.set(path, sites.length > 0 ? this.oneName(sites) : fallback);
    }
    return this.fileNames.get(path) ?? null;
  }

  /** The new name a code-marked mention at `position` of a declaring source takes by its owning class, else by its
   * file; null when it is listed. */
  private ownedName(found: ProjectSource, position: number): string | null {
    const { source, checker } = found;
    if (!this.owned.has(source.fileName)) this.owned.set(source.fileName, ownerSpans(source));
    const enclosing = (this.owned.get(source.fileName) ?? [])
      .filter((span) => span.start <= position && position < span.end)
      .sort((a, b) => a.end - a.start - (b.end - b.start));
    for (const { node } of enclosing) {
      const landed = lookup(checker, node, this.old);
      if (landed === 'incomplete') return null;
      if (landed !== null) return this.oneName(landed.map((d) => this.siteOf(d)));
    }
    return this.fileName(source);
  }

  /** Each scanned file's mentions of OLD: sources, then prose files. */
  private mentionFiles(): [string, Mention[]][] {
    const files: [string, Mention[]][] = [];
    for (const { source } of this.holding) files.push([source.fileName, mentions(source.text, this.old, sourceRegions(source))]);
    const extensions: string[] = manifest()['dr-refactor'].prose_extensions;
    for (const rel of sourceFiles(this.r.root, []).sort(byCodePoint)) {
      const path = join(this.r.root, rel);
      if (!extensions.some((ext) => rel.endsWith(ext)) || !existsSync(path)) continue;
      const text = this.session.text(path);
      if (text.includes(this.old)) files.push([path, mentions(text, this.old, [{ start: 0, end: text.length, where: 'prose' }])]);
    }
    return files;
  }

  /** File a mention: rewritten to `newName` as the first entry taking that name, listed when null. */
  private decide(path: string, mention: Mention, newName: string | null): void {
    const entry = this.targets.find((t) => t.newName === newName)?.index ?? this.entry;
    const finding = this.record(mentionOutcome(path, mention, newName !== null, this.old, newName ?? ''), entry);
    if (finding !== null) this.listed.push({ path, start: mention.start, end: mention.end, finding });
  }

  /** Each declared string form's site of a class or module-level rename: rewritten when every module-level
   * declaration of OLD in the project is renamed to one name, else listed. */
  forms(forms: RegExp[]): void {
    if (forms.length === 0) return;
    const declared = this.holding.flatMap(({ source }) => topDeclarations(source, this.old).map((start): [string, number] => [source.fileName, start]));
    if (!declared.some(([path, start]) => this.namesAt(path, start).size > 0)) return;
    const newName = this.oneName(declared);
    for (const { source } of this.holding) {
      const path = source.fileName;
      const sites = sourceRegions(source).flatMap((region) => formSites(source.text, region, this.old, forms));
      const seen = new Set<number>();
      for (const [start, end] of sites.sort((a, b) => a[0] - b[0])) {
        if (seen.has(start) || this.covered(path, start, end)) continue;
        seen.add(start);
        this.literalSites.set(path, [...(this.literalSites.get(path) ?? []), [start, end]]);
        this.decide(path, { start, end, where: 'string' }, newName);
      }
    }
  }

  /** `--docs`: each mention rewritten for one entry (qualified, or code-marked and decided by its owning class or
   * its file), else listed. */
  docs(): void {
    const owners = this.owners();
    const names = [...new Set(owners.map((o) => o.newName))];
    const colliding = this.declarations
      .filter((d) => !this.renamed.has(keyOf(d.path, d.start)))
      .map((d) => [...modulePath(this.r, d.path), d.owner]);
    for (const [path, found] of this.mentionFiles()) {
      const text = this.session.text(path);
      const source = this.declaring.has(path) ? this.session.sources.get(path) : undefined;
      for (const m of found) {
        if (this.handled(path, m.start)) continue;
        const qualifying = names.filter((name) => qualified(text, m.start, owners.filter((o) => o.newName === name), colliding));
        this.decide(path, m, this.mentionName(qualifying, source, text, m));
      }
    }
  }

  /** The name a mention takes: the one qualifying name, else a code-marked mention's owned name; null when listed. */
  private mentionName(qualifying: string[], source: ProjectSource | undefined, text: string, m: Mention): string | null {
    if (qualifying.length > 0) return qualifying.length === 1 ? (qualifying[0] ?? null) : null;
    return source !== undefined && codeMarked(text, m) ? this.ownedName(source, m.start) : null;
  }

  /** Whether an edit or a form site already covers `start`. */
  private handled(path: string, start: number): boolean {
    if (this.edits.some((e) => e.path === path && e.start <= start && start < e.start + e.length)) return true;
    return (this.literalSites.get(path) ?? []).some(([s, e]) => s <= start && start < e);
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

/** `spec` resolved: the symbol its locator names, and what can be renamed there. */
function resolve(r: Refactor, spec: EntrySpec): Target {
  const located = locate(r, spec.file, spec.shown, spec.locator, spec.retarget === undefined);
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
  const reexport = spec.retarget !== undefined && (ts().isImportSpecifier(node.parent) || ts().isExportSpecifier(node.parent));
  const key = (reexport ? undefined : declarationKeys(symbol, old)[0]) ?? keyOf(file, info.triggerSpan.start);
  return { index: spec.index, indexes: [spec.index], refusals: [], retarget: spec.retarget !== undefined, file, position, old, newName: spec.newName ?? '', key, literal, intent: key, edits: [], own: new Set(), home: null, identity: new Set(), original: '', move: null };
}

/** `spec` as a module rename: its file moved to its new stem beside itself, keeping its extension. */
function resolveModule(r: Refactor, spec: EntrySpec): Target {
  const { file } = spec;
  r.owner(file);
  const newName = spec.newName ?? '';
  if (!validModuleName(newName)) throw new RefactorError(message('refactor.cannot-rename'));
  const { stem, extension } = moduleName(file);
  const key = `module\0${canonical(file)}`;
  const move = { from: file, to: join(dirname(file), `${newName}${extension}`) };
  return { index: spec.index, indexes: [spec.index], refusals: [], retarget: false, file, position: 0, old: stem, newName, key, literal: false, intent: key, edits: [], own: new Set(), home: null, identity: new Set(), original: '', move };
}

/** A `refactor.map-conflict` for each site two entries rewrite differently; identical edits are one. */
function mapConflicts(session: Session, edits: Tagged[]): Refusal[] {
  const sorted = edits.toSorted((a, b) => byCodePoint(a.path, b.path) || a.start - b.start);
  const out: Refusal[] = [];
  for (const [i, a] of sorted.entries()) {
    for (let j = i + 1; j < sorted.length; j += 1) {
      const b = sorted[j] as Tagged;
      if (b.path !== a.path || b.start >= a.start + Math.max(a.length, 1)) break;
      const same = b.start === a.start && b.length === a.length && b.newText === a.newText;
      if (same || a.entry === b.entry) continue;
      const [first, second] = [Math.min(a.entry, b.entry), Math.max(a.entry, b.entry)];
      const line = session.lineOf(a.path, a.start);
      out.push(refusal(message('refactor.map-conflict', { path: session.r.rel(a.path), line, first, second })));
      break;
    }
  }
  return unique(out);
}

/** `--keep` sites: what they keep, and those that kept nothing. */
class Keeps {
  private readonly sites: Site[];
  private readonly matched = new Set<number>();

  constructor(
    private readonly session: Session,
    raws: string[],
  ) {
    this.sites = raws.map((raw) => Site.parse(raw, session.r.root));
  }

  /** `rel:line` is kept; `mark` counts the keeps it matches. */
  kept(rel: string, line: number, mark = true): boolean {
    const hits = this.sites.flatMap((site, i) => (site.covers(rel, line) ? [i] : []));
    if (mark) for (const i of hits) this.matched.add(i);
    return hits.length > 0;
  }

  /** A whole-file or directory keep covers `path`; marks the keeps it matches. */
  keepsFile(path: string): boolean {
    const rel = this.session.r.rel(path);
    const hits = this.sites.flatMap((site, i) => (site.line === null && site.coversPath(rel) ? [i] : []));
    for (const i of hits) this.matched.add(i);
    return hits.length > 0;
  }

  /** The edit at `position` of `path` is on a kept line. */
  keeps(path: string, position: number): boolean {
    return this.kept(this.session.r.rel(path), this.session.lineOf(path, position));
  }

  /** Every keep that matched nothing, in command-line order. */
  unmatched(): Site[] {
    return this.sites.filter((_, i) => !this.matched.has(i));
  }
}

/** The edit is on a kept line or in a kept literal; both count it. */
function keptEdit(e: Edit, keeps: Keeps, literals: LiteralKeeps): boolean {
  const line = keeps.keeps(e.path, e.start);
  return literals.kept(e.path, e.start, e.start + e.length) || line;
}

/** Drop every edit, blind spot and leftover of `group` at a kept site or in a kept literal. */
function keep(group: NameGroup, keeps: Keeps, literals: LiteralKeeps): void {
  const root = group.session.r.root;
  const inLiteral = (f: Finding, mark: boolean): boolean => literals.kept(join(root, f.path), f.position, f.position + 1, mark);
  const kept = group.edits.filter((e) => !keptEdit(e, keeps, literals));
  group.edits.splice(0, group.edits.length, ...kept);
  group.blindspots = group.blindspots.filter((b) => !keeps.kept(b.path, b.line) && !inLiteral(b, true));
  group.leftovers = group.leftovers.filter((f) => !keeps.kept(f.path, f.line, false) && !inLiteral(f, false));
}

/** `refactor.pick-ambiguous` for `pick` between entries `a` and `b`. */
const ambiguous = (pick: Pick, old: string, a: number, b: number): Refusal =>
  refusal(message('refactor.pick-ambiguous', { site: pick.raw, first: Math.min(a, b), second: Math.max(a, b), old }), 2);

/** Each listed mention `pick` rewrites with the entry whose new name it takes; its refusal when it names none, or one
 * two entries rename differently. */
function pickChoices(session: Session, pick: Pick, listed: [Listed, NameGroup][]): [Listed, NameGroup, Target][] | Refusal {
  const out: [Listed, NameGroup, Target][] = [];
  for (const [m, group] of listed) {
    if (!pick.site.covers(session.r.rel(m.path), m.finding.line)) continue;
    const targets = pick.entry === null ? group.targets : group.targets.filter((t) => t.indexes.includes(pick.entry ?? 0));
    const [first] = targets;
    if (first === undefined) continue;
    const other = targets.find((t) => t.newName !== first.newName);
    if (other !== undefined) return ambiguous(pick, group.old, first.index, other.index);
    out.push([m, group, first]);
  }
  return out.length > 0 ? out : refusal(message('refactor.pick-unmatched', { site: pick.raw }), 2);
}

/** Each `--docs-pick` applied to the listed mentions of its line no edit covers, as an edit of the chosen entry unless
 * its site is kept, the mention no longer listed; every pick's refusal, in pick order. */
function resolvePicks(session: Session, groups: NameGroup[], raws: string[], keeps: Keeps, literals: LiteralKeeps): Refusal[] {
  if (raws.length === 0) return [];
  const edits = groups.flatMap((g) => g.edits);
  const covered = (m: Listed): boolean => edits.some((e) => e.path === m.path && e.start < m.end && m.start < e.start + e.length);
  const listed = groups.flatMap((g) => g.listed.filter((m) => !covered(m)).map((m): [Listed, NameGroup] => [m, g]));
  const chosen = new Map<Listed, [NameGroup, Target]>();
  const refusals: Refusal[] = [];
  for (const raw of raws) {
    const pick = Pick.parse(raw, session.r.root);
    const found = pickChoices(session, pick, listed);
    if (!Array.isArray(found)) {
      refusals.push(found);
      continue;
    }
    for (const [m, group, target] of found) {
      const before = chosen.get(m)?.[1] ?? target;
      chosen.set(m, [group, before]);
      if (before.newName === target.newName) continue;
      refusals.push(ambiguous(pick, group.old, before.index, target.index));
      break;
    }
  }
  if (refusals.length > 0) return refusals;
  for (const [m, [group, target]] of chosen) {
    group.leftovers = group.leftovers.filter((f) => f !== m.finding);
    const edit = { path: m.path, start: m.start, length: m.end - m.start, newText: target.newName, entry: target.index };
    if (!keptEdit(edit, keeps, literals)) group.edits.push(edit);
  }
  return [];
}

/** The finding of an error that refuses one entry. */
export function entryFailure(error: unknown): Refusal {
  if (error instanceof LocatorError || error instanceof UsageError || error instanceof MapError) return refusal(error.message, 2);
  if (error instanceof RefactorError) return refusal(error.message);
  throw error;
}

/** The name an entry's locator spells: the last word of its symbol path. */
const spelledName = (spec: EntrySpec): string | null => spec.locator.symbol?.match(/\w+/gu)?.at(-1) ?? null;

interface Resolution {
  targets: Target[];
  failures: Refusal[];
  /** Every entry that failed spells a name. */
  spelled: boolean;
  names: Set<string>;
}

/** `spec`'s target, its literal value and retarget checked. */
function resolveEntry(r: Refactor, spec: EntrySpec): Target {
  if (spec.module === true) return resolveModule(r, spec);
  const target = resolve(r, spec);
  if (target.literal && literalValueForbidden().some((part) => target.newName.includes(part))) throw new UsageError(message('refactor.literal-value', { value: target.newName }));
  if (spec.retarget !== undefined) target.intent = resolveTarget(r, spec.file, spec.locator, spec.shown, target, spec.retarget);
  return target;
}

/** `target` added to `targets`, or merged into the one with its key and equal intent; else `refactor.map-duplicate`. */
function mergeTarget(targets: Target[], target: Target, map: string): Refusal | null {
  const same = targets.find((t) => t.key === target.key);
  if (same === undefined) targets.push(target);
  else if (same.retarget !== target.retarget || (target.retarget ? same.intent !== target.intent : same.newName !== target.newName)) {
    return refusal(message('refactor.map-duplicate', { map, first: same.index, second: target.index }), 2);
  } else same.indexes.push(target.index);
  return null;
}

/** The targets of `specs`, each symbol once, searching no reference: equal intents merge, different ones are refused
 * naming both; each failure in entry order. */
function resolveAll(r: Refactor, specs: EntrySpec[], map: string): Resolution {
  const targets: Target[] = [];
  const failures: Refusal[] = [];
  const names = new Set<string>();
  let spelled = true;
  for (const spec of specs) {
    let target: Target;
    try {
      target = resolveEntry(r, spec);
    } catch (error) {
      failures.push(entryFailure(error));
      const name = spelledName(spec);
      if (name === null) spelled = false;
      else names.add(name);
      continue;
    }
    names.add(target.old);
    if (spec.retarget !== undefined) names.add(spec.retarget.match(/\w+/gu)?.at(-1) ?? '');
    const duplicate = mergeTarget(targets, target, map);
    if (duplicate !== null) failures.push(duplicate);
  }
  for (const target of targets.filter((t) => t.retarget)) {
    const final = targets.find((t) => !t.retarget && t.key === target.intent)?.newName;
    if (final !== undefined) rename(target, final);
  }
  names.delete('');
  return { targets, failures, spelled, names };
}

/** The files a rename can edit: each TypeScript source (true), and with `docs` each prose file (false). */
function editableFiles(r: Refactor, docs: boolean): Map<string, boolean> {
  const out = new Map(languageFiles(r.root, 'typescript').map((path): [string, boolean] => [r.rel(path), true]));
  if (!docs) return out;
  const extensions: string[] = manifest()['dr-refactor'].prose_extensions;
  for (const rel of sourceFiles(r.root, []).sort(byCodePoint)) if (extensions.some((ext) => rel.endsWith(ext)) && !out.has(rel)) out.set(rel, false);
  return out;
}

/** Every check that needs no reference: each site naming something, no `--stand-in` site when every entry renames a
 * module, no `--stub` (it moves only Python modules), each line keep spelling an old name (in a comment only with
 * `--docs`) or lying in a moved file, each module's new name free beside it. */
function checks(r: Refactor, resolution: Resolution): Refusal[] {
  const sites: [string, string, string][] = [
    ...(r.args.with_stand_ins ?? []).map((raw): [string, string, string] => ['--with', raw, r.root]),
    ...(r.args.without_stand_ins ?? []).map((raw): [string, string, string] => ['--without', raw, r.root]),
    ...(r.args.keep ?? []).map((raw): [string, string, string] => ['--keep', raw, process.cwd()]),
    ...(r.args.docs === true ? (r.args.docs_pick ?? []) : []).map((raw): [string, string, string] => ['--docs-pick', raw, process.cwd()]),
  ];
  const { refusals: out, missing } = missingSites(r, sites);
  if ((r.args.docs_pick ?? []).length > 0 && r.args.docs !== true) out.push(refusal(message('refactor.pick-needs-docs'), 2));
  const { targets } = resolution;
  if (targets.length > 0 && targets.every((t) => t.move !== null)) {
    for (const [option, raw] of sites) {
      if ((option === '--with' || option === '--without') && !missing.has(`${option}\0${raw}`)) out.push(refusal(message('refactor.not-stand-in', { site: raw }), 2));
    }
  }
  if (r.args.stub != null) out.push(refusal(message('refactor.stub-not-module'), 2));
  out.push(...keepChecks(r, resolution, (raw) => missing.has(`--keep\0${raw}`)), ...takenNames(r, targets));
  return out;
}

/** `refactor.site-missing` for each site naming nothing, and those sites' `option\0raw` keys. */
function missingSites(r: Refactor, sites: [string, string, string][]): { refusals: Refusal[]; missing: Set<string> } {
  const refusals: Refusal[] = [];
  const missing = new Set<string>();
  for (const [option, raw, base] of sites) {
    const site = option === '--docs-pick' ? Pick.parse(raw, r.root, base) : Site.parse(raw, r.root, base);
    if (!site.missing(r.root)) continue;
    refusals.push(refusal(message('refactor.site-missing', { option, site: raw }), 2));
    missing.add(`${option}\0${raw}`);
  }
  return { refusals, missing };
}

/** `refactor.name-conflict` for each module move whose new name a sibling already takes. */
function takenNames(r: Refactor, targets: Target[]): Refusal[] {
  return targets.flatMap((t) => {
    const taken = t.move === null || t.newName === t.old ? null : takenBy(t.file, t.newName);
    return taken === null ? [] : [refusal(message('refactor.name-conflict', { name: t.newName, path: r.rel(taken), line: 1 }))];
  });
}

/** `refactor.keep-unmatched` for each line keep on a line spelling no old name, outside every moved file. */
function keepChecks(r: Refactor, resolution: Resolution, missing: (raw: string) => boolean): Refusal[] {
  const keeps = (r.args.keep ?? []).filter((raw) => !missing(raw) && Site.parse(raw, r.root).line !== null);
  if (!resolution.spelled || keeps.length === 0 || resolution.targets.some((t) => t.literal)) return [];
  const docs = r.args.docs === true;
  const editable = editableFiles(r, docs);
  const texts = new Map<string, string>();
  const text = (rel: string): string => {
    let found = texts.get(rel);
    if (found === undefined) {
      found = splitBom(readFile(join(r.root, rel), 'utf8'))[1];
      texts.set(rel, found);
    }
    return found;
  };
  const moved = resolution.targets.flatMap((t) => (t.move === null ? [] : [r.rel(t.move.from)]));
  return keeps
    .filter((raw) => !keepSpells(Site.parse(raw, r.root), editable, text, resolution.names, moved, docs))
    .map((raw) => refusal(message('refactor.keep-unmatched', { site: raw }), 2));
}

function checkSupported(r: Refactor): void {
  if (r.args.in_hierarchy === false) throw new RefactorError(message('refactor.ts-not-supported', { option: '--no-in-hierarchy' }));
  if (r.args.unsure === 'include') throw new RefactorError(message('refactor.ts-not-supported', { option: '--unsure include' }));
}

function runRules(group: NameGroup, docs: boolean, renamedNames: Set<string>, forms: RegExp[]): void {
  if (group.member) group.scan();
  if (group.literal) group.equalStrings();
  group.forms(forms);
  if (docs) group.docs();
  else group.dropCommentEdits();
  if (group.member && !docs && !group.literal) group.literals();
  if (docs) group.compounds(renamedNames);
  group.dropOwnDeclarations();
}

/** Each module move whose new stem an earlier move takes in its directory, naming the earlier one's file at line 1. */
function convergingMoves(session: Session, moves: Target[]): { path: string; line: number; name: string }[] {
  const first = new Map<string, Target>();
  const out: { path: string; line: number; name: string }[] = [];
  for (const t of moves) {
    const key = `${dirname(t.file)}\0${t.newName}`;
    const earlier = first.get(key);
    if (earlier === undefined) first.set(key, t);
    else out.push({ path: session.r.rel(earlier.file), line: 1, name: t.newName });
  }
  return out;
}

/** A `refactor.name-conflict` for the first site of each check that finds one: each rename entry's edits alone, in map
 * order, then, when `together`, all entries' and every module move's. */
function nameConflicts(session: Session, targets: Target[], pending: Tagged[], edits: Tagged[], together: boolean, moves: Target[]): Refusal[] {
  const found: { path: string; line: number; name: string }[] = together ? convergingMoves(session, moves) : [];
  if (targets.length === 0) return found.map((c) => refusal(message('refactor.name-conflict', c)));
  const done = new Set(edits.map((e) => keyOf(e.path, e.start)));
  const kept = new Set(pending.map((e) => keyOf(e.path, e.start)).filter((k) => !done.has(k)));
  const entries: CheckEntry[] = targets.map((t) => ({ index: t.index, old: t.old, newName: t.newName, expected: t.retarget ? t.identity : null }));
  const names = targets.flatMap((t) => [t.old, t.newName, ...(t.retarget ? [t.original] : [])]).map((name) => identifierText(name));
  const checks = new NameChecks(session.sources, names, (path) => session.r.rel(path));
  const passes = entries.filter((e) => e.expected === null && e.newName !== e.old).map((e) => [e]);
  if (entries.length > 1 && together) passes.push(entries);
  for (const pass of passes) {
    const conflict = checks.check(pass, edits, kept);
    if (conflict !== null) found.push({ path: session.r.rel(conflict.path), line: session.lineOf(conflict.path, conflict.position), name: conflict.name });
  }
  found.sort((a, b) => byCodePoint(a.path, b.path) || a.line - b.line || byCodePoint(a.name, b.name));
  return unique(found.map((c) => refusal(message('refactor.name-conflict', c))));
}

const texts = (findings: Finding[]): Refusal[] => {
  const seen = new Set<string>();
  return findings
    .toSorted(byPosition)
    .filter((f) => {
      const key = `${f.path}\0${f.line}\0${f.position}\0${f.text}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((f) => refusal(f.text));
};

/** Site resolution over the final `edits`: each `--with` or `--without` site of `unclassified`, each computed `--with`
 * stand-in, then the refused `picks`; with none of those, each unneeded whole-path keep's and literal keep's warning
 * printed, and each line keep that matched nothing. */
function resolveSites(session: Session, edits: Tagged[], keeps: Keeps, literals: LiteralKeeps, unclassified: string[], groups: NameGroup[], picks: Refusal[]): Refusal[] {
  const standIns = [...unclassified.map((site) => refusal(message('refactor.not-stand-in', { site }), 2)), ...groups.flatMap((g) => g.computed)];
  if (picks.length > 0) return [...standIns, ...picks];
  const edited = new Map<string, number[]>();
  for (const e of edits) {
    const rel = session.r.rel(e.path);
    const lines = edited.get(rel) ?? [];
    lines.push(session.lineOf(e.path, e.start));
    edited.set(rel, lines);
  }
  const { warnings, refusals } = resolveKeeps(keeps.unmatched(), edited);
  process.stderr.write([...warnings, ...literals.unneeded()].map((w) => `${w}\n`).join(''));
  return [...standIns, ...refusals];
}

/** The repo's `refactor.string_forms`, compiled; the config's error. */
function stringForms(r: Refactor): { forms: RegExp[]; failures: Refusal[] } {
  try {
    return { forms: compileForms(loadConfig(findRepoRoot(r.root)).refactor.string_forms), failures: [] };
  } catch (error) {
    if (error instanceof ConfigError) return { forms: [], failures: [refusal(error.message, 2)] };
    throw error;
  }
}

/** Run `specs` (a rename, a retarget, or a map's entries; `map` in messages) as one refactor, its phases announced
 * on `progress`: 0, or `Refused` with every refusal. */
export function runEntries(r: Refactor, specs: EntrySpec[], map: string, progress: Progress): number {
  checkSupported(r);
  const failFast = r.args.fail_fast === true;
  const allowed = r.args.allow_blindspots === true;
  progress.phase('resolve');
  const resolution = timed('resolve', () => resolveAll(r, specs, map));
  progress.phase('checks');
  const { forms, failures: formFailures } = stringForms(r);
  const told = new Set(formFailures.flatMap((f) => f.lines));
  const failures = [...resolution.failures, ...checks(r, resolution), ...formFailures, ...configFailures(r).filter((f) => !f.lines.some((line) => told.has(line)))];
  if (failures.length > 0) throw new Refused(failures);
  const { targets } = resolution;
  const symbols = targets.filter((t) => t.move === null);
  progress.phase('references');
  const session = new Session(r, symbols.map((t) => t.file));
  const keeps = new Keeps(session, r.args.keep ?? []);
  const literals = new LiteralKeeps(r.args.keep_literal ?? [], (path, keys) => {
    const source = session.sources.get(path)?.source;
    return source === undefined ? [] : literalSpans(source, keys);
  });
  const keptSite = (path: string, position: number): boolean => keptEdit({ path, start: position, length: 1, newText: '' }, keeps, literals);
  const needs: Need[] = [];
  for (const [i, target] of targets.entries()) {
    progress.item(i + 1, targets.length, target.indexes, target.old, target.newName);
    timed('references', () => {
      const { move } = target;
      if (move !== null) {
        if (target.newName !== target.old) target.edits = moveEdits(r, move.from, move.to, [[move.from, move.to]], [move.from]);
        return;
      }
      target.edits = renameLocations(r.services(target.file), target.file, target.position, target.newName, !target.retarget);
      if (target.retarget) target.refusals = retargetSites(session, target, keptSite, needs);
    });
  }
  const olds = [...new Set(symbols.map((t) => t.old))];
  if (olds.length > 0) progress.phase('rules');
  const renamedNames = new Set(olds);
  const withSites = r.args.with_stand_ins ?? [];
  const withoutSites = r.args.without_stand_ins ?? [];
  const matched = new Set<string>();
  const groups: NameGroup[] = [];
  const pending: Tagged[] = [];
  let stopped = false;
  for (const [n, old] of olds.entries()) {
    const members = symbols.filter((t) => t.old === old);
    const group = timed('rules', () => {
      const named = new NameGroup(session, old, members);
      if (named.member) for (const site of named.classify(withSites, withoutSites)) matched.add(site);
      runRules(named, r.args.docs === true, renamedNames, forms);
      return named;
    });
    pending.push(...group.edits);
    keep(group, keeps, literals);
    groups.push(group);
    const refused = texts([...members.flatMap((t) => t.refusals), ...(allowed ? [] : group.blindspots), ...group.standIns]);
    const indexes = members.flatMap((t) => t.indexes).toSorted((a, b) => a - b);
    const newNames = [...new Set(members.map((t) => t.newName))].join(', ');
    progress.result(n + 1, olds.length, indexes, old, newNames, refused.flatMap((f) => f.lines));
    if (refused.length > 0 && failFast) {
      stopped = true;
      break;
    }
  }
  const moving = targets.filter((t) => t.move !== null && t.newName !== t.old && !keeps.keepsFile(t.file));
  const moduleEdits = targets
    .filter((t) => t.move !== null)
    .flatMap((t) => t.edits.map((e) => ({ ...e, entry: t.index })))
    .filter((e) => !keptEdit(e, keeps, literals));
  const retargets = texts(targets.flatMap((t) => t.refusals));
  const blindspots = groups.flatMap((g) => g.blindspots).sort(byPosition);
  const blind = allowed ? [] : texts(blindspots);
  const standIns = texts(groups.flatMap((g) => g.standIns));
  let edits: Tagged[] = [];
  let conflicts: Refusal[] = [];
  let sites: Refusal[] = [];
  if (!stopped) {
    const picks = resolvePicks(session, groups, r.args.docs_pick ?? [], keeps, literals);
    edits = [...groups.flatMap((g) => g.edits), ...planImports(session, needs), ...moduleEdits];
    sites = resolveSites(session, edits, keeps, literals, [...withSites, ...withoutSites].filter((site) => !matched.has(site)), groups, picks);
  }
  if (!stopped && sites.length === 0) {
    progress.phase('conflicts');
    conflicts = timed('conflicts', () => {
      const merged = mapConflicts(session, edits);
      return [...nameConflicts(session, symbols, pending, edits, merged.length === 0, moving), ...merged];
    });
  }
  const attr = groups.filter((g) => g.blindspots.length > 0).map((g) => g.old).join(', .');
  const closing = blind.length > 0 ? [refusal(message('refactor.blindspots', { count: blind.length, attr }))] : [];
  const report = unique([...retargets, ...blind, ...standIns, ...conflicts, ...sites, ...closing]);
  if (report.length > 0) throw new Refused(report);
  const leftovers = groups.flatMap((g) => g.leftovers).sort(byPosition);
  process.stderr.write([...blindspots, ...leftovers].map((f) => `${f.text}\n`).join(''));
  const headers = targets.map((t) => message(t.retarget ? 'refactor.retarget-header' : 'refactor.rename-header', { old: t.old, new: t.newName }));
  const moves = moving.flatMap((t): [string, string][] => (t.move === null ? [] : [[t.move.from, t.move.to]]));
  return r.emit(headers, mergeEdits(edits), moves, [], progress);
}
