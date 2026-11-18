// The literal sources of a name: the plain string literals a supported binding gives it, in project sources only, and
// the reads of every name holding one.
import type * as TS from 'typescript';
import { ts } from '../lang/index.js';
import { plainString } from './members.js';

/** A plain string literal a name holds: its file, its inner span and its text. */
export interface LiteralSource {
  path: string;
  start: number;
  end: number;
  text: string;
}

/** A read of a name holding a source: the name as written and where it starts. */
export interface Read {
  path: string;
  start: number;
  name: string;
}

/** What a supported binding gives its name: one value, or each element of what it iterates. */
type Bound = { value: TS.Expression } | { each: TS.Expression };

interface Context {
  service: TS.LanguageService;
  program: TS.Program;
  checker: TS.TypeChecker;
  /** The symbols on the chain being followed. */
  seen: Set<TS.Symbol>;
}

/** The array methods whose callback takes an element as its first parameter. */
const ELEMENT_CALLBACKS = new Set(['every', 'filter', 'find', 'findIndex', 'findLast', 'findLastIndex', 'flatMap', 'forEach', 'map', 'some']);

function unwrapped(expression: TS.Expression): TS.Expression {
  let node = expression;
  while (ts().isParenthesizedExpression(node)) node = node.expression;
  return node;
}

/** An identifier or a dotted name. */
function isName(node: TS.Node): node is TS.Identifier | TS.PropertyAccessExpression {
  return ts().isIdentifier(node) || (ts().isPropertyAccessExpression(node) && ts().isIdentifier(node.name) && isName(node.expression));
}

const isConstAssertion = (node: TS.Node): node is TS.AsExpression => ts().isAsExpression(node) && ts().isConstTypeReference(node.type);

/** The symbol `name` names, imports and re-exports followed. */
function symbolOf(checker: TS.TypeChecker, name: TS.Node): TS.Symbol | undefined {
  const symbol = checker.getSymbolAtLocation(ts().isPropertyAccessExpression(name) ? name.name : name);
  const aliased = symbol !== undefined && (symbol.flags & ts().SymbolFlags.Alias) !== 0; // NOSONAR(S1529) — SymbolFlags bitmask test
  return aliased ? checker.getAliasedSymbol(symbol) : symbol;
}

/** Nothing but its declaration writes the declared `name`. */
function unwritten(context: Context, name: TS.Node): boolean {
  const file = name.getSourceFile();
  const start = name.getStart(file);
  const references = (context.service.findReferences(file.fileName, start) ?? []).flatMap((found) => found.references);
  return !references.some((r) => r.isWriteAccess && !(r.fileName === file.fileName && r.textSpan.start === start));
}

/** `expression` can give a source: a string literal, a name or an `as const` display. */
function mayHold(expression: TS.Expression): boolean {
  const node = unwrapped(expression);
  return ts().isStringLiteral(node) || isName(node) || isConstAssertion(node);
}

/** The first parameter of an array method's element callback: the array it is called on. */
function callbackBinding(parameter: TS.ParameterDeclaration): Bound | null {
  const callback = parameter.parent;
  if (!ts().isArrowFunction(callback) && !ts().isFunctionExpression(callback)) return null;
  if (callback.parameters[0] !== parameter || parameter.dotDotDotToken !== undefined || parameter.initializer !== undefined) return null;
  const call = callback.parent;
  if (!ts().isCallExpression(call) || call.arguments[0] !== callback || !ts().isPropertyAccessExpression(call.expression)) return null;
  return ELEMENT_CALLBACKS.has(call.expression.name.text) ? { each: call.expression.expression } : null;
}

/** A `const` or an unwritten `let`: its initializer, or what its `for…of` iterates. */
function variableBinding(context: Context, declaration: TS.VariableDeclaration): Bound | null {
  const list = declaration.parent;
  if (!ts().isVariableDeclarationList(list)) return null;
  const kind = list.flags & ts().NodeFlags.BlockScoped; // NOSONAR(S1529) — NodeFlags bitmask test
  if (kind !== ts().NodeFlags.Const && kind !== ts().NodeFlags.Let) return null;
  let bound: Bound | null = null;
  if (ts().isForOfStatement(list.parent)) bound = list.parent.awaitModifier === undefined ? { each: list.parent.expression } : null;
  else if (declaration.initializer !== undefined && !ts().isForInStatement(list.parent) && mayHold(declaration.initializer)) bound = { value: declaration.initializer };
  return bound !== null && (kind === ts().NodeFlags.Const || unwritten(context, declaration.name)) ? bound : null;
}

