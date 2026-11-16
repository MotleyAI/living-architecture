// A rename's name checks: every name keeps its declaration (each identifier spelled with an old or a new name
// re-resolved over an overlay program of the edited code), and a renamed member takes no name its type's namespace holds.
import type * as TS from 'typescript';
import { byCodePoint } from '../contract/index.js';
import { ts } from '../lang/index.js';
import type { Edit } from './edits.js';
import type { ProjectSource } from './session.js';

/** An entry of a check: its index and new name; a retarget's expected declarations, else null. */
export interface CheckEntry {
  index: number;
  old: string;
  newName: string;
  expected: Set<string> | null;
}

/** An edit with the entry it comes from. */
export interface EntryEdit extends Edit {
  entry: number;
}

/** A refused new name and its site (absolute path, offset) in the original code. */
export interface NameConflict {
  name: string;
  path: string;
  position: number;
}

interface Internals {
  getMeaningFromLocation(node: TS.Node): number;
  getMeaningFromDeclaration(node: TS.Node): number;
}

/** TypeScript's semantic meaning of a position or a declaration (internal in its typings). */
function internals(): Internals {
  const found = ts() as unknown as Partial<Internals>;
  if (found.getMeaningFromLocation === undefined || found.getMeaningFromDeclaration === undefined) throw new Error('typescript no longer provides semantic meanings');
  return found as Internals;
}

const keyOf = (path: string, start: number): string => `${path}\0${start}`;

const ESCAPE = String.raw`\u`;

/** The name an identifier's source text spells, its unicode escapes decoded. */
export const identifierText = (raw: string): string =>
  raw.replaceAll(/\\u\{([0-9a-fA-F]+)\}|\\u([0-9a-fA-F]{4})/gu, (_match, braced: string | undefined, plain: string | undefined) => String.fromCodePoint(Number.parseInt(braced ?? plain ?? '', 16)));

/** `text` may spell one of `names`: it spells one, or holds a unicode escape. */
const mayName = (text: string, names: Set<string>): boolean => [...names].some((name) => text.includes(name)) || text.includes(ESCAPE);

/** A declared name's start: a quoted name's (computed or not) is its text's, inside the quotes. */
function nameStart(name: TS.Node, source: TS.SourceFile): number {
  const literal = ts().isComputedPropertyName(name) ? name.expression : name;
  return ts().isStringLiteral(literal) || ts().isNoSubstitutionTemplateLiteral(literal) ? literal.getStart(source) + 1 : name.getStart(source);
}

/** A file's edits applied, and positions of the edited text mapped back to the original. */
class EditedFile {
  readonly text: string;
  private readonly spans: { start: number; end: number; original: number; shift: number }[] = [];

  constructor(original: string, edits: Edit[]) {
    const sorted = edits.toSorted((a, b) => a.start - b.start);
    let out = '';
    let at = 0;
    let shift = 0;
    for (const edit of sorted) {
      if (edit.start < at) continue;
      out += original.slice(at, edit.start);
      const start = edit.start + shift;
      this.spans.push({ start, end: start + edit.newText.length, original: edit.start, shift: shift + edit.newText.length - edit.length });
      out += edit.newText;
      at = edit.start + edit.length;
      shift += edit.newText.length - edit.length;
    }
    this.text = out + original.slice(at);
  }

  /** The original offset of `position`: an edit's own start for a position inside its new text. */
  original(position: number): number {
    let shift = 0;
    for (const span of this.spans) {
      if (position < span.start) break;
      if (position < span.end) return span.original;
      shift = span.shift;
    }
    return position - shift;
  }
}

/** A program's file-name canonicalization (internal in TypeScript's typings). */
interface Canonical {
  useCaseSensitiveFileNames(): boolean;
  getCanonicalFileName(name: string): string;
}

/** The program `program` over the edited texts, unchanged source files reused: its host canonicalizes file names as
 * `program` does, so the shared source files keep their paths. */
