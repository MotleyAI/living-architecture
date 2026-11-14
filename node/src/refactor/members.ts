// A member name's receivers the checker types as `any`, the calls naming a member by a string, and the class,
// interface and type-literal members declaring it: one scan behind `dr-compliance --attr` and a rename's guards.
import type * as TS from 'typescript';
import { language } from '../contract/index.js';
import { ts } from '../lang/index.js';
import { Lines } from './lines.js';

interface StringForm {
  call: string;
  object: number;
  member: number;
}

/** A string-member call naming the member: its literal's inner span and its object argument. */
export interface FormCall {
  call: TS.CallExpression;
  start: number;
  end: number;
  object: TS.Expression;
}

/** A class member declaration of the name: its name's start (a computed name's bracket), its line (1-based), its
 * owner's name and whether a computed name declares it. */
export interface MemberDeclaration {
  path: string;
  start: number;
  line: number;
  owner: string;
  computed: boolean;
}

const FORMS = (): StringForm[] => language('typescript').string_member_calls as StringForm[];

export function* walk(node: TS.Node): Generator<TS.Node> {
  yield node;
  for (const child of node.getChildren()) yield* walk(child);
}

export const isAny = (checker: TS.TypeChecker, node: TS.Node): boolean =>
  (checker.getTypeAtLocation(node).flags & ts().TypeFlags.Any) !== 0; // NOSONAR(S1529) — TypeFlags bitmask test

/** A single- or double-quoted string literal's inner span and text, without escapes. */
export function plainString(node: TS.Node | undefined, source: TS.SourceFile): [number, number, string] | null {
  if (node === undefined || !ts().isStringLiteral(node)) return null;
  const raw = node.getText(source);
  if (raw.slice(1, -1) !== node.text || !`'"`.includes(raw[0] ?? '')) return null;
  const start = node.getStart(source) + 1;
  return [start, start + node.text.length, node.text];
}

/** `callee` spelled `call`, its head declared outside the project's sources (a library or declaration file). */
function resolvesTo(checker: TS.TypeChecker, callee: TS.Expression, call: string, source: TS.SourceFile): boolean {
  if (callee.getText(source) !== call) return false;
  let head: TS.Expression = callee;
  while (ts().isPropertyAccessExpression(head)) head = head.expression;
  let symbol = checker.getSymbolAtLocation(head);
  if (symbol !== undefined && (symbol.flags & ts().SymbolFlags.Alias) !== 0) symbol = checker.getAliasedSymbol(symbol); // NOSONAR(S1529) — SymbolFlags bitmask test
  const declarations = symbol?.declarations ?? [];
  return declarations.length > 0 && declarations.every((d) => d.getSourceFile().isDeclarationFile);
}

/** The registry's string-member calls whose member literal is `name`. */
export function formCalls(checker: TS.TypeChecker, source: TS.SourceFile, name: string): FormCall[] {
  const out: FormCall[] = [];
  for (const node of walk(source)) {
    if (!ts().isCallExpression(node)) continue;
    for (const form of FORMS()) {
      const literal = plainString(node.arguments[form.member], source);
      const object = node.arguments[form.object];
      if (literal?.[2] !== name || object === undefined || ts().isSpreadElement(object)) continue;
      if (!resolvesTo(checker, node.expression, form.call, source)) continue;
      out.push({ call: node, start: literal[0], end: literal[1], object });
      break;
    }
  }
  return out;
}

/** A receiver of `.name` typed `any`: a property access or a string-member call's object. */
export interface AnyReceiver {
  position: number;
  receiver: string;
}

/** Every `x.name` whose receiver is typed `any`. */
export function anyAccesses(checker: TS.TypeChecker, source: TS.SourceFile, name: string): AnyReceiver[] {
  const out: AnyReceiver[] = [];
  for (const node of walk(source)) {
    if (ts().isPropertyAccessExpression(node) && node.name.text === name && isAny(checker, node.expression)) {
      out.push({ position: node.getStart(source), receiver: node.expression.getText(source) });
    }
  }
  return out;
}