/** `symbol`'s one supported binding in a project source, else null; `access`: it is read as `K.NAME`. */
function binding(context: Context, symbol: TS.Symbol, access: boolean): Bound | null {
  const [declaration, ...others] = symbol.declarations ?? [];
  if (declaration === undefined || others.length > 0) return null;
  const file = declaration.getSourceFile();
  if (file.isDeclarationFile || context.program.isSourceFileFromExternalLibrary(file)) return null;
  const name = ts().getNameOfDeclaration(declaration);
  if (name === undefined || !ts().isIdentifier(name)) return null;
  if (ts().isVariableDeclaration(declaration)) return variableBinding(context, declaration);
  if (ts().isParameter(declaration)) {
    const bound = callbackBinding(declaration);
    return bound !== null && unwritten(context, name) ? bound : null;
  }
  if (!ts().isPropertyDeclaration(declaration) || !access || declaration.initializer === undefined || !mayHold(declaration.initializer)) return null;
  const constant = ts().ModifierFlags.Static | ts().ModifierFlags.Readonly;
  return (ts().getCombinedModifierFlags(declaration) & constant) === constant && unwritten(context, name) ? { value: declaration.initializer } : null; // NOSONAR(S1529) — ModifierFlags bitmask test
}

function sourceOf(literal: TS.Node): LiteralSource | null {
  const file = literal.getSourceFile();
  const plain = plainString(literal, file);
  return plain === null ? null : { path: file.fileName, start: plain[0], end: plain[1], text: plain[2] };
}

/** The binding of the name `name` reads, null when unsupported or already on the chain. */
function bindingOf(context: Context, name: TS.Identifier | TS.PropertyAccessExpression): Bound | null {
  const symbol = symbolOf(context.checker, name);
  if (symbol === undefined || context.seen.has(symbol)) return null;
  context.seen.add(symbol);
  return binding(context, symbol, ts().isPropertyAccessExpression(name));
}

/** The elements of the `as const` array literal of plain string literals that `expression` is or names. */
function elements(context: Context, expression: TS.Expression): LiteralSource[] {
  const node = unwrapped(expression);
  if (isName(node)) {
    const bound = bindingOf(context, node);
    return bound !== null && 'value' in bound ? elements(context, bound.value) : [];
  }
  const display = isConstAssertion(node) ? unwrapped(node.expression) : node;
  if (display === node || !ts().isArrayLiteralExpression(display)) return [];
  const found = display.elements.map((element) => sourceOf(element));
  return found.every((source): source is LiteralSource => source !== null) ? found : [];
}

/** The sources of the value `expression`: a plain string literal, or a name's. */
function valueSources(context: Context, expression: TS.Expression): LiteralSource[] {
  const node = unwrapped(expression);
  if (!isName(node)) return [sourceOf(node)].filter((source): source is LiteralSource => source !== null);
  const bound = bindingOf(context, node);
  if (bound === null) return [];
  return 'value' in bound ? valueSources(context, bound.value) : elements(context, bound.each);
}

function contextOf(service: TS.LanguageService): Context | null {
  const program = service.getProgram();
  return program === undefined ? null : { service, program, checker: program.getTypeChecker(), seen: new Set() };
}

/** The literal sources of the name `node` reads (an identifier or a dotted name) in `service`'s program. */
export function literalSources(service: TS.LanguageService, node: TS.Node): LiteralSource[] {
  const context = contextOf(service);
  return context === null || !isName(node) ? [] : valueSources(context, node);
}

/** The name `expression` hands its value or its elements to: a declared name, a `for…of` target or a callback's first
 * parameter. */
function carriedTo(expression: TS.Node): TS.Node | null {
  let node = expression;
  while (ts().isParenthesizedExpression(node.parent) || isConstAssertion(node.parent)) node = node.parent;
  const parent = node.parent;
  if ((ts().isVariableDeclaration(parent) || ts().isPropertyDeclaration(parent)) && parent.initializer === node) return parent.name;
  if (ts().isForOfStatement(parent) && parent.expression === node) {
    return ts().isVariableDeclarationList(parent.initializer) ? (parent.initializer.declarations[0]?.name ?? null) : null;
  }
  if (!ts().isPropertyAccessExpression(parent) || parent.expression !== node || !ts().isCallExpression(parent.parent) || parent.parent.expression !== parent) return null;
  const [callback] = parent.parent.arguments;
  return callback !== undefined && (ts().isArrowFunction(callback) || ts().isFunctionExpression(callback)) ? (callback.parameters[0]?.name ?? null) : null;
}