function overlayProgram(program: TS.Program, edited: Map<string, EditedFile>): TS.Program {
  const options = program.getCompilerOptions();
  const canonical = program as unknown as Canonical;
  const host = ts().createCompilerHost(options, true);
  const fallback = host.getSourceFile.bind(host);
  host.getSourceFile = (name, version, onError, create) => {
    const file = edited.get(name);
    if (file !== undefined) return ts().createSourceFile(name, file.text, version, true);
    return program.getSourceFile(name) ?? fallback(name, version, onError, create);
  };
  host.readFile = (name) => edited.get(name)?.text ?? ts().sys.readFile(name);
  host.getCurrentDirectory = () => program.getCurrentDirectory();
  host.useCaseSensitiveFileNames = () => canonical.useCaseSensitiveFileNames();
  host.getCanonicalFileName = (name) => canonical.getCanonicalFileName(name);
  Object.assign(host, { useSourceOfProjectReferenceRedirect: () => true });
  const references = program.getProjectReferences();
  return ts().createProgram({ rootNames: program.getRootFileNames(), options, host, oldProgram: program, ...(references === undefined ? {} : { projectReferences: references }) });
}

/** Declarations whose name is a member's, not a scope's. */
const MEMBER_KINDS = (): Set<TS.SyntaxKind> => {
  const k = ts().SyntaxKind;
  return new Set([
    k.PropertyAssignment,
    k.PropertyDeclaration,
    k.PropertySignature,
    k.MethodDeclaration,
    k.MethodSignature,
    k.GetAccessor,
    k.SetAccessor,
    k.EnumMember,
    k.NamedTupleMember,
    k.JsxAttribute,
  ]);
};

/** `id` is a name the language resolves: a reference, a declaration's name, an import's or re-export's name, an
 * export's local name. */
function resolvable(id: TS.Identifier, members: Set<TS.SyntaxKind>): boolean {
  const parent = id.parent;
  if (ts().isPropertyAccessExpression(parent)) return parent.expression === id;
  if (ts().isQualifiedName(parent)) return parent.left === id;
  if (ts().isImportSpecifier(parent)) return true;
  if (ts().isExportSpecifier(parent)) return parent.parent.parent.moduleSpecifier !== undefined || (parent.propertyName ?? parent.name) === id;
  if (ts().isBindingElement(parent)) return parent.name === id || parent.initializer === id;
  if (members.has(parent.kind)) return (parent as TS.NamedDeclaration).name !== id;
  return !(
    ts().isLabeledStatement(parent) ||
    ts().isBreakOrContinueStatement(parent) ||
    ts().isMetaProperty(parent) ||
    ts().isImportTypeNode(parent) ||
    ts().isNamespaceExport(parent) ||
    ts().isNamespaceExportDeclaration(parent)
  );
}

/** The declaration `id` names, when it is a resolvable declaration's name. */
function declarationOf(id: TS.Identifier): TS.Declaration | null {
  const parent = id.parent;
  if (ts().isExportSpecifier(parent) || ts().isShorthandPropertyAssignment(parent)) return null;
  return (parent as TS.NamedDeclaration).name === id ? (parent as TS.Declaration) : null;
}

/** Every resolvable identifier of `source` spelled with one of `names`. */
function identifiers(source: TS.SourceFile, names: Set<string>): TS.Identifier[] {
  const members = MEMBER_KINDS();
  const out: TS.Identifier[] = [];
  const visit = (node: TS.Node): void => {
    if (ts().isIdentifier(node)) {
      if (names.has(node.text) && resolvable(node, members)) out.push(node);
      return;
    }
    ts().forEachChild(node, visit);
  };
  visit(source);
  return out;
}

/** One identifier: its key and spelling, and the declarations it resolves to, as keys in the original code. */
interface Occurrence {
  key: string;
  path: string;
  start: number;
  text: string;
  node: TS.Identifier;
  checker: TS.TypeChecker;
  declarations: string[];
}

