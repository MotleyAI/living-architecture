// `--symbol Q`: a declaration located by its path inside a TypeScript file (`Class.method`, `fn.<locals>.inner`,
// `fn(param)`, `Alias['value']`); declarations the checker resolves to one symbol are one symbol.
import type * as TS from 'typescript';
import { byCodePoint, message } from '../contract/index.js';
import { ts } from '../lang/index.js';
import { Lines } from './lines.js';

export const LOCALS = '<locals>';
const PATH = /^(?<path>[^()[\]]+)(?:\((?<param>[^()]+)\))?(?:\[(?<quote>['"])(?<value>.*)\k<quote>\])?$/su;

/** The path names no declaration, or more than one symbol; the message is user-facing (exit 2). */
export class LocatorError extends Error {}

export interface SymbolPath {
  segments: string[];
  param: string | null;
  value: string | null;
}

export function parsePath(raw: string): SymbolPath | null {
  const m = PATH.exec(raw.trim());
  if (m?.groups === undefined) return null;
  const segments = (m.groups.path ?? '').split('.').map((s) => s.trim());
  if (segments.includes('') || segments[0] === LOCALS || segments.at(-1) === LOCALS) return null;
  return { segments, param: m.groups.param?.trim() ?? null, value: m.groups.value ?? null };
}

/** What a path names: the position of the declaration's name (or inside the literal member's string) in `file`. */
export interface Located {
  file: string;
  position: number;
  topLevel: boolean;
}

interface Declaration {
  name: string;
  node: TS.Node;
  nameNode: TS.Node;
}

const isFunctionLike = (node: TS.Node): node is TS.SignatureDeclaration & { body?: TS.Node } =>
  ts().isFunctionDeclaration(node) ||
  ts().isMethodDeclaration(node) ||
  ts().isConstructorDeclaration(node) ||
  ts().isGetAccessorDeclaration(node) ||
  ts().isSetAccessorDeclaration(node) ||
  ts().isFunctionExpression(node) ||
  ts().isArrowFunction(node);

function nameText(name: TS.Node | undefined): string | null {
  if (name === undefined) return null;
  if (ts().isIdentifier(name) || ts().isStringLiteral(name) || ts().isNumericLiteral(name) || ts().isPrivateIdentifier(name)) return name.text;
  return null;
}

function declaration(node: TS.Node, name: TS.Node | undefined): Declaration[] {
  const text = nameText(name);
  return text === null || name === undefined ? [] : [{ name: text, node, nameNode: name }];
}

/** The identifiers a binding name declares, destructuring entered. */
function bindingNames(node: TS.Node, name: TS.BindingName): Declaration[] {
  if (ts().isIdentifier(name)) return declaration(node, name);
  return name.elements.flatMap((element) => (ts().isOmittedExpression(element) ? [] : bindingNames(element, element.name)));
}

type NamedStatement =
  | TS.FunctionDeclaration
  | TS.ClassDeclaration
  | TS.InterfaceDeclaration
  | TS.TypeAliasDeclaration
  | TS.EnumDeclaration
  | TS.ModuleDeclaration
  | TS.ImportEqualsDeclaration;

const isNamedStatement = (node: TS.Node): node is NamedStatement =>
  ts().isFunctionDeclaration(node) ||
  ts().isClassDeclaration(node) ||
  ts().isInterfaceDeclaration(node) ||
  ts().isTypeAliasDeclaration(node) ||
  ts().isEnumDeclaration(node) ||
  ts().isModuleDeclaration(node) ||
  ts().isImportEqualsDeclaration(node);

function importDeclarations(node: TS.ImportDeclaration): Declaration[] {
  const clause = node.importClause;
  const bindings = clause?.namedBindings;
  if (clause === undefined) return [];
  const named = bindings !== undefined && ts().isNamedImports(bindings) ? bindings.elements.flatMap((s) => declaration(s, s.name)) : [];
  const namespace = bindings !== undefined && ts().isNamespaceImport(bindings) ? declaration(bindings, bindings.name) : [];
  return [...declaration(clause, clause.name), ...namespace, ...named];
}

/** The names a statement itself declares; null for a statement that declares none. */
function ownDeclarations(node: TS.Node): Declaration[] | null {
  if (ts().isVariableStatement(node)) return node.declarationList.declarations.flatMap((d) => bindingNames(d, d.name));
  if (ts().isVariableDeclarationList(node)) return node.declarations.flatMap((d) => bindingNames(d, d.name));
  if (isNamedStatement(node)) return declaration(node, node.name);
  if (ts().isImportDeclaration(node)) return importDeclarations(node);
  return null;
}

/** The declarations of a statement list, blocks and control flow entered when `nested`, nested functions not. */
function statementDeclarations(statements: readonly TS.Node[], nested: boolean): Declaration[] {
  const out: Declaration[] = [];
  const visit = (node: TS.Node): void => {
    const own = ownDeclarations(node);
    if (own !== null) out.push(...own);
    else if (nested && !isFunctionLike(node) && !ts().isClassLike(node)) ts().forEachChild(node, visit);
  };
  for (const statement of statements) visit(statement);
  return out;
}

/** A scope a segment looks names up in: a file, namespace, class, interface, type literal, enum or function body. */
type Scope = TS.Node;

function namespaceMembers(scope: TS.ModuleDeclaration): Declaration[] {
  const body = scope.body;
  if (body === undefined) return [];
  if (ts().isModuleBlock(body)) return statementDeclarations(body.statements, false);
  return ts().isModuleDeclaration(body) ? declaration(body, body.name) : [];
}

/** A class's, interface's or type literal's members, a class's parameter properties included. */
function typeMembers(scope: TS.ClassLikeDeclaration | TS.InterfaceDeclaration | TS.TypeLiteralNode): Declaration[] {
  const out = (scope.members as TS.NodeArray<TS.Node>).flatMap((m) => declaration(m, (m as TS.NamedDeclaration).name));
  const constructor = ts().isClassLike(scope) ? scope.members.find(ts().isConstructorDeclaration) : undefined;
  const properties = (constructor?.parameters ?? []).filter((p) => ts().isParameterPropertyDeclaration(p, p.parent));
  return [...out, ...properties.flatMap((p) => declaration(p, p.name))];
}

function members(scope: Scope): Declaration[] {
  if (ts().isSourceFile(scope)) return statementDeclarations(scope.statements, false);
  if (ts().isModuleDeclaration(scope)) return namespaceMembers(scope);
  if (ts().isClassLike(scope) || ts().isInterfaceDeclaration(scope) || ts().isTypeLiteralNode(scope)) return typeMembers(scope);
  if (ts().isEnumDeclaration(scope)) return scope.members.flatMap((m) => declaration(m, m.name));
  return [];
}

/** The function body a declaration's `<locals>` are in: a function, method, accessor, or a variable's function value. */
function functionOf(node: TS.Node): TS.Node | null {
  if (isFunctionLike(node)) return node;
  if (ts().isVariableDeclaration(node) && node.initializer !== undefined) {
    const value = node.initializer;
    if (ts().isArrowFunction(value) || ts().isFunctionExpression(value)) return value;
  }
  return null;
}

function locals(fn: TS.Node): Declaration[] {
  const body = (fn as { body?: TS.Node }).body;
  if (body === undefined) return [];
  return ts().isBlock(body) ? statementDeclarations(body.statements, true) : [];
}

/** The scopes a declaration opens for a member segment: its own body, or the type literal a type alias names. */
function memberScopes(node: TS.Node): Scope[] {
  if (ts().isTypeAliasDeclaration(node)) return ts().isTypeLiteralNode(node.type) ? [node.type] : [];
  if (ts().isClassLike(node) || ts().isInterfaceDeclaration(node) || ts().isEnumDeclaration(node) || ts().isModuleDeclaration(node)) return [node];
  return [];
}

type Lookup = (scope: Scope) => Declaration[];

const lookup: Lookup = (scope) => (ts().isSourceFile(scope) || !isFunctionLike(scope) ? members(scope) : locals(scope));

/** The declarations grouped by the checker's symbol, in source order. */
function bySymbol(checker: TS.TypeChecker, found: Declaration[]): Declaration[][] {
  const groups = new Map<TS.Symbol | TS.Node, Declaration[]>();
  for (const d of found.toSorted((a, b) => a.nameNode.getStart() - b.nameNode.getStart())) {
    const key = checker.getSymbolAtLocation(d.nameNode) ?? d.nameNode;
    groups.set(key, [...(groups.get(key) ?? []), d]);
  }
  return [...groups.values()];
}

const IMPORTS = (node: TS.Node): boolean =>
  ts().isImportSpecifier(node) || ts().isImportClause(node) || ts().isNamespaceImport(node) || ts().isImportEqualsDeclaration(node);

/** The declaration an import binding names, followed through its alias; the binding itself when it resolves outside sources. */
function imported(checker: TS.TypeChecker, d: Declaration): Located | null {
  const symbol = checker.getSymbolAtLocation(d.nameNode);
  if (symbol === undefined || (symbol.flags & ts().SymbolFlags.Alias) === 0) return null; // NOSONAR(S1529) — SymbolFlags bitmask test
  const target = checker.getAliasedSymbol(symbol).declarations?.[0];
  const name = target === undefined ? undefined : ts().getNameOfDeclaration(target as TS.Declaration);
  const source = target?.getSourceFile();
  if (name === undefined || source === undefined || source.isDeclarationFile) return null;
  return { file: source.fileName, position: name.getStart(source), topLevel: false };
}

/** The declaration `raw` names in `source`; LocatorError when it names none or more than one symbol. */
export function locate(checker: TS.TypeChecker, source: TS.SourceFile, raw: string, shown: string): Located {
  const path = parsePath(raw);
  const unresolved = (names: Iterable<string>): LocatorError =>
    new LocatorError(message('refactor.symbol-unresolved', { path: shown, symbol: raw, candidates: [...new Set(names)].sort(byCodePoint).join(', ') }));
  if (path === null) throw unresolved(members(source).map((d) => d.name));
  const { segments } = path;
  const groups = walk(checker, source, segments, unresolved);
  if (groups.length > 1) {
    const lines = new Lines(source.text);
    const sites = groups.map((g) => `${shown}:${lines.lineOf((g[0] as Declaration).nameNode.getStart(source))}`);
    throw new LocatorError(message('refactor.symbol-ambiguous', { path: shown, symbol: raw, candidates: sites.join(', ') }));
  }
  const group = groups[0] as Declaration[];
  if (path.param !== null) {
    const param = parameter(group, path.param, unresolved);
    if (path.value !== null) return literalMember(source, [param], path.value, unresolved);
    return { file: source.fileName, position: param.nameNode.getStart(source), topLevel: false };
  }
  if (path.value !== null) return literalMember(source, group, path.value, unresolved);
  const first = group[0] as Declaration;
  if (IMPORTS(first.node)) {
    const target = imported(checker, first);
    if (target !== null) return target;
  }
  return { file: source.fileName, position: first.nameNode.getStart(source), topLevel: segments.length === 1 && !IMPORTS(first.node) };
}

/** The symbols (declaration groups) the segments reach from the file. */
function walk(checker: TS.TypeChecker, source: TS.SourceFile, segments: string[], unresolved: (names: Iterable<string>) => LocatorError): Declaration[][] {
  let scopes: Scope[] = [source];
  for (let i = 0; ; ) {
    const found = scopes.flatMap(lookup);
    const groups = bySymbol(checker, found.filter((d) => d.name === segments[i]));
    if (groups.length === 0) throw unresolved(found.map((d) => d.name));
    i += 1;
    if (i === segments.length) return groups;
    const viaLocals = segments[i] === LOCALS;
    if (viaLocals) i += 1;
    const nodes = groups.flat().map((d) => d.node);
    scopes = viaLocals ? nodes.flatMap((n) => functionOf(n) ?? []) : nodes.flatMap(memberScopes);
    if (scopes.length === 0) {
      const opened = [...nodes.flatMap((n) => functionOf(n) ?? []), ...nodes.flatMap(memberScopes)];
      throw unresolved(opened.flatMap(lookup).map((d) => d.name));
    }
  }
}

function parameter(group: Declaration[], name: string, unresolved: (names: Iterable<string>) => LocatorError): Declaration {
  const params = group.flatMap((d) => {
    const fn = functionOf(d.node);
    return fn === null ? [] : (fn as TS.SignatureDeclaration).parameters.flatMap((p) => bindingNames(p, p.name));
  });
  const found = params.find((p) => p.name === name);
  if (found === undefined) throw unresolved(params.map((p) => p.name));
  return found;
}

/** Inside the string `value` of a string-literal type in the declaration's annotation or alias body. */
function literalMember(source: TS.SourceFile, group: Declaration[], value: string, unresolved: (names: Iterable<string>) => LocatorError): Located {
  const strings: TS.StringLiteral[] = [];
  const collect = (node: TS.Node): void => {
    if (ts().isLiteralTypeNode(node) && ts().isStringLiteral(node.literal)) strings.push(node.literal);
    ts().forEachChild(node, collect);
  };
  for (const d of group) {
    const type = (d.node as { type?: TS.Node }).type;
    if (type !== undefined) collect(type);
  }
  const found = strings.find((s) => s.text === value);
  if (found === undefined) throw unresolved(strings.map((s) => s.text));
  return { file: source.fileName, position: found.getStart(source) + 1, topLevel: false };
}
