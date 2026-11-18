// `dr-refactor rename`, `retarget` and `rename-map` for TypeScript: every entry resolved first, then each rename
// rule once per old name over one session, one refusal report and one change set.
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import type * as TS from 'typescript';
import { sourceFiles } from '../config/index.js';
import { byCodePoint, literalValueForbidden, manifest, message, readFile } from '../contract/index.js';
import { canonical, stripSourceExtension, ts } from '../lang/index.js';
import { configFailures } from './baseline.js';
import { type CheckEntry, identifierText, NameChecks } from './bindings.js';
import { isCompound } from './compound.js';
import { type Edit, mergeEdits, RefactorError, splitBom } from './edits.js';
import { MapError } from './map.js';
import { Lines } from './lines.js';
import { moduleName, moveEdits, takenBy, validModuleName } from './module-rename.js';
import { displayHolds, type LiteralSource, literalSources, sourceReads } from './literal-sources.js';
import { anyAccesses, anyNamed, isAny, type MemberDeclaration, memberDeclarations, memberNameStart, type NamedAccess, namedAccesses, plainString, walk } from './members.js';
import { codeMarked, type Mention, mentions, type Owner, qualified, type Region, sourceRegions } from './mentions.js';
import {
  blindspotOutcome,
  compoundOutcome,
  formCallOutcome,
  literalOutcomes,
  mentionOutcome,
  mixedOutcome,
  type Outcome,
  sourceOutcome,
  unrelatedOutcome,
  unresolvedOutcome,
} from './outcomes.js';
import { type AddedError, addedErrors } from './program-check.js';
import { declarationKeys, type Finding, type Home, keyOf, type Need, planImports, rename, resolveTarget, retargetSites, symbolOf } from './retarget.js';
import { type Progress, type Refusal, refusal, Refused, unique } from './progress.js';
import { languageFiles } from './routing.js';
import { type Locator, locate, nodeAt, type ProjectSource, projectSources, type Refactor, UsageError } from './session.js';
import { keepSpells, resolveKeeps, Site } from './sites.js';
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

/** A name in the member position of a string-named access: the sources it holds that spell OLD, the new name of each
 * declaration its object's lookup lands on (null: unchanged; none for an untyped object), and its read. */
interface NameUse {
  path: string;
  position: number;
  start: number;
  end: number;
  receiver: string;
  sources: LiteralSource[];
  landings: (string | null)[];
}

/** A source this rename rewrites, and the reads that prove it names what is renamed. */
interface Rewritten {
  source: LiteralSource;
  proven: Set<string>;
}

/** A name another site already takes. */
type Taken = { path: string; line: number; name: string };

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

/** The entries renaming one old name: each rule runs once over all of them. */
class NameGroup {
  readonly edits: Tagged[] = [];
  /** Each renamed member declaration's new name. */
  readonly renamed = new Map<string, string>();
  readonly declaring = new Set<string>();
  /** `--with` sites naming a stand-in declared by a computed name. */
  readonly computed: Refusal[] = [];
  blindspots: Finding[] = [];
  /** Each rewritten source, by its key. */
  private readonly rewritten = new Map<string, Rewritten>();
  /** Each rewritten source whose display already holds the new name, by the source's key. */
  private readonly taken = new Map<string, Taken>();
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

  /** Member strings and the sources of member names landing only on declarations renamed to one name are rewritten;
   * `any` receivers and those landing on renamed and unchanged declarations are blind spots. */
  scan(): void {
    const holding = new Set(this.holding);
    const uses: NameUse[] = [];
    for (const found of this.session.sources.values()) {
      const { source, checker } = found;
      const path = source.fileName;
      if (holding.has(found)) {
        for (const { position, receiver } of timed('blindspot-scan', () => anyAccesses(checker, source, this.old))) {
          this.record(blindspotOutcome(path, position, null, receiver, this.old));
        }
      }
      for (const access of namedAccesses(checker, source)) {
        if (plainString(access.member, source) === null) uses.push(...this.nameUse(found, access));
        else this.namedLiteral(found, access);
      }
    }
    this.followUses(uses);
  }