/** Resolves names in one program state, declaration positions mapped to the original code. */
class Resolver {
  constructor(private readonly original: (path: string, position: number) => number) {}

  /** `d`'s key: its file and its name's start in the original code. */
  key(d: TS.Declaration): string {
    const source = d.getSourceFile();
    const name = ts().getNameOfDeclaration(d);
    const start = name === undefined ? d.getStart(source) : nameStart(name, source);
    return keyOf(source.fileName, this.original(source.fileName, start));
  }

  /** The declarations `id` resolves to with the meaning its position requires, an import followed to its target. */
  resolve(checker: TS.TypeChecker, id: TS.Identifier): string[] {
    const parent = id.parent;
    let symbol = ts().isShorthandPropertyAssignment(parent) && parent.name === id ? checker.getShorthandAssignmentValueSymbol(parent) : checker.getSymbolAtLocation(id);
    if (symbol !== undefined && (symbol.flags & ts().SymbolFlags.Alias) !== 0) symbol = checker.getAliasedSymbol(symbol); // NOSONAR(S1529) — SymbolFlags bitmask test
    const meaning = internals().getMeaningFromLocation(id);
    const declarations = (symbol?.declarations ?? []).filter((d) => (internals().getMeaningFromDeclaration(d) & meaning) !== 0); // NOSONAR(S1529) — SemanticMeaning bitmask test
    return [...new Set(declarations.map((d) => this.key(d)))].sort(byCodePoint);
  }

  /** The occurrences of `names` in `source`, keyed in the original code. */
  occurrences(path: string, source: TS.SourceFile, checker: TS.TypeChecker, names: Set<string>): Occurrence[] {
    return identifiers(source, names).map((node) => {
      const start = this.original(path, node.getStart(source));
      return { key: keyOf(path, start), path, start, text: node.text, node, checker, declarations: this.resolve(checker, node) };
    });
  }
}

/** A declaration key's path and offset. */
const at = (key: string): { path: string; position: number } => ({ path: key.slice(0, key.indexOf('\0')), position: Number(key.slice(key.indexOf('\0') + 1)) });

const same = (a: string[], b: string[]): boolean => a.length === b.length && a.every((k, i) => k === b[i]);

/** SymbolFlags for a semantic meaning. */
function symbolFlags(meaning: number): number {
  const flags = ts().SymbolFlags;
  return (meaning & 1 ? flags.Value : 0) | (meaning & 2 ? flags.Type : 0) | (meaning & 4 ? flags.Namespace : 0); // NOSONAR(S1529) — SemanticMeaning and SymbolFlags bitmasks
}

/** A member declaration a rename renames: its key, entry, holder and side. */
interface RenamedMember {
  key: string;
  path: string;
  start: number;
  entry: CheckEntry;
  holder: TS.Node;
  isStatic: boolean;
  checker: TS.TypeChecker;
}

const hasStatic = (d: TS.Node): boolean => ts().canHaveModifiers(d) && (ts().getModifiers(d) ?? []).some((m) => m.kind === ts().SyntaxKind.StaticKeyword);

/** The type holding member `d` (a parameter property's class), null for a declaration that is no member. */
function holderOf(d: TS.Node): TS.Node | null {
  if (ts().isParameter(d)) return ts().isParameterPropertyDeclaration(d, d.parent) ? d.parent.parent : null;
  const parent = d.parent as TS.Node | undefined;
  if (parent === undefined) return null;
  const holds = ts().isClassLike(parent) || ts().isInterfaceDeclaration(parent) || ts().isTypeLiteralNode(parent) || ts().isEnumDeclaration(parent) || ts().isObjectLiteralExpression(parent);
  if (!holds) return null;
  const member = ts().isClassElement(d) || ts().isTypeElement(d) || ts().isEnumMember(d) || ts().isPropertyAssignment(d) || ts().isShorthandPropertyAssignment(d) || ts().isMethodDeclaration(d) || ts().isAccessor(d);
  return member && !ts().isConstructorDeclaration(d) && !ts().isClassStaticBlockDeclaration(d) ? parent : null;
}

