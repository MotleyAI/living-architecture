// A word table's carve-outs against TypeScript declarations: what they keep, and the mentions they cover.
import type * as TS from 'typescript';
import { ts } from '../lang/index.js';
import type { Located } from './symbols.js';
import { type Carvable, carved, carveKey, heldWords, type WordTable } from './words.js';

/** The identifier a declaration declares; undefined for any other node, an object literal's member and an import or
 * export that binds the name it imports. */
export function declaredName(node: TS.Node): TS.Identifier | undefined {
  let name: TS.Node | undefined;
  if (ts().isVariableDeclaration(node) || ts().isBindingElement(node)) name = node.name;
  else if (ts().isParameter(node)) name = ts().isIndexSignatureDeclaration(node.parent) ? undefined : node.name;
  else if (ts().isImportSpecifier(node) || ts().isExportSpecifier(node)) name = node.propertyName === undefined ? undefined : node.name;
  else if (ts().isPropertyDeclaration(node) || ts().isMethodDeclaration(node) || ts().isAccessor(node) || ts().isPropertySignature(node) || ts().isMethodSignature(node)) {
    name = ts().isObjectLiteralExpression(node.parent) ? undefined : node.name;
  } else if (
    ts().isFunctionDeclaration(node) ||
    ts().isFunctionExpression(node) ||
    ts().isClassLike(node) ||
    ts().isInterfaceDeclaration(node) ||
    ts().isTypeAliasDeclaration(node) ||
    ts().isEnumDeclaration(node) ||
    ts().isEnumMember(node) ||
    ts().isModuleDeclaration(node) ||
    ts().isTypeParameterDeclaration(node) ||
    ts().isImportEqualsDeclaration(node) ||
    ts().isImportClause(node) ||
    ts().isNamespaceImport(node) ||
    ts().isNamespaceExport(node)
  ) {
    name = node.name;
  }
  return name !== undefined && ts().isIdentifier(name) ? name : undefined;
}

/** The written type annotation of a parameter, variable, field or property signature; null for any other declaration. */
export function annotationOf(node: TS.Node, source: TS.SourceFile): string | null {
  const annotated = ts().isParameter(node) || ts().isVariableDeclaration(node) || ts().isPropertyDeclaration(node) || ts().isPropertySignature(node);
  return annotated && node.type !== undefined ? node.type.getText(source) : null;
}

/** The declaration whose name holds `position`, from the innermost node there outwards. */
function declarationAt(source: TS.SourceFile, position: number): TS.Node | null {
  let node: TS.Node = source;
  for (;;) {
    const inner: TS.Node | undefined = ts().forEachChild(node, (child) => (child.getStart(source) <= position && position < child.end ? child : undefined));
    if (inner === undefined) break;
    node = inner;
  }
  for (let found: TS.Node | undefined = node; found !== undefined && !ts().isSourceFile(found); found = found.parent) {
    const name = (found as TS.NamedDeclaration).name;
    if (name !== undefined && name.getStart(source) <= position && position <= name.end) return found;
  }
  return null;
}

const holdsMembers = (node: TS.Node | undefined): node is TS.Node =>
  node !== undefined && (ts().isClassLike(node) || ts().isInterfaceDeclaration(node) || ts().isTypeLiteralNode(node) || ts().isEnumDeclaration(node));

const isFunction = (node: TS.Node): boolean => ts().isFunctionLike(node) && !ts().isIndexSignatureDeclaration(node);

/** The node whose scope declares `declaration`: the class of a member, the function of a parameter or local, else the file. */
function scopeOf(declaration: TS.Node, source: TS.SourceFile): TS.Node {
  const parent = declaration.parent as TS.Node | undefined;
  if (ts().isParameter(declaration) && ts().isParameterPropertyDeclaration(declaration, declaration.parent)) return declaration.parent.parent;
  if (holdsMembers(parent) && !ts().isParameter(declaration)) return parent;
  for (let node = parent; node !== undefined; node = node.parent) if (isFunction(node)) return node;
  return source;
}

