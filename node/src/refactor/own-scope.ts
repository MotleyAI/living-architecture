// The own-scope name check: a rename whose new name the scope declaring its symbol already holds, decided from the
// compiler's symbol tables before any reference search.
import type * as TS from 'typescript';
import { byCodePoint } from '../contract/index.js';
import { ts } from '../lang/index.js';
import { hasStatic, holderOf, identifierText, internals, memberName, nameStart, type NameConflict, ownMembers } from './bindings.js';
import { keyOf, symbolOf } from './retarget.js';
import { nodeAt, type Refactor } from './session.js';

/** A resolved entry of a symbol: its index, where it was located, its new name and whether it is a retarget. */
export interface ScopedEntry {
  index: number;
  file: string;
  position: number;
  old: string;
  newName: string;
  retarget: boolean;
}

/** A scope's symbol table (internal in TypeScript's typings), and a local symbol's exported one. */
interface Scoped {
  locals?: Map<TS.__String, TS.Symbol>;
}
interface Exported {
  exportSymbol?: TS.Symbol;
}

/** A declaration in its scope: the scope's identity (a symbol table, or a side of a type), whether it is a type's
 * member, and the declarations of the new name the scope holds. */
interface Placed {
  entry: ScopedEntry;
  declaration: TS.Declaration;
  scope: object;
  member: boolean;
  existing: TS.Declaration[];
}

/** One identity per side (static, instance) of each type, every declaration merged into it included. */
const sides = new WeakMap<object, [object, object]>();

function sideOf(type: object, isStatic: boolean): object {
  const found = sides.get(type) ?? [{}, {}];
  sides.set(type, found);
  return found[isStatic ? 0 : 1];
}

const position = (d: TS.Declaration): { path: string; position: number } => {
  const source = d.getSourceFile();
  const name = ts().getNameOfDeclaration(d);
  return { path: source.fileName, position: name === undefined ? d.getStart(source) : nameStart(name, source) };
};

const keyAt = (d: TS.Declaration): string => {
  const at = position(d);
  return keyOf(at.path, at.position);
};

const isNamespace = (d: TS.Node): boolean => ts().isModuleDeclaration(d);

/** The language lets scope declarations `a` and `b` share one name: they merge or are overloads. */
function mayShare(a: TS.Node, b: TS.Node): boolean {
  const both = (test: (n: TS.Node) => boolean): boolean => test(a) && test(b);
  const pair = (x: (n: TS.Node) => boolean, y: (n: TS.Node) => boolean): boolean => (x(a) && y(b)) || (y(a) && x(b));
  if (both(ts().isInterfaceDeclaration) || pair(ts().isInterfaceDeclaration, ts().isClassDeclaration)) return true;
  if (both(ts().isEnumDeclaration) || both(ts().isFunctionDeclaration)) return true;
  return pair(isNamespace, (n) => isNamespace(n) || ts().isClassDeclaration(n) || ts().isFunctionDeclaration(n) || ts().isEnumDeclaration(n));
}

const overlaps = (a: TS.Node, b: TS.Node): boolean => (internals().getMeaningFromDeclaration(a) & internals().getMeaningFromDeclaration(b)) !== 0; // NOSONAR(S1529) — SemanticMeaning bitmask test

/** Member `d` of `holder` placed on its side, with the members of `spelled` that side of the type declares, in every
 * declaration merged into it. */
function placedMember(entry: ScopedEntry, d: TS.Declaration, holder: TS.Node, spelled: string, checker: TS.TypeChecker): Placed {
  const isStatic = !ts().isParameter(d) && hasStatic(d);
  const side = (m: TS.Node): boolean => (ts().isParameter(m) ? !isStatic : hasStatic(m) === isStatic);
  const type = checker.getTypeAtLocation(holder).getSymbol();
  const holders = (type?.declarations ?? []).filter((h) => h.kind === holder.kind || ts().isClassLike(h) || ts().isInterfaceDeclaration(h));
  const members = (holders.includes(holder as TS.Declaration) ? holders : [holder]).flatMap((h) => ownMembers(h));
  const existing = members.filter((m) => m !== d && side(m) && memberName(m, checker) === spelled);
  return { entry, declaration: d, scope: sideOf(type ?? holder, isStatic), member: true, existing: existing as TS.Declaration[] };
}

/** Declaration `d` of `symbol` placed in the scope whose table binds it, with the declarations of `spelled` that table
 * holds under a meaning `d` has; null when no table of an enclosing scope binds it. */