/** The member declaration whose name starts at `start`, else null. */
function memberAt(source: TS.SourceFile, start: number): TS.Declaration | null {
  let node: TS.Node = source;
  for (;;) {
    const inner: TS.Node | undefined = ts().forEachChild(node, (child) => (child.getStart(source) <= start && start < child.end ? child : undefined));
    if (inner === undefined) break;
    node = inner;
  }
  let declaration = node.parent as TS.Node | undefined;
  if (declaration !== undefined && ts().isComputedPropertyName(declaration)) {
    // A computed key names its member by value: only a quoted key is the name an edit renames.
    if (!ts().isStringLiteralLike(declaration.expression)) return null;
    declaration = declaration.parent;
  }
  if (declaration === undefined || holderOf(declaration) === null) return null;
  const name = ts().getNameOfDeclaration(declaration as TS.Declaration);
  const within = name !== undefined && name.getStart(source) <= start && start < name.end;
  return within ? (declaration as TS.Declaration) : null;
}

/** A member declaration's name: a computed key's literal value (by its type), null when it has none. */
function memberName(d: TS.Node, checker: TS.TypeChecker | undefined): string | null {
  const name = ts().getNameOfDeclaration(d as TS.Declaration);
  if (name === undefined) return null;
  if (!ts().isComputedPropertyName(name)) return ts().isIdentifier(name) || ts().isPrivateIdentifier(name) || ts().isStringLiteralLike(name) || ts().isNumericLiteral(name) ? name.text : null;
  if (ts().isStringLiteralLike(name.expression) || ts().isNumericLiteral(name.expression)) return name.expression.text;
  const type = checker?.getTypeAtLocation(name.expression);
  if (type?.isStringLiteral() === true) return type.value;
  return type?.isNumberLiteral() === true ? String(type.value) : null;
}

/** The members `holder` declares itself. */
function ownMembers(holder: TS.Node): TS.Node[] {
  if (ts().isClassLike(holder)) {
    const constructors = holder.members.filter((m) => ts().isConstructorDeclaration(m));
    const properties = constructors.flatMap((c) => c.parameters.filter((p) => ts().isParameterPropertyDeclaration(p, p.parent)));
    return [...holder.members.filter((m) => holderOf(m) !== null), ...properties];
  }
  if (ts().isInterfaceDeclaration(holder) || ts().isTypeLiteralNode(holder)) return [...holder.members];
  if (ts().isEnumDeclaration(holder)) return [...holder.members];
  if (ts().isObjectLiteralExpression(holder)) return [...holder.properties];
  return [];
}

/** The type of `holder`'s side its members live on. */
function sideType(checker: TS.TypeChecker, holder: TS.Node, isStatic: boolean): TS.Type {
  const type = checker.getTypeAtLocation(holder);
  const symbol = type.getSymbol();
  if (symbol === undefined) return type;
  if (ts().isClassLike(holder)) return isStatic ? checker.getTypeOfSymbolAtLocation(symbol, holder) : checker.getDeclaredTypeOfSymbol(symbol);
  if (ts().isEnumDeclaration(holder)) return checker.getTypeOfSymbolAtLocation(symbol, holder);
  return type;
}

const nodeKey = (node: TS.Node): string => keyOf(node.getSourceFile().fileName, node.getStart(node.getSourceFile()));

/** A member declaration's key: its name's start. */
function memberKey(d: TS.Node): string {
  const source = d.getSourceFile();
  const name = ts().getNameOfDeclaration(d as TS.Declaration);
  return keyOf(source.fileName, name === undefined ? d.getStart(source) : nameStart(name, source));
}