/** The declared name `name` holds `source`, as its value or among its elements. */
function holds(service: TS.LanguageService, name: TS.Node, source: LiteralSource): boolean {
  const context = contextOf(service);
  const symbol = context === null ? undefined : symbolOf(context.checker, name);
  const bound = context === null || symbol === undefined ? null : binding(context, symbol, true);
  if (context === null || bound === null) return false;
  const iterated = elements({ ...context, seen: new Set() }, 'value' in bound ? bound.value : bound.each);
  const found = 'value' in bound ? [...valueSources(context, bound.value), ...iterated] : iterated;
  return found.some((s) => s.path === source.path && s.start === source.start);
}

/** The identifier of `file` starting at `start`. */
function identifierAt(file: TS.SourceFile, start: number): TS.Identifier | null {
  let node: TS.Node = file;
  for (;;) {
    const inner: TS.Node | undefined = ts().forEachChild(node, (child) => (child.getStart(file) <= start && start < child.end ? child : undefined));
    if (inner === undefined) return ts().isIdentifier(node) && node.getStart(file) === start ? node : null;
    node = inner;
  }
}

/** The string literal of `file` whose inner span starts at `start`. */
function literalAt(file: TS.SourceFile, start: number): TS.Node | null {
  let node: TS.Node = file;
  for (;;) {
    const inner: TS.Node | undefined = ts().forEachChild(node, (child) => (child.getStart(file) < start && start < child.end ? child : undefined));
    if (inner === undefined) return ts().isStringLiteral(node) ? node : null;
    node = inner;
  }
}

/** The display holding `source` has the plain string `text` among its elements. */
export function displayHolds(file: TS.SourceFile, source: LiteralSource, text: string): boolean {
  const display = literalAt(file, source.start)?.parent;
  return display !== undefined && ts().isArrayLiteralExpression(display) && display.elements.some((element) => plainString(element, file)?.[2] === text);
}

/** `parent` declares the name `name`. */
function declares(parent: TS.Node, name: TS.Identifier): boolean {
  return (parent as TS.NamedDeclaration).name === name && !ts().isPropertyAccessExpression(parent) && !ts().isShorthandPropertyAssignment(parent);
}

/** The identifiers referring to the declared `holder`, its own declaration aside. */
function references(service: TS.LanguageService, program: TS.Program, holder: TS.Node): TS.Identifier[] {
  const file = holder.getSourceFile();
  const out: TS.Identifier[] = [];
  for (const reference of (service.findReferences(file.fileName, holder.getStart(file)) ?? []).flatMap((found) => found.references)) {
    const source = program.getSourceFile(reference.fileName);
    const node = source === undefined ? null : identifierAt(source, reference.textSpan.start);
    if (node !== null && node !== holder) out.push(node);
  }
  return out;
}

/** Every read of a name holding `source` in `services`' programs, but the ones carrying it to another such name. */
export function sourceReads(services: TS.LanguageService[], source: LiteralSource): Read[] {
  const out = new Map<string, Read>();
  for (const service of services) {
    const program = service.getProgram();
    const file = program?.getSourceFile(source.path);
    const literal = file === undefined ? null : literalAt(file, source.start);
    if (program === undefined || literal === null) continue;
    const first = carriedTo(ts().isArrayLiteralExpression(literal.parent) ? literal.parent : literal);
    const pending = first === null ? [] : [first];
    const held = new Set<TS.Node>();
    for (let holder = pending.pop(); holder !== undefined; holder = pending.pop()) {
      if (held.has(holder) || !ts().isIdentifier(holder) || !holds(service, holder, source)) continue;
      held.add(holder);
      for (const reference of references(service, program, holder)) {
        const parent = reference.parent;
        if (ts().isImportSpecifier(parent) || ts().isExportSpecifier(parent)) pending.push(parent.name);
        else if (!declares(parent, reference)) {
          const read = ts().isPropertyAccessExpression(parent) && parent.name === reference ? parent : reference;
          const next = carriedTo(read);
          if (next !== null && ts().isIdentifier(next) && holds(service, next, source)) pending.push(next);
          else out.set(`${read.getSourceFile().fileName}\0${read.getStart()}`, { path: read.getSourceFile().fileName, start: read.getStart(), name: read.getText() });
        }
      }
    }
  }
  return [...out.values()];
}
