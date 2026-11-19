// `--symbol Q`: a declaration located by its path inside a TypeScript file (`Class.method`, `fn.<locals>.inner`,
// `fn(param)`, `Alias['value']`), or every local of a name by a wildcard path (`*.<locals>.name`); declarations the
// checker resolves to one symbol are one symbol, and without a checker those one scope declares.
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

/** A wildcard path's parts: `scope.*.<locals>.name`, the scope empty for the whole file. */
export interface WildcardPath {
  scope: string[];
  name: string;
}

/** `raw` as a wildcard path; null for any other path, a misplaced `*` included. */
export function wildcardPath(raw: string): WildcardPath | null {
  const path = parsePath(raw);
  if (path?.param !== null || path.value !== null) return null;
  const scope = path.segments.slice(0, -3);
  const [star, step, name = ''] = path.segments.slice(-3);
  if (path.segments.length < 3 || star !== '*' || step !== LOCALS || name === '*') return null;
  return scope.includes('*') || scope.at(-1) === LOCALS ? null : { scope, name };
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
  /** The scope it was looked up in. */
  scope?: TS.Node;
}

const isFunctionLike = (node: TS.Node): node is TS.SignatureDeclaration & { body?: TS.Node } =>
  ts().isFunctionDeclaration(node) ||
  ts().isMethodDeclaration(node) ||
  ts().isConstructorDeclaration(node) ||
  ts().isGetAccessorDeclaration(node) ||
  ts().isSetAccessorDeclaration(node) ||
  ts().isFunctionExpression(node) ||
  ts().isArrowFunction(node) ||
  ts().isMethodSignature(node) ||
  ts().isCallSignatureDeclaration(node) ||
  ts().isConstructSignatureDeclaration(node);

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

/** The names an `export { ... } from` re-exports; none for a local export, which declares nothing. */
function reexportDeclarations(node: TS.ExportDeclaration): Declaration[] {
  const clause = node.exportClause;
  if (node.moduleSpecifier === undefined || clause === undefined || !ts().isNamedExports(clause)) return [];
  return clause.elements.flatMap((s) => declaration(s, s.name));
}