/** Every `x.name` and string-member object typed `any`, in position order. */
export function anyReceivers(checker: TS.TypeChecker, source: TS.SourceFile, name: string): AnyReceiver[] {
  const out = anyAccesses(checker, source, name);
  for (const found of formCalls(checker, source, name)) {
    if (isAny(checker, found.object)) out.push({ position: found.call.getStart(source), receiver: found.object.getText(source) });
  }
  return out.sort((a, b) => a.position - b.position);
}

const OWNERS = (): Set<number> => {
  const k = ts().SyntaxKind;
  return new Set([k.ClassDeclaration, k.ClassExpression, k.InterfaceDeclaration, k.TypeLiteral]);
};

/** The name of a class, interface or type literal (the type alias or declaration holding it). */
function ownerName(owner: TS.Node, source: TS.SourceFile): string {
  for (let node: TS.Node | undefined = owner; node !== undefined && !ts().isSourceFile(node); node = node.parent) {
    const name = (node as TS.NamedDeclaration).name;
    if (name !== undefined && ts().isIdentifier(name)) return name.text;
  }
  return owner.getText(source).slice(0, 20);
}

/** The class, interface or type literal declaring member `node`: its parent, or a parameter property's class. */
function memberOwner(node: TS.Node): TS.Node | undefined {
  const parent = node.parent as TS.Node | undefined;
  if (parent !== undefined && ts().isParameter(node) && ts().isParameterPropertyDeclaration(node, parent)) return parent.parent;
  return parent;
}

/** The start of the text `name` names a member by: an identifier, or the inside of a string literal or computed string. */
export function memberNameStart(declared: TS.Node, name: string, source: TS.SourceFile): number | null {
  if ((ts().isIdentifier(declared) || ts().isPrivateIdentifier(declared)) && declared.text === name) return declared.getStart(source);
  const literal = ts().isComputedPropertyName(declared) ? declared.expression : declared;
  if ((ts().isStringLiteral(literal) || ts().isNoSubstitutionTemplateLiteral(literal)) && literal.text === name) return literal.getStart(source) + 1;
  return null;
}

/** The declarations of member `name` that `owner` itself declares: the checker's properties of its instance and
 * static sides, and `#private` names by their syntax (they are not properties). */
function ownDeclarations(checker: TS.TypeChecker, owner: TS.Node, name: string): Set<TS.Declaration> {
  const type = checker.getTypeAtLocation(owner);
  const types = [type];
  const symbol = type.getSymbol();
  if (ts().isClassLike(owner) && symbol !== undefined) types.push(checker.getDeclaredTypeOfSymbol(symbol), checker.getTypeOfSymbolAtLocation(symbol, owner));
  const out = new Set<TS.Declaration>();
  for (const t of types) for (const d of t.getProperty(name)?.declarations ?? []) if (memberOwner(d) === owner) out.add(d);
  for (const child of walk(owner)) {
    const declared = (child as TS.NamedDeclaration).name;
    if (declared !== undefined && ts().isPrivateIdentifier(declared) && declared.text === name && memberOwner(child) === owner) out.add(child as TS.Declaration);
  }
  return out;
}

/** Every member named `name` that a class, an interface or a type literal of `source` declares, in position order. */
export function memberDeclarations(checker: TS.TypeChecker, source: TS.SourceFile, name: string, path: string): MemberDeclaration[] {
  const owners = OWNERS();
  const lines = new Lines(source.text);
  const out: MemberDeclaration[] = [];
  for (const node of walk(source)) {
    if (!owners.has(node.kind)) continue;
    for (const declaration of ownDeclarations(checker, node, name)) {
      const declared = ts().getNameOfDeclaration(declaration);
      if (declared === undefined) continue;
      const named = memberNameStart(declared, name, source);
      const start = named ?? declared.getStart(source);
      out.push({ path, start, line: lines.lineOf(start), owner: ownerName(node, source), computed: named === null });
    }
  }
  return out.sort((a, b) => a.start - b.start);
}