function placedLocal(entry: ScopedEntry, d: TS.Declaration, symbol: TS.Symbol, spelled: string): Placed | null {
  if (ts().isFunctionExpression(d) || ts().isClassExpression(d)) return null;
  for (let node = d.parent as TS.Node | undefined; node !== undefined; node = node.parent as TS.Node | undefined) {
    const locals = (node as Scoped).locals;
    const bound = locals?.get(symbol.escapedName);
    if (locals === undefined || bound === undefined) continue;
    if (bound !== symbol && (bound as Exported).exportSymbol !== symbol) return null;
    const other = locals.get(ts().escapeLeadingUnderscores(spelled));
    const declarations = ((other as Exported | undefined)?.exportSymbol ?? other)?.declarations ?? [];
    return { entry, declaration: d, scope: locals, member: false, existing: declarations.filter((e) => e !== d && overlaps(d, e) && !mayShare(d, e)) };
  }
  return null;
}

/** Each declaration of `entry`'s symbol in its scope; empty when the entry's file is in no program. */
function placed(r: Refactor, entry: ScopedEntry): Placed[] {
  const program = r.services(entry.file)[0]?.getProgram();
  const source = program?.getSourceFile(entry.file);
  if (program === undefined || source === undefined) return [];
  const checker = program.getTypeChecker();
  const symbol = symbolOf(checker, nodeAt(source, entry.position));
  const spelled = identifierText(entry.newName);
  return (symbol?.declarations ?? []).flatMap((d) => {
    const holder = holderOf(d);
    const found = holder === null ? placedLocal(entry, d, symbol as TS.Symbol, spelled) : placedMember(entry, d, holder, spelled, checker);
    return found === null ? [] : [found];
  });
}

/** Each `new_name` entry of `entries` (by its index) whose declaring scope holds its new name: a declaration no entry
 * renames to another name (the first one is named), else an earlier entry's renamed onto it (the latest entry's
 * finding, naming the earliest's first declaration). A pair with a declaration `kept`, or one the entries do not
 * decide, is left out. */
export function ownScopeConflicts(r: Refactor, entries: ScopedEntry[], kept: (path: string, position: number) => boolean): Map<number, NameConflict> {
  const all = entries.map((entry) => ({ entry, placed: placed(r, entry) }));
  const owner = new Map<string, ScopedEntry>();
  for (const { entry, placed: declared } of all) for (const p of declared) owner.set(keyAt(p.declaration), entry);
  const isKept = (d: TS.Declaration): boolean => kept(position(d).path, position(d).position);
  const byPlace = (a: TS.Declaration, b: TS.Declaration): number => byCodePoint(r.rel(position(a).path), r.rel(position(b).path)) || position(a).position - position(b).position;
  const out = new Map<number, NameConflict>();
  const meeting = new Map<object, Map<string, Placed[]>>();
  for (const { entry, placed: declared } of all) {
    if (entry.retarget || identifierText(entry.newName) === identifierText(entry.old)) continue;
    const spelled = identifierText(entry.newName);
    for (const p of declared) {
      const names = meeting.get(p.scope) ?? new Map<string, Placed[]>();
      names.set(spelled, [...(names.get(spelled) ?? []), p]);
      meeting.set(p.scope, names);
    }
    const existing = [...new Set(declared.flatMap((p) => p.existing))];
    if (declared.some((p) => isKept(p.declaration)) || existing.some(isKept)) continue;
    const renamed = existing.map((e) => owner.get(keyAt(e)));
    if (renamed.some((o) => o?.retarget === true)) continue;
    const staying = existing.filter((_, i) => renamed[i] === undefined || identifierText((renamed[i] as ScopedEntry).newName) === spelled);
    const first = staying.toSorted(byPlace)[0];
    if (first !== undefined) out.set(entry.index, { name: entry.newName, ...position(first) });
  }
  for (const names of meeting.values()) {
    for (const group of names.values()) {
      const shares = (a: Placed, b: Placed): boolean => !a.member && (!overlaps(a.declaration, b.declaration) || mayShare(a.declaration, b.declaration));
      const meets = group.filter((a) => group.some((b) => b.entry !== a.entry && !shares(a, b)));
      const indexes = [...new Set(meets.map((p) => p.entry.index))].sort((a, b) => a - b);
      if (indexes.length < 2 || meets.some((p) => isKept(p.declaration))) continue;
      const latest = (meets.find((p) => p.entry.index === indexes.at(-1)) as Placed).entry;
      const earliest = meets.filter((p) => p.entry.index === indexes[0]).map((p) => p.declaration).toSorted(byPlace)[0] as TS.Declaration;
      if (!out.has(latest.index)) out.set(latest.index, { name: latest.newName, ...position(earliest) });
    }
  }
  return out;
}