  /** A string-named access of OLD by a literal: a blind spot on an `any` object, else a call form's by its landings
   * (the language service renames a typed element access). */
  private namedLiteral({ source, checker }: ProjectSource, access: NamedAccess): void {
    const literal = plainString(access.member, source);
    if (literal?.[2] !== this.old) return;
    const path = source.fileName;
    const spot = anyNamed(checker, source, access, this.old);
    if (spot?.site !== undefined) {
      this.record(blindspotOutcome(path, spot.position, [literal[0], literal[1]], spot.receiver, this.old, { site: spot.site, silent: spot.silent === true }));
    } else if (ts().isCallExpression(access.access)) {
      const names = this.landings(checker, access.object);
      const distinct = new Set(names.filter((n) => n !== null));
      const renamed = distinct.size > 1 ? [true, false] : names.map((n) => n !== null);
      const call = { call: access.access, start: literal[0], end: literal[1], object: access.object };
      this.record(formCallOutcome(path, call, renamed, access.object.getText(source), this.old, [...distinct][0] ?? ''));
    }
  }

  /** `access` when a name with a source spelling OLD stands for its member. */
  private nameUse({ source, checker, service }: ProjectSource, access: NamedAccess): NameUse[] {
    const sources = literalSources(service, access.member).filter((s) => s.text === this.old && this.session.sources.has(s.path));
    if (sources.length === 0) return [];
    const landings = isAny(checker, access.object) ? [] : this.landings(checker, access.object);
    const [start, end] = [access.member.getStart(source), access.member.end];
    return [{ path: source.fileName, position: access.access.getStart(source), start, end, receiver: access.object.getText(source), sources, landings }];
  }

  /** Each source of `uses`: rewritten when its uses land only on declarations renamed to one name, left unlisted when
   * only on unchanged ones, and every landing use a mixed-target blind spot when on both. */
  private followUses(uses: NameUse[]): void {
    const bySource = new Map<string, [LiteralSource, NameUse[]]>();
    for (const use of uses) {
      for (const source of use.sources) {
        const key = keyOf(source.path, source.start);
        bySource.set(key, [source, [...(bySource.get(key)?.[1] ?? []), use]]);
      }
    }
    for (const [source, found] of bySource.values()) {
      const landing = found.filter((use) => use.landings.length > 0);
      const names = landing.flatMap((use) => use.landings);
      const distinct = [...new Set(names.filter((n) => n !== null))];
      const [newName] = distinct;
      if (names.length === 0) continue;
      if (newName !== undefined && distinct.length === 1 && !names.includes(null)) {
        this.rewrite(source, newName, landing.map((use) => keyOf(use.path, use.start)));
        continue;
      }
      this.record(unrelatedOutcome(source.path, source.start, source.end));
      if (newName !== undefined) for (const use of landing) this.record(mixedOutcome(use.path, use.start, use.end, use.position, use.receiver, this.old));
    }
  }

  /** Rewrite `source` to `newName`, the reads at `proven` naming what is renamed. */
  private rewrite(source: LiteralSource, newName: string, proven: string[]): void {
    const key = keyOf(source.path, source.start);
    const known = this.rewritten.get(key);
    if (known !== undefined) {
      for (const read of proven) known.proven.add(read);
      return;
    }
    this.rewritten.set(key, { source, proven: new Set(proven) });
    this.record(sourceOutcome(source, newName));
    const file = this.session.sources.get(source.path)?.source;
    if (file === undefined || !displayHolds(file, source, newName)) return;
    this.taken.set(key, { path: this.r.rel(source.path), line: this.session.lineOf(source.path, source.start), name: newName });
  }

  /** The rewritten sources `--keep` left. */
  private kept(): [string, Rewritten][] {
    return [...this.rewritten].filter(([, { source }]) => this.edits.some((e) => e.path === source.path && e.start === source.start));
  }

  /** Each rewritten source whose display already holds the new name. */
  sourceConflicts(): Taken[] {
    return this.kept().flatMap(([key]) => this.taken.get(key) ?? []);
  }