/** The names a statement itself declares; null for a statement that declares none. */
function ownDeclarations(node: TS.Node): Declaration[] | null {
  if (ts().isVariableStatement(node)) return node.declarationList.declarations.flatMap((d) => bindingNames(d, d.name));
  if (ts().isVariableDeclarationList(node)) return node.declarations.flatMap((d) => bindingNames(d, d.name));
  if (isNamedStatement(node)) return declaration(node, node.name);
  if (ts().isImportDeclaration(node)) return importDeclarations(node);
  if (ts().isExportDeclaration(node)) return reexportDeclarations(node);
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

const lookupIn = (scope: Scope): Declaration[] => lookup(scope).map((d) => ({ ...d, scope }));

const ids = new WeakMap<TS.Node, number>();
let nextId = 0;

function idOf(node: TS.Node): string {
  let id = ids.get(node);
  if (id === undefined) {
    nextId += 1;
    id = nextId;
    ids.set(node, id);
  }
  return `#${id}`;
}

const opensBlock = (node: TS.Node): boolean =>
  ts().isBlock(node) ||
  ts().isSourceFile(node) ||
  ts().isModuleBlock(node) ||
  ts().isCaseBlock(node) ||
  ts().isForStatement(node) ||
  ts().isForInStatement(node) ||
  ts().isForOfStatement(node) ||
  ts().isCatchClause(node) ||
  isFunctionLike(node);

/** The block, loop or function whose scope a local declaration is in; a `var`'s is its function. */
function blockOf(node: TS.Node): TS.Node {
  let declared: TS.Node = node;
  while (ts().isBindingElement(declared) || ts().isObjectBindingPattern(declared) || ts().isArrayBindingPattern(declared)) declared = declared.parent;
  const list = ts().isVariableDeclaration(declared) && ts().isVariableDeclarationList(declared.parent) ? declared.parent : undefined;
  const hoisted = list !== undefined && (list.flags & ts().NodeFlags.BlockScoped) === 0; // NOSONAR(S1529) — NodeFlags bitmask test
  let scope = (list ?? declared).parent as TS.Node | undefined;
  while (scope !== undefined && !(hoisted ? isFunctionLike(scope) || ts().isSourceFile(scope) || ts().isModuleBlock(scope) : opensBlock(scope))) scope = scope.parent;
  return scope ?? node.getSourceFile();
}

/** A member scope's key: equal for the declarations that merge (a namespace's blocks, an interface's bodies). */
function scopeKey(scope: Scope): string {
  if (ts().isSourceFile(scope)) return '';
  if (ts().isTypeLiteralNode(scope)) return ts().isTypeAliasDeclaration(scope.parent) ? `${scopeKey(scope.parent)}{}` : idOf(scope);
  const name = nameText((scope as TS.NamedDeclaration).name);
  if (name === null) return idOf(scope);
  const parent = scope.parent as TS.Node | undefined;
  if (parent === undefined || ts().isSourceFile(parent)) return `/${name}`;
  if (ts().isModuleBlock(parent)) return `${scopeKey(parent.parent)}/${name}`;
  return ts().isModuleDeclaration(parent) ? `${scopeKey(parent)}/${name}` : `${idOf(blockOf(scope))}/${name}`;
}

const isStatic = (node: TS.Node): boolean => ts().canHaveModifiers(node) && (ts().getModifiers(node) ?? []).some((m) => m.kind === ts().SyntaxKind.StaticKeyword);

/** A declaration's symbol read from syntax: its scope, a function's local by its block, and its name. */
function syntacticKey(d: Declaration): string {
  const scope = d.scope ?? d.node.getSourceFile();
  const home = ts().isSourceFile(scope) || !isFunctionLike(scope) ? scopeKey(scope) : idOf(blockOf(d.node));
  return `${home}|${isStatic(d.node) ? 'static ' : ''}${d.name}`;
}

/** The declarations grouped by the checker's symbol (without one, by scope and name), in source order. */
function bySymbol(checker: TS.TypeChecker | null, found: Declaration[]): Declaration[][] {
  const groups = new Map<TS.Symbol | TS.Node | string, Declaration[]>();
  for (const d of found.toSorted((a, b) => a.nameNode.getStart() - b.nameNode.getStart())) {
    const key = checker === null ? syntacticKey(d) : (checker.getSymbolAtLocation(d.nameNode) ?? d.nameNode);
    groups.set(key, [...(groups.get(key) ?? []), d]);
  }
  return [...groups.values()];
}

const IMPORTS = (node: TS.Node): boolean =>
  ts().isImportSpecifier(node) || ts().isImportClause(node) || ts().isNamespaceImport(node) || ts().isImportEqualsDeclaration(node) || ts().isExportSpecifier(node);

/** The declaration an import binding names, followed through its alias; the binding itself when it resolves outside sources. */
function imported(checker: TS.TypeChecker | null, d: Declaration): Located | null {
  if (checker === null) return null;
  const symbol = checker.getSymbolAtLocation(d.nameNode);
  if (symbol === undefined || (symbol.flags & ts().SymbolFlags.Alias) === 0) return null; // NOSONAR(S1529) — SymbolFlags bitmask test
  const target = checker.getAliasedSymbol(symbol).declarations?.[0];
  const name = target === undefined ? undefined : ts().getNameOfDeclaration(target as TS.Declaration);
  const source = target?.getSourceFile();
  if (name === undefined || source === undefined || source.isDeclarationFile) return null;
  return { file: source.fileName, position: name.getStart(source), topLevel: false };
}

type Unresolved = (names: Iterable<string>) => LocatorError;

const unresolvedAs = (raw: string, shown: string): Unresolved => (names) =>
  new LocatorError(message('refactor.symbol-unresolved', { path: shown, symbol: raw, candidates: [...new Set(names)].sort(byCodePoint).join(', ') }));

/** The declaration `raw` names in `source` (by syntax alone without a `checker`), an import or re-export followed to
 * what it names unless `follow` is false; LocatorError when it names none or more than one symbol, or is a wildcard. */
export function locate(checker: TS.TypeChecker | null, source: TS.SourceFile, raw: string, shown: string, follow = true): Located {
  if (wildcardPath(raw) !== null) throw new LocatorError(message('refactor.symbol-wildcard', { path: shown, symbol: raw }));
  const path = parsePath(raw);
  const unresolved = unresolvedAs(raw, shown);
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
  if (follow && IMPORTS(first.node)) {
    const target = imported(checker, first);
    if (target !== null) return target;
  }
  return { file: source.fileName, position: first.nameNode.getStart(source), topLevel: segments.length === 1 && !IMPORTS(first.node) };
}

/** The symbols (declaration groups) the segments reach from the file. */
function walk(checker: TS.TypeChecker | null, source: TS.SourceFile, segments: string[], unresolved: Unresolved): Declaration[][] {
  let scopes: Scope[] = [source];
  for (let i = 0; ; ) {
    const found = scopes.flatMap(lookupIn);
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

function parameter(group: Declaration[], name: string, unresolved: Unresolved): Declaration {
  const params = group.flatMap((d) => {
    const fn = functionOf(d.node);
    return fn === null ? [] : (fn as TS.SignatureDeclaration).parameters.flatMap((p) => bindingNames(p, p.name));
  });
  const found = params.find((p) => p.name === name);
  if (found === undefined) throw unresolved(params.map((p) => p.name));
  return found;
}

/** Inside the string `value` of a string-literal type in the declaration's annotation or alias body. */
function literalMember(source: TS.SourceFile, group: Declaration[], value: string, unresolved: Unresolved): Located {
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

/** The scopes a declaration opens, whatever the next step: its function body and its members. */
const opened = (node: TS.Node): Scope[] => [...(functionOf(node) === null ? [] : [functionOf(node) as TS.Node]), ...memberScopes(node)];

/** Every local a wildcard path names in `source`, one per symbol in source order; LocatorError when it names none,
 * listing the names its scope, or the file, declares. */
export function locateEvery(checker: TS.TypeChecker | null, source: TS.SourceFile, raw: string, shown: string): Located[] {
  const wildcard = wildcardPath(raw);
  const unresolved = unresolvedAs(raw, shown);
  if (wildcard === null) return [locate(checker, source, raw, shown)];
  const roots: Scope[] = wildcard.scope.length === 0 ? [source] : walk(checker, source, wildcard.scope, unresolved).flat().flatMap((d) => opened(d.node));
  const functions: Scope[] = [];
  const collect = (scope: Scope): void => {
    for (const d of lookup(scope)) {
      const fn = functionOf(d.node);
      if (fn !== null) functions.push(fn);
      for (const inner of opened(d.node)) collect(inner);
    }
  };
  for (const root of roots) collect(root);
  const groups = bySymbol(checker, functions.flatMap(lookupIn).filter((d) => d.name === wildcard.name));
  if (groups.length === 0) throw unresolved(roots.flatMap(lookup).map((d) => d.name));
  return groups.map((group) => ({ file: source.fileName, position: (group[0] as Declaration).nameNode.getStart(source), topLevel: false }));
}

/** A symbol a path reaches: its path (null when the path does not locate exactly it), its declarations' names in
 * source order, its first declaration, and whether it is a function's local or a parameter. */
export interface Reached {
  path: string | null;
  names: TS.Node[];
  node: TS.Node;
  local: boolean;
  parameter: boolean;
}

const SEGMENT = /^[\p{ID_Start}$_][\p{ID_Continue}$\u200C\u200D]*$/u;

const under = (path: string | null, suffix: string): string | null => (path === null ? null : `${path}${suffix}`);

/** The parameters of `functions`, the first of each name by its path under `one`. */
function parametersOf(functions: Scope[], one: string | null): Reached[] {
  const seen = new Set<string>();
  const found = functions.flatMap((fn) => (fn as TS.SignatureDeclaration).parameters.flatMap((param) => bindingNames(param, param.name)));
  return found.map((p) => {
    const first = one !== null && !seen.has(p.name) && SEGMENT.test(p.name);
    seen.add(p.name);
    return { path: first ? `${one}(${p.name})` : null, names: [p.nameNode], node: p.node, local: false, parameter: true };
  });
}

/** Every symbol of `source` a symbol path reaches, read from syntax. */
export function reach(source: TS.SourceFile): Reached[] {
  const out: Reached[] = [];
  const visit = (scopes: Scope[], prefix: string | null, local: boolean): void => {
    const found = scopes.flatMap(lookupIn);
    for (const name of new Set(found.map((d) => d.name))) {
      const groups = bySymbol(null, found.filter((d) => d.name === name));
      const path = prefix !== null && SEGMENT.test(name) ? `${prefix}${name}` : null;
      const one = groups.length === 1 ? path : null;
      for (const group of groups) out.push({ path: one, names: group.map((d) => d.nameNode), node: (group[0] as Declaration).node, local, parameter: false });
      const nodes = groups.flat().map((d) => d.node);
      const functions = nodes.flatMap((node) => functionOf(node) ?? []);
      out.push(...parametersOf(functions, one));
      if (functions.length > 0) visit(functions, under(path, `.${LOCALS}.`), true);
      const inner = nodes.flatMap(memberScopes);
      if (inner.length > 0) visit(inner, under(path, '.'), false);
    }
  };
  visit([source], '', false);
  return out;
}