/** The class and interface declarations of the project's sources and the types each extends or implements. */
class Hierarchy {
  private readonly bases = new Map<string, Set<string>>();
  private readonly nodes = new Map<string, TS.ClassLikeDeclaration | TS.InterfaceDeclaration>();
  private readonly merged = new Map<string, Set<string>>();

  constructor(sources: Iterable<ProjectSource>) {
    for (const { source, checker } of sources) {
      const visit = (node: TS.Node): void => {
        if (ts().isClassLike(node) || ts().isInterfaceDeclaration(node)) this.add(checker, node);
        ts().forEachChild(node, visit);
      };
      visit(source);
    }
  }

  private add(checker: TS.TypeChecker, node: TS.ClassLikeDeclaration | TS.InterfaceDeclaration): void {
    const key = nodeKey(node);
    this.nodes.set(key, node);
    const declarations = checker.getTypeAtLocation(node).getSymbol()?.declarations ?? [];
    this.merged.set(key, new Set([key, ...declarations.filter((d) => ts().isClassLike(d) || ts().isInterfaceDeclaration(d)).map(nodeKey)]));
    const bases = new Set<string>();
    for (const clause of node.heritageClauses ?? []) {
      for (const type of clause.types) {
        for (const d of checker.getTypeAtLocation(type).getSymbol()?.declarations ?? []) {
          if (ts().isClassLike(d) || ts().isInterfaceDeclaration(d)) bases.add(nodeKey(d));
        }
      }
    }
    this.bases.set(key, bases);
  }

  /** Every project type `key` extends or implements, transitively. */
  ancestors(key: string): Set<string> {
    const out = new Set<string>();
    const pending = [...(this.bases.get(key) ?? [])];
    for (let next = pending.pop(); next !== undefined; next = pending.pop()) {
      if (out.has(next)) continue;
      out.add(next);
      pending.push(...(this.bases.get(next) ?? []));
    }
    return out;
  }

  /** Every project type extending or implementing `key`, transitively. */
  descendants(key: string): Set<string> {
    return new Set([...this.nodes.keys()].filter((k) => this.ancestors(k).has(key)));
  }

  /** `key` and every class or interface declaration merged with it. */
  declarations(key: string): Set<string> {
    return this.merged.get(key) ?? new Set([key]);
  }

  /** The class or interface declaration of `key`. */
  node(key: string): TS.ClassLikeDeclaration | TS.InterfaceDeclaration | undefined {
    return this.nodes.get(key);
  }
}

/** The keys of the types a renamed member's name is shared with: its holder, its project ancestors and
 * descendants, each with every declaration merged with it. */
function relatedHolders(m: RenamedMember, hierarchy: Hierarchy): Set<string> {
  const own = [...hierarchy.declarations(nodeKey(m.holder))];
  const near = own.flatMap((key) => [key, ...hierarchy.ancestors(key), ...hierarchy.descendants(key)]);
  return new Set(near.flatMap((key) => [...hierarchy.declarations(key)]));
}

/** A conflict candidate; the first by path then offset is reported. */
interface Site {
  name: string;
  path: string;
  position: number;
}

/** The name checks of one rename or map over the project's sources. */
export class NameChecks {
  private readonly before = new Map<string, Occurrence>();
  private readonly names: Set<string>;
  private hierarchy: Hierarchy | null = null;

  /** `names`: every old and new name, and retargets' target names; resolved once over the original code. */
  constructor(
    private readonly sources: Map<string, ProjectSource>,
    names: Iterable<string>,
    private readonly rel: (path: string) => string,
  ) {
    this.names = new Set(names);
    const resolver = new Resolver((_path, position) => position);
    for (const [path, { source, checker }] of sources) {
      if (!mayName(source.text, this.names)) continue;
      for (const o of resolver.occurrences(path, source, checker, this.names)) this.before.set(o.key, o);
    }
  }

