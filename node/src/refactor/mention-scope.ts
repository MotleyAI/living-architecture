// Where a `--docs` mention belongs: the classes owning a position, a class's lookup of a member, a file's
// module-level declarations of a name, and the sites of declared string forms.
import type * as TS from 'typescript';
import { ts } from '../lang/index.js';
import { walk } from './members.js';
import type { Region } from './mentions.js';

/** A class, interface or type literal and the span it owns: its declaration with the JSDoc attached to it. */
export interface OwnerSpan {
  start: number;
  end: number;
  node: TS.Node;
}

const isOwner = (node: TS.Node): boolean => ts().isClassLike(node) || ts().isInterfaceDeclaration(node) || ts().isTypeLiteralNode(node);

/** The owners of `source`. */
export function ownerSpans(source: TS.SourceFile): OwnerSpan[] {
  const out: OwnerSpan[] = [];
  for (const node of walk(source)) {
    if (!isOwner(node)) continue;
    const anchor = ts().isTypeLiteralNode(node) && ts().isTypeAliasDeclaration(node.parent) ? node.parent : node;
    const docs = ts().getJSDocCommentsAndTags(anchor).filter((doc) => ts().isJSDoc(doc));
    out.push({ start: Math.min(anchor.getStart(source), ...docs.map((doc) => doc.getStart(source))), end: anchor.end, node });
  }
  return out;
}

/** A declaration of `node`'s symbol extends a type the checker cannot resolve, directly or through its bases. */
function unresolvedBase(checker: TS.TypeChecker, node: TS.Node, seen: Set<TS.Node>): boolean {
  if (seen.has(node) || !(ts().isClassLike(node) || ts().isInterfaceDeclaration(node))) return false;
  seen.add(node);
  for (const clause of node.heritageClauses ?? []) {
    if (clause.token !== ts().SyntaxKind.ExtendsKeyword) continue;
    for (const base of clause.types) {
      const written = checker.getTypeAtLocation(ts().isClassLike(node) ? base.expression : base);
      if ((written.flags & ts().TypeFlags.Any) !== 0) return true;
      const declarations = checker.getTypeAtLocation(base).symbol?.declarations ?? [];
      if (declarations.some((d) => unresolvedBase(checker, d, seen))) return true;
    }
  }
  return false;
}

/** The declarations `owner`'s property lookup of `name` lands on (instance side, then a class's static side); null
 * when it has no such member, 'incomplete' when a base that could hold it does not resolve. */
export function lookup(checker: TS.TypeChecker, owner: TS.Node, name: string): TS.Declaration[] | 'incomplete' | null {
  const type = checker.getTypeAtLocation(owner);
  const symbol = type.symbol as TS.Symbol | undefined;
  const statics = ts().isClassLike(owner) && symbol !== undefined ? checker.getTypeOfSymbolAtLocation(symbol, owner).getProperty(name) : undefined;
  const found = [type.getProperty(name), statics].flatMap((property) => property?.declarations ?? []);
  if (found.length > 0) return found;
  const seen = new Set<TS.Node>();
  return [owner, ...(symbol?.declarations ?? [])].some((d) => unresolvedBase(checker, d, seen)) ? 'incomplete' : null;
}

/** The start of each module-level declaration of `name` in `source`. */
export function topDeclarations(source: TS.SourceFile, name: string): number[] {
  const out: number[] = [];
  const add = (declared: TS.Node | undefined): void => {
    if (declared !== undefined && ts().isIdentifier(declared) && declared.text === name) out.push(declared.getStart(source));
  };
  for (const statement of source.statements) {
    if (ts().isVariableStatement(statement)) for (const d of statement.declarationList.declarations) add(d.name);
    else if (
      ts().isFunctionDeclaration(statement) ||
      ts().isClassDeclaration(statement) ||
      ts().isInterfaceDeclaration(statement) ||
      ts().isTypeAliasDeclaration(statement) ||
      ts().isEnumDeclaration(statement) ||
      ts().isModuleDeclaration(statement)
    ) {
      add(statement.name);
    }
  }
  return out;
}

const ASCII = /^[\0-\x7F]*$/u;

/** The spans of `old` as the symbol group of a form matching in a string region of `text`; none in a non-ASCII one. */
export function formSites(text: string, region: Region, old: string, forms: RegExp[]): [number, number][] {
  const part = text.slice(region.start, region.end);
  if (region.where !== 'string' || !part.includes(old) || !ASCII.test(part)) return [];
  const out: [number, number][] = [];
  for (const form of forms) {
    for (const match of part.matchAll(form)) {
      const span = match.indices?.[1];
      if (match[1] === old && span !== undefined) out.push([region.start + span[0], region.start + span[1]]);
    }
  }
  return out;
}

/** `refactor.string_forms` patterns compiled to search a literal part and report the symbol group's span. */
export const compileForms = (patterns: string[]): RegExp[] => patterns.map((pattern) => new RegExp(pattern, 'dg'));