  /** Each read of a name holding a rewritten source that does not prove it names what is renamed. */
  unverifiedReads(): Finding[] {
    const out: Finding[] = [];
    for (const [, { source, proven }] of this.kept()) {
      const values = { old: this.old, source_path: this.r.rel(source.path), source_line: this.session.lineOf(source.path, source.start) };
      for (const read of sourceReads(this.session.servicesFor(source.path), source)) {
        if (!proven.has(keyOf(read.path, read.start))) out.push(this.session.finding(read.path, read.start, 'refactor.unverified-read', { ...values, name: read.name }));
      }
    }
    return out;
  }

  /** A literal member's names: each error the edits bring on a name is followed to its sources spelling OLD, which are
   * rewritten, and the program checked again; the errors then left are blind spots. */
  follow(): void {
    const { newName } = this;
    for (;;) {
      let merged: Map<string, Edit[]>;
      try {
        merged = mergeEdits(this.edits);
      } catch (error) {
        if (error instanceof RefactorError) return;
        throw error;
      }
      const added = addedErrors(this.r, merged);
      const before = this.rewritten.size;
      if (newName !== null) {
        for (const error of added) for (const [source, read] of this.errorSources(error)) this.rewrite(source, newName, [read]);
      }
      if (this.rewritten.size > before) continue;
      for (const error of added) this.record(unresolvedOutcome(error.path, error.start, error.end, this.old));
      return;
    }
  }

  /** The sources spelling OLD of the name `error` is on, each with that read's key, but those the rename's own
   * locations already rewrite. */
  private errorSources(error: AddedError): [LiteralSource, string][] {
    const found = this.session.sources.get(error.path);
    const name = found === undefined ? null : erroringName(found.source, error.start, error.end);
    if (found === undefined || name === null) return [];
    const read = keyOf(error.path, name.getStart(found.source));
    return literalSources(found.service, name)
      .filter((s) => s.text === this.old && this.session.sources.has(s.path))
      .filter((s) => this.rewritten.has(keyOf(s.path, s.start)) || !this.edited(s.path, s.start, s.end))
      .map((s) => [s, read]);
  }