/** A scope's span: the file, or a class or function from its first decorator or attached JSDoc comment to its end. */
function span(scope: TS.Node, source: TS.SourceFile): [number, number] {
  if (ts().isSourceFile(scope)) return [0, source.text.length];
  let node = scope;
  if (ts().isTypeLiteralNode(node) && ts().isTypeAliasDeclaration(node.parent)) node = node.parent;
  const declared = node.parent as TS.Node | undefined;
  const valued = (ts().isArrowFunction(node) || ts().isFunctionExpression(node)) && declared !== undefined && ts().isVariableDeclaration(declared) && declared.initializer === node;
  if (valued) {
    const list = declared.parent;
    if (ts().isVariableDeclarationList(list) && list.declarations.length === 1 && ts().isVariableStatement(list.parent)) node = list.parent;
  }
  return [node.getStart(source, true), node.end];
}

/** Each carve-out's located symbols, as keys; `locate` raises LocatorError for a path that names nothing or is a
 * wildcard. */
export function locateCarveSymbols(table: WordTable, locate: (file: string, symbol: string) => Located): Set<string>[] {
  return table.carveOuts.map((carve) => new Set((carve.symbols ?? []).map(({ file, symbol }) => {
    const found = locate(file, symbol);
    return carveKey(found.file, found.position);
  })));
}

/** A table's carve-outs over a run's sources; `rel` gives a file's project-relative path. */
export class Carving {
  constructor(
    readonly table: WordTable,
    private readonly located: Set<string>[],
    private readonly rel: (path: string) => string,
  ) {}

  /** What the carve-outs are matched against for `declaration`. */
  private carvable(declaration: TS.Node, source: TS.SourceFile): Carvable {
    const name = (declaration as TS.NamedDeclaration).name;
    const keys = name === undefined ? [] : [carveKey(source.fileName, name.getStart(source))];
    return { rel: this.rel(source.fileName), annotation: annotationOf(declaration, source), keys };
  }

  /** A carve-out keeps a word of `old` for `declaration`. */
  private keepsDeclaration(declaration: TS.Node, source: TS.SourceFile, old: string): boolean {
    const found = this.carvable(declaration, source);
    return heldWords(old, this.table.words).some((word) => carved(this.table, this.located, word, found) !== null);
  }

  /** A carve-out keeps a word of `old` for the declaration named at `position` of `source`. */
  keeps(source: TS.SourceFile, position: number, old: string): boolean {
    const declaration = declarationAt(source, position);
    return declaration !== null && this.keepsDeclaration(declaration, source, old);
  }

  /** The spans of `source` whose mentions of `old` a carve-out covers: the file under a carved path, and the scope
   * declaring each carved declaration named `old`. */
  covered(source: TS.SourceFile, old: string): [number, number][] {
    const whole: Carvable = { rel: this.rel(source.fileName), annotation: null, keys: [] };
    if (heldWords(old, this.table.words).some((word) => carved(this.table, [], word, whole) !== null)) return [[0, source.text.length]];
    const out: [number, number][] = [];
    const visit = (node: TS.Node): void => {
      const name = (node as TS.NamedDeclaration).name;
      const named = name !== undefined && (ts().isIdentifier(name) || ts().isStringLiteral(name)) && name.text === old;
      if (named && this.keepsDeclaration(node, source, old)) out.push(span(scopeOf(node, source), source));
      ts().forEachChild(node, visit);
    };
    visit(source);
    return out;
  }
}

/** `node` carries a decorator spelled as one of `names` (dotted), bare or called. */
export function decoratedBy(node: TS.Node, source: TS.SourceFile, names: string[]): boolean {
  const decorators = ts().canHaveDecorators(node) ? (ts().getDecorators(node) ?? []) : [];
  return decorators.some((d) => names.includes((ts().isCallExpression(d.expression) ? d.expression.expression : d.expression).getText(source)));
}

/** The declaration named at `position` of `source` is a fixture: decorated by one of `names`. */
export function fixtureAt(source: TS.SourceFile, position: number, names: string[]): boolean {
  const declaration = names.length === 0 ? null : declarationAt(source, position);
  return declaration !== null && decoratedBy(declaration, source, names);
}
