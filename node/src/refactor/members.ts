// A member name's receivers the checker types as `any`, the accesses naming a member by a string or a name, and the
// class, interface and type-literal members declaring it: one scan behind `dr-compliance --attr` and a rename's guards.
import type * as TS from 'typescript';
import { language } from '../contract/index.js';
import { ts } from '../lang/index.js';
import { Lines } from './lines.js';

/** A registry string-member call: how it is spelled, its object's and member's argument positions, whether a miss
 * raises no error (`silent`), or does so once the argument at `default` is passed. */
export interface StringForm {
  call: string;
  object: number;
  member: number;
  silent?: boolean;
  default?: number;
}

/** A string-member call naming the member: its literal's inner span and its object argument. */
export interface FormCall {
  call: TS.CallExpression;
  start: number;
  end: number;
  object: TS.Expression;
}

/** An access naming a member by an expression: a registry string-member call or an element access. */
export interface NamedAccess {
  access: TS.CallExpression | TS.ElementAccessExpression;
  object: TS.Expression;
  member: TS.Expression;
  silent: boolean;
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

const isPosition = (value: unknown): boolean => Number.isInteger(value) && (value as number) >= 0;

function isStringForm(entry: unknown): entry is StringForm {
  if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) return false;
  const form = entry as Record<string, unknown>;
  if (typeof form.call !== 'string' || !isPosition(form.object) || !isPosition(form.member)) return false;
  return (form.silent === undefined || typeof form.silent === 'boolean') && (form.default === undefined || isPosition(form.default));
}

/** The registry's `string_member_calls` entries, validated; a malformed entry is an error. */
export function stringForms(raw: unknown): StringForm[] {
  if (!Array.isArray(raw)) throw new Error('languages.yaml: string_member_calls is not a list');
  return raw.map((entry: unknown, i) => {
    if (!isStringForm(entry)) throw new Error(`languages.yaml: string_member_calls[${i}] is malformed`);
    return entry;
  });
}

let forms: StringForm[] | null = null;
const FORMS = (): StringForm[] => (forms ??= stringForms(language('typescript').string_member_calls));

export function* walk(node: TS.Node): Generator<TS.Node> {
  yield node;
  for (const child of node.getChildren()) yield* walk(child);
}

export const isAny = (checker: TS.TypeChecker, node: TS.Node): boolean =>
  (checker.getTypeAtLocation(node).flags & ts().TypeFlags.Any) !== 0; // NOSONAR(S1529) — TypeFlags bitmask test

/** `node`'s source text, each run of whitespace as one space. */
const collapsed = (node: TS.Node): string => node.getText().replace(/\s+/gu, ' ');

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

/** `call` as the registry form it resolves to, else null. */
function formAccess(checker: TS.TypeChecker, call: TS.CallExpression, source: TS.SourceFile): NamedAccess | null {
  for (const form of FORMS()) {
    const object = call.arguments[form.object];
    const member = call.arguments[form.member];
    if (object === undefined || member === undefined || ts().isSpreadElement(object) || ts().isSpreadElement(member)) continue;
    if (!resolvesTo(checker, call.expression, form.call, source)) continue;
    const silent = form.silent === true || (form.default !== undefined && call.arguments.length > form.default);
    return { access: call, object, member, silent };
  }
  return null;
}

/** Every access of `source` naming a member by an expression, in position order. */
export function namedAccesses(checker: TS.TypeChecker, source: TS.SourceFile): NamedAccess[] {
  const out: NamedAccess[] = [];
  for (const node of walk(source)) {
    if (ts().isElementAccessExpression(node)) out.push({ access: node, object: node.expression, member: node.argumentExpression, silent: false });
    else if (ts().isCallExpression(node)) {
      const found = formAccess(checker, node, source);
      if (found !== null) out.push(found);
    }
  }
  return out;
}

/** A string-named access as printed: `CALLEE(RECEIVER, 'NAME')`, `, …` standing for further arguments, or
 * `RECEIVER['NAME']`. */
export function siteText(access: TS.CallExpression | TS.ElementAccessExpression, receiver: TS.Expression, name: string): string {
  if (ts().isElementAccessExpression(access)) return `${collapsed(receiver)}['${name}']`;
  return `${collapsed(access.expression)}(${collapsed(receiver)}, '${name}'${access.arguments.length > 2 ? ', …' : ''})`;
}

/** A receiver of `.name` typed `any`; a string-named access has its printed `site`, its literal's inner span and
 * whether a miss raises no error. */
export interface AnyReceiver {
  position: number;
  receiver: string;
  site?: string;
  literal?: [number, number];
  silent?: boolean;
}

/** An `any` receiver's finding: its template and its values other than path and line. */
export function blindspotFinding(found: Pick<AnyReceiver, 'receiver' | 'site' | 'silent'>, name: string): { template: string; values: Record<string, unknown> } {
  const values = { receiver: found.receiver, attr: name, type: language('typescript').any_type as string };
  if (found.site === undefined) return { template: 'compliance.attr-blindspot', values };
  return { template: found.silent === true ? 'compliance.string-blindspot-silent' : 'compliance.string-blindspot', values: { ...values, site: found.site } };
}

/** Every `x.name` whose receiver is typed `any`. */
export function anyAccesses(checker: TS.TypeChecker, source: TS.SourceFile, name: string): AnyReceiver[] {
  const out: AnyReceiver[] = [];
  for (const node of walk(source)) {
    if (!ts().isPropertyAccessExpression(node) || node.name.text !== name || !isAny(checker, node.expression)) continue;
    out.push({ position: node.getStart(source), receiver: collapsed(node.expression) });
  }
  return out;
}

/** `found` naming `name` by a plain string literal on an object typed `any`, else null. */
export function anyNamed(checker: TS.TypeChecker, source: TS.SourceFile, found: NamedAccess, name: string): AnyReceiver | null {
  const literal = plainString(found.member, source);
  if (literal?.[2] !== name || !isAny(checker, found.object)) return null;
  const site = siteText(found.access, found.object, name);
  return { position: found.access.getStart(source), receiver: collapsed(found.object), site, literal: [literal[0], literal[1]], silent: found.silent };
}

/** Every string-named access of `name` whose object is typed `any`. */
export function anyNamedAccesses(checker: TS.TypeChecker, source: TS.SourceFile, name: string): AnyReceiver[] {
  return namedAccesses(checker, source).flatMap((found) => anyNamed(checker, source, found, name) ?? []);
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