  /** The first site at which `edits` of `entries` change a name's declaration or meet a member, else null; `kept`
   * holds the keys of the edits `--keep` dropped. */
  check(entries: CheckEntry[], edits: EntryEdit[], kept: Set<string>): NameConflict | null {
    const byIndex = new Map(entries.map((e) => [e.index, e]));
    const ours = edits.filter((e) => byIndex.has(e.entry));
    const editAt = new Map(ours.map((e) => [keyOf(e.path, e.start), e]));
    const edited = this.edited(ours);
    const resolver = new Resolver((path, position) => edited.get(path)?.original(position) ?? position);
    const after = this.after(edited, resolver);
    const renamed = new Map<string, CheckEntry>();
    for (const [key, o] of this.before) {
      const edit = editAt.get(key);
      const entry = edit === undefined ? undefined : byIndex.get(edit.entry);
      const now = after.get(key);
      if (entry?.expected === null && now !== undefined && now.text !== o.text && declarationOf(o.node) !== null) renamed.set(key, entry);
    }
    const members = this.renamedMembers(ours, byIndex);
    for (const m of members) renamed.set(m.key, m.entry);
    const first = this.firstDeclarations(renamed);
    const sites: Site[] = [];
    const meet = (a: CheckEntry, b: CheckEntry): void => {
      const earlier = a.index < b.index ? a : b;
      const site = first.get(earlier.index);
      if (site !== undefined) sites.push({ name: earlier.newName, ...site });
    };
    for (const [key, o] of this.before) {
      const now = after.get(key);
      if (now !== undefined) this.compare(o, now, { edit: editAt.get(key), byIndex, renamed, kept, sites, meet, fallback: entries[0] as CheckEntry });
    }
    for (const now of after.values()) this.sharedScope(now, resolver, renamed, sites, meet);
    this.members(members, sites, meet);
    const found = sites.toSorted((a, b) => byCodePoint(this.rel(a.path), this.rel(b.path)) || a.position - b.position)[0];
    return found ?? null;
  }

  /** Each project source's edited text. */
  private edited(edits: EntryEdit[]): Map<string, EditedFile> {
    const byPath = new Map<string, EntryEdit[]>();
    for (const e of edits) if (this.sources.has(e.path)) byPath.set(e.path, [...(byPath.get(e.path) ?? []), e]);
    return new Map([...byPath].map(([path, fileEdits]) => [path, new EditedFile((this.sources.get(path) as ProjectSource).source.text, fileEdits)]));
  }

  /** The occurrences after the edits, by their key in the original code. */
  private after(edited: Map<string, EditedFile>, resolver: Resolver): Map<string, Occurrence> {
    const programs = new Map<TS.Program, TS.Program>();
    const programOf = (found: ProjectSource): TS.Program | undefined => {
      const program = found.service.getProgram();
      if (program === undefined) return undefined;
      if (!programs.has(program)) {
        const touched = [...edited.keys()].some((path) => program.getSourceFile(path) !== undefined);
        programs.set(program, touched ? overlayProgram(program, edited) : program);
      }
      return programs.get(program);
    };
    const out = new Map<string, Occurrence>();
    for (const [path, found] of this.sources) {
      const text = edited.get(path)?.text ?? found.source.text;
      if (!mayName(text, this.names)) continue;
      const program = programOf(found);
      const source = program?.getSourceFile(path);
      if (program === undefined || source === undefined) continue;
      for (const o of resolver.occurrences(path, source, program.getTypeChecker(), this.names)) if (!out.has(o.key)) out.set(o.key, o);
    }
    return out;
  }

