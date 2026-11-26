// Where a `--docs` mention belongs: the classes owning a position, a class's lookup of a member, a file's
// module-level declarations of a name, and the sites of declared string forms.
import type * as TS from 'typescript';
import { ts } from '../lang/index.js';
import { isAny, walk } from './members.js';
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

type Heritage = TS.ClassLikeDeclaration | TS.InterfaceDeclaration;

const heritage = (node: TS.Node): node is Heritage => ts().isClassLike(node) || ts().isInterfaceDeclaration(node);

/** Each extended base of `declarations` in order: the node whose type shows whether it resolves, and the base. */
function* bases(declarations: Heritage[]): Generator<[TS.Node, TS.ExpressionWithTypeArguments]> {
  for (const declaration of declarations) {
    for (const clause of declaration.heritageClauses ?? []) {
      if (clause.token !== ts().SyntaxKind.ExtendsKeyword) continue;
      for (const base of clause.types) yield [ts().isClassLike(declaration) ? base.expression : base, base];
    }
  }
}

/** Walking `node`'s bases in order: false once a type declares `name`, true at an unresolved base before that;
 * undefined when the walk meets neither. */
function blocked(checker: TS.TypeChecker, node: TS.Node, name: TS.__String, seen: Set<TS.Node>): boolean | undefined {
  if (seen.has(node) || !heritage(node)) return undefined;
  const symbol = checker.getTypeAtLocation(node).symbol as TS.Symbol | undefined;
  if (symbol?.members?.has(name) === true || symbol?.exports?.has(name) === true) return false;
  const merged = (symbol?.declarations ?? [node]).filter(heritage);
  for (const declaration of merged) seen.add(declaration);
  for (const [written, base] of bases(merged)) {
    if (isAny(checker, written)) return true;
    const declarations = checker.getTypeAtLocation(base).symbol?.declarations ?? [];
    const state = declarations.map((d) => blocked(checker, d, name, seen)).find((found) => found !== undefined);
    if (state !== undefined) return state;
  }
  return undefined;
}

/** The declarations `owner`'s property lookup of `name` lands on (its instance side and a class's static side); null
 * when it has no such member, 'incomplete' when a base that could hold it first does not resolve. */
export function lookup(checker: TS.TypeChecker, owner: TS.Node, name: string): TS.Declaration[] | 'incomplete' | null {
  if (blocked(checker, owner, ts().escapeLeadingUnderscores(name), new Set()) === true) return 'incomplete';
  const type = checker.getTypeAtLocation(owner);
  const symbol = type.symbol as TS.Symbol | undefined;
  const statics = ts().isClassLike(owner) && symbol !== undefined ? checker.getTypeOfSymbolAtLocation(symbol, owner).getProperty(name) : undefined;
  const found = [type.getProperty(name), statics].flatMap((property) => property?.declarations ?? []);
  return found.length > 0 ? found : null;
}

/** The identifiers `declared` binds, through destructuring. */
function bound(declared: TS.Node | undefined): TS.Identifier[] {
  if (declared === undefined) return [];
  if (ts().isIdentifier(declared)) return [declared];
  if (!ts().isObjectBindingPattern(declared) && !ts().isArrayBindingPattern(declared)) return [];
  return declared.elements.flatMap((element) => (ts().isBindingElement(element) ? bound(element.name) : []));
}

/** The binding names of an import declaration. */
function imported(statement: TS.ImportDeclaration): (TS.Node | undefined)[] {
  const bindings = statement.importClause?.namedBindings;
  const named = bindings !== undefined && ts().isNamedImports(bindings) ? bindings.elements : [];
  return [statement.importClause?.name, bindings !== undefined && ts().isNamespaceImport(bindings) ? bindings.name : undefined, ...named.map((e) => e.name)];
}

/** The binding names a module-level statement declares. */
function declared(statement: TS.Statement): (TS.Node | undefined)[] {
  if (ts().isVariableStatement(statement)) return statement.declarationList.declarations.map((d) => d.name);
  if (ts().isImportDeclaration(statement)) return imported(statement);
  const named =
    ts().isImportEqualsDeclaration(statement) ||
    ts().isFunctionDeclaration(statement) ||
    ts().isClassDeclaration(statement) ||
    ts().isInterfaceDeclaration(statement) ||
    ts().isTypeAliasDeclaration(statement) ||
    ts().isEnumDeclaration(statement) ||
    ts().isModuleDeclaration(statement);
  return named ? [statement.name] : [];
}

/** The start of each module-level declaration of `name` in `source`, import bindings included. */
export function topDeclarations(source: TS.SourceFile, name: string): number[] {
  const names = source.statements.flatMap(declared).flatMap(bound);
  return names.filter((identifier) => identifier.text === name).map((identifier) => identifier.getStart(source));
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