  /** The new name of each declaration the lookup of OLD on `object`'s type lands on, null for an unchanged one. */
  private landings(checker: TS.TypeChecker, object: TS.Expression): (string | null)[] {
    const type = checker.getApparentType(checker.getTypeAtLocation(object));
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

/** The identifier or dotted name an error at `start`..`end` of `source` is on: the one it spans, or the value of the
 * `return` whose keyword it spans (where the checker reports a returned value). */
function erroringName(source: TS.SourceFile, start: number, end: number): TS.Node | null {
  let node = nodeAt(source, start);
  while (node.parent.getStart(source) === start && node.parent.end <= end) node = node.parent;
  if (ts().isReturnStatement(node) && node.getFirstToken(source)?.end === end) node = node.expression ?? node;
  else if (node.getStart(source) !== start || node.end !== end) return null;
  return ts().isIdentifier(node) || ts().isPropertyAccessExpression(node) ? node : null;
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

/** Drop every edit, blind spot and leftover of `group` at a kept site. */
function keep(group: NameGroup, keeps: Keeps): void {
  const kept = group.edits.filter((e) => !keeps.keeps(e.path, e.start));
  group.edits.splice(0, group.edits.length, ...kept);
  group.blindspots = group.blindspots.filter((b) => !keeps.kept(b.path, b.line));
  group.leftovers = group.leftovers.filter((f) => !keeps.kept(f.path, f.line, false));
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
  ];
  const { refusals: out, missing } = missingSites(r, sites);
  const { targets } = resolution;
  if (targets.length > 0 && targets.every((t) => t.move !== null)) {
    for (const [option, raw] of sites) if (option !== '--keep' && !missing.has(`${option}\0${raw}`)) out.push(refusal(message('refactor.not-stand-in', { site: raw }), 2));
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
    if (!Site.parse(raw, r.root, base).missing(r.root)) continue;
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

function runRules(group: NameGroup, docs: boolean, renamedNames: Set<string>): void {
  if (group.member) group.scan();
  if (group.literal) group.follow();
  if (group.literal) group.equalStrings();
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
function nameConflicts(session: Session, targets: Target[], pending: Tagged[], edits: Tagged[], together: boolean, moves: Target[], taken: Taken[]): Refusal[] {
  const found: Taken[] = [...taken, ...(together ? convergingMoves(session, moves) : [])];
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

/** Site resolution over the final `edits`: each unneeded whole-path keep's warning printed; each `--with` or
 * `--without` site of `unclassified`, each computed `--with` stand-in, then each line keep that matched nothing. */
function resolveSites(session: Session, edits: Tagged[], keeps: Keeps, unclassified: string[], groups: NameGroup[]): Refusal[] {
  const edited = new Map<string, number[]>();
  for (const e of edits) {
    const rel = session.r.rel(e.path);
    const lines = edited.get(rel) ?? [];
    lines.push(session.lineOf(e.path, e.start));
    edited.set(rel, lines);
  }
  const { warnings, refusals } = resolveKeeps(keeps.unmatched(), edited);
  process.stderr.write(warnings.map((w) => `${w}\n`).join(''));
  return [
    ...unclassified.map((site) => refusal(message('refactor.not-stand-in', { site }), 2)),
    ...groups.flatMap((g) => g.computed),
    ...refusals,
  ];
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
  const failures = [...resolution.failures, ...checks(r, resolution), ...configFailures(r)];
  if (failures.length > 0) throw new Refused(failures);
  const { targets } = resolution;
  const symbols = targets.filter((t) => t.move === null);
  progress.phase('references');
  const session = new Session(r, symbols.map((t) => t.file));
  const keeps = new Keeps(session, r.args.keep ?? []);
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
      if (target.retarget) target.refusals = retargetSites(session, target, (path, position) => keeps.keeps(path, position), needs);
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
      runRules(named, r.args.docs === true, renamedNames);
      return named;
    });
    pending.push(...group.edits);
    keep(group, keeps);
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
    .filter((e) => !keeps.keeps(e.path, e.start));
  const retargets = texts(targets.flatMap((t) => t.refusals));
  const blindspots = groups.flatMap((g) => g.blindspots).sort(byPosition);
  const blind = allowed ? [] : texts(blindspots);
  const standIns = texts(groups.flatMap((g) => g.standIns));
  let edits: Tagged[] = [];
  let conflicts: Refusal[] = [];
  let sites: Refusal[] = [];
  if (!stopped) {
    edits = [...groups.flatMap((g) => g.edits), ...planImports(session, needs), ...moduleEdits];
    sites = resolveSites(session, edits, keeps, [...withSites, ...withoutSites].filter((site) => !matched.has(site)), groups);
  }
  if (!stopped && sites.length === 0) {
    progress.phase('conflicts');
    conflicts = timed('conflicts', () => {
      const merged = mapConflicts(session, edits);
      const taken = groups.flatMap((g) => g.sourceConflicts());
      return [...nameConflicts(session, symbols, pending, edits, merged.length === 0, moving, taken), ...merged];
    });
  }
  const attr = groups.filter((g) => g.blindspots.length > 0).map((g) => g.old).join(', .');
  const closing = blind.length > 0 ? [refusal(message('refactor.blindspots', { count: blind.length, attr }))] : [];
  const report = unique([...retargets, ...blind, ...standIns, ...conflicts, ...sites, ...closing]);
  if (report.length > 0) throw new Refused(report);
  const leftovers = groups.flatMap((g) => [...g.leftovers, ...g.unverifiedReads()]).sort(byPosition);
  process.stderr.write([...blindspots, ...leftovers].map((f) => `${f.text}\n`).join(''));
  const headers = targets.map((t) => message(t.retarget ? 'refactor.retarget-header' : 'refactor.rename-header', { old: t.old, new: t.newName }));
  const moves = moving.flatMap((t): [string, string][] => (t.move === null ? [] : [[t.move.from, t.move.to]]));
  return r.emit(headers, mergeEdits(edits), moves, [], progress);
}