  /** Sites where occurrence `o` resolves to other declarations after the edits (`now`): a rewritten one must keep its
   * declarations (a retarget's: its target's), a kept one may dangle, any other must keep them. */
  private compare(o: Occurrence, now: Occurrence, c: CompareContext): void {
    const added = now.declarations.filter((k) => !o.declarations.includes(k));
    const existing = added.filter((k) => !c.renamed.has(k) && this.sources.has(at(k).path));
    const entry = c.edit === undefined ? undefined : c.byIndex.get(c.edit.entry);
    if (entry !== undefined && now.text !== o.text) {
      this.compareRewritten(o, now, entry, { added, existing }, c);
      return;
    }
    if (same(now.declarations, o.declarations)) return;
    const via = added.map((k) => c.renamed.get(k)).find((e) => e !== undefined) ?? o.declarations.map((k) => c.renamed.get(k)).find((e) => e !== undefined) ?? c.fallback;
    if (!c.kept.has(o.key)) {
      c.sites.push({ name: via.newName, path: o.path, position: o.start });
    } else if (now.declarations.length > 0) {
      for (const k of existing) c.sites.push({ name: via.newName, ...at(k) });
      if (existing.length === 0) c.sites.push({ name: via.newName, path: o.path, position: o.start });
    }
  }

  /** Sites where rewritten occurrence `o` of `entry` resolves to other declarations than expected. */
  private compareRewritten(o: Occurrence, now: Occurrence, entry: CheckEntry, found: { added: string[]; existing: string[] }, c: CompareContext): void {
    const expected = entry.expected;
    const ok = expected === null ? same(now.declarations, o.declarations) : now.declarations.length > 0 && now.declarations.every((k) => expected.has(k));
    if (ok) return;
    for (const k of found.existing) c.sites.push({ name: entry.newName, ...at(k) });
    const others = found.added.flatMap((k) => {
      const other = c.renamed.get(k);
      return other !== undefined && other !== entry ? [other] : [];
    });
    for (const other of others) c.meet(entry, other);
    if (found.existing.length === 0 && others.length === 0) c.sites.push({ name: entry.newName, path: o.path, position: o.start });
  }

  /** A declaration of the edited code that shares its scope and a meaning with another, one of them renamed. */
  private sharedScope(now: Occurrence, resolver: Resolver, renamed: Map<string, CheckEntry>, sites: Site[], meet: (a: CheckEntry, b: CheckEntry) => void): void {
    const declaration = declarationOf(now.node);
    if (declaration === null || ts().isFunctionExpression(declaration) || ts().isClassExpression(declaration)) return;
    const meaning = internals().getMeaningFromDeclaration(declaration);
    const table = now.checker.resolveName(now.text, declaration.parent, symbolFlags(meaning), false);
    const mine = renamed.get(now.key);
    for (const other of table?.declarations ?? []) {
      if (other === declaration || (internals().getMeaningFromDeclaration(other) & meaning) === 0) continue; // NOSONAR(S1529) — SemanticMeaning bitmask test
      const key = resolver.key(other);
      const theirs = renamed.get(key);
      if (mine !== undefined && theirs !== undefined) {
        if (mine !== theirs) meet(mine, theirs);
      } else if (theirs !== undefined) {
        sites.push({ name: theirs.newName, path: now.path, position: now.start });
      } else if (mine !== undefined) {
        const site = at(key);
        sites.push({ name: mine.newName, ...(this.sources.has(site.path) ? site : { path: now.path, position: now.start }) });
      }
    }
  }

  /** The member declarations `edits` rename: their new text the entry's new name, or a shorthand property's
   * `<new>: <value>`. */
  private renamedMembers(edits: EntryEdit[], byIndex: Map<number, CheckEntry>): RenamedMember[] {
    const out: RenamedMember[] = [];
    for (const e of edits) {
      const entry = byIndex.get(e.entry);
      const found = this.sources.get(e.path);
      if (entry?.expected !== null || found === undefined || entry.newName === entry.old) continue;
      if (e.newText !== entry.newName && !e.newText.startsWith(`${entry.newName}: `)) continue;
      const declaration = memberAt(found.source, e.start);
      const holder = declaration === null ? null : holderOf(declaration);
      if (declaration === null || holder === null) continue;
      out.push({ key: keyOf(e.path, e.start), path: e.path, start: e.start, entry, holder, isStatic: !ts().isParameter(declaration) && hasStatic(declaration), checker: found.checker });
    }
    return out;
  }

  /** Each entry's first renamed declaration by path, then offset. */
  private firstDeclarations(renamed: Map<string, CheckEntry>): Map<number, { path: string; position: number }> {
    const all = [...renamed].map(([key, entry]) => ({ entry: entry.index, ...at(key) })).sort((a, b) => byCodePoint(this.rel(a.path), this.rel(b.path)) || a.position - b.position);
    const out = new Map<number, { path: string; position: number }>();
    for (const { entry, path, position } of all) if (!out.has(entry)) out.set(entry, { path, position });
    return out;
  }

  /** Renamed members whose type, an ancestor (the root included) or a project descendant declares the new name. */
  private members(renamed: RenamedMember[], sites: Site[], meet: (a: CheckEntry, b: CheckEntry) => void): void {
    if (renamed.length === 0) return;
    this.hierarchy ??= new Hierarchy(this.sources.values());
    const renamedKeys = new Set(renamed.map((m) => m.key));
    for (const m of renamed) this.member(m, this.hierarchy, renamedKeys, sites);
    for (const m of renamed) {
      const related = relatedHolders(m, this.hierarchy);
      for (const other of renamed) {
        if (other.entry !== m.entry && identifierText(other.entry.newName) === identifierText(m.entry.newName) && other.isStatic === m.isStatic && related.has(nodeKey(other.holder))) meet(m.entry, other.entry);
      }
    }
  }

  /** Sites of the members of `m`'s new name its type, an ancestor or a project descendant declares. */
  private member(m: RenamedMember, hierarchy: Hierarchy, renamedKeys: Set<string>, sites: Site[]): void {
    const name = m.entry.newName;
    const spelled = identifierText(name);
    const holderKey = nodeKey(m.holder);
    const conflicting = (d: TS.Node): boolean => memberName(d, this.sources.get(d.getSourceFile().fileName)?.checker) === spelled && !renamedKeys.has(memberKey(d)) && (ts().isParameter(d) ? !m.isStatic : hasStatic(d) === m.isStatic);
    const push = (d: TS.Node): void => {
      sites.push({ name, ...(this.sources.has(d.getSourceFile().fileName) ? at(memberKey(d)) : { path: m.path, position: m.start }) });
    };
    const holders: TS.Node[] = [m.holder];
    for (const key of relatedHolders(m, hierarchy)) {
      if (key === holderKey) continue;
      const node = hierarchy.node(key);
      if (node !== undefined && (!m.isStatic || ts().isClassLike(node))) holders.push(node);
    }
    for (const holder of holders) for (const d of ownMembers(holder).filter(conflicting)) push(d);
    const inherited = m.checker.getPropertyOfType(sideType(m.checker, m.holder, m.isStatic), spelled);
    // An implicit member (a class's `prototype`) has no declaration: the renamed one is the site.
    if (inherited !== undefined && (inherited.declarations ?? []).length === 0) sites.push({ name, path: m.path, position: m.start });
    const elsewhere = (d: TS.Node): boolean => {
      const holder = holderOf(d);
      return holder === null || nodeKey(holder) !== holderKey;
    };
    for (const d of inherited?.declarations ?? []) if (elsewhere(d) && !renamedKeys.has(memberKey(d))) push(d);
  }
}

interface CompareContext {
  edit: EntryEdit | undefined;
  byIndex: Map<number, CheckEntry>;
  renamed: Map<string, CheckEntry>;
  kept: Set<string>;
  sites: Site[];
  meet: (a: CheckEntry, b: CheckEntry) => void;
  fallback: CheckEntry;
}
