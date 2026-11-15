// `retarget` for TypeScript: an alias's target and its home, each rename location of the alias kept, re-pointed or
// refused so every rewritten name stays bound, and the imports of the target planned once across a map's entries.
import { basename, dirname, relative } from 'node:path';
import type * as TS from 'typescript';
import { message } from '../contract/index.js';
import { posix, stripSourceExtension, ts } from '../lang/index.js';
import { type Edit, RefactorError } from './edits.js';
import { memberDeclarations, memberNameStart, walk } from './members.js';
import { type Locator, nodeAt, type ProjectSource, type Refactor, UsageError } from './session.js';
import { locate as locateSymbol } from './symbols.js';

export interface Finding {
  path: string;
  line: number;
  position: number;
  text: string;
}

/** A module alias's target: the module its alias's module imports it from (the alias's own file where it declares it;
 * `file` null for a package), as that module spells it, the name it exports it by, and the name written for it. */
export interface Home {
  file: string | null;
  specifier: string | null;
  exported: string;
  local: string;
}

/** What a retarget entry knows of its alias and target. */
export interface Retarget {
  index: number;
  file: string;
  old: string;
  newName: string;
  edits: Edit[];
  own: Set<string>;
  home: Home | null;
  /** The target's declarations, as keys. */
  identity: Set<string>;
  /** The target's name before the map renames it. */
  original: string;
}

/** `local` bound to the target by an import in `anchor`'s block (when `bind`); `leaving`, an import of the alias in
 * `anchor`, dropped from it; `duplicates`, later imports of the target the added one makes redundant. */
export interface Need {
  path: string;
  anchor: TS.ImportDeclaration;
  home: Home;
  local: string;
  type: boolean;
  bind: boolean;
  leaving: TS.ImportSpecifier | null;
  duplicates: TS.ImportSpecifier[];
}

/** The project's sources and the facts a retarget reports with. */
export interface RetargetSession {
  r: Refactor;
  sources: Map<string, ProjectSource>;
  lineOf(path: string, position: number): number;
  finding(path: string, position: number, template: string, values: Record<string, unknown>): Finding;
}

export const keyOf = (path: string, start: number): string => `${path}\0${start}`;

/** The symbol `node` names, an import binding followed to what it imports. */
export function symbolOf(checker: TS.TypeChecker, node: TS.Node): TS.Symbol | undefined {
  return followed(checker, checker.getSymbolAtLocation(node));
}

function followed(checker: TS.TypeChecker, symbol: TS.Symbol | undefined): TS.Symbol | undefined {
  const aliased = symbol !== undefined && (symbol.flags & ts().SymbolFlags.Alias) !== 0; // NOSONAR(S1529) — SymbolFlags bitmask test
  return aliased ? checker.getAliasedSymbol(symbol) : symbol;
}

/** The name starts of a symbol's declarations, as keys. */
export function declarationKeys(symbol: TS.Symbol | undefined, old: string): string[] {
  return (symbol?.declarations ?? []).flatMap((d) => {
    const file = d.getSourceFile();
    const name = ts().getNameOfDeclaration(d);
    return name === undefined ? [] : [keyOf(file.fileName, memberNameStart(name, old, file) ?? name.getStart(file))];
  });
}

/** The body, class or file that holds declaration `node`. */
export function scopeOf(node: TS.Node): TS.Node {
  let scope = node.parent;
  while (!(ts().isFunctionLike(scope) || ts().isSourceFile(scope) || ts().isModuleBlock(scope) || ts().isClassLike(scope) || ts().isInterfaceDeclaration(scope) || ts().isTypeLiteralNode(scope) || ts().isEnumDeclaration(scope))) {
    scope = scope.parent;
  }
  return scope;
}

/** The source file of the module `specifier` names. */
function moduleFile(checker: TS.TypeChecker, specifier: TS.Expression): string | null {
  const module = checker.getSymbolAtLocation(specifier);
  const declaration = module?.valueDeclaration ?? module?.declarations?.[0];
  return declaration !== undefined && ts().isSourceFile(declaration) ? declaration.fileName : null;
}

const specifierText = (specifier: TS.Expression): string | null => (ts().isStringLiteral(specifier) ? specifier.text : null);

/** A re-export declaring `alias` (`export { T as ALIAS } from 'M'`, `import { T as ALIAS } from 'M'`) of `raw`; null
 * when `alias` is no such re-export. */
function reexportHome(checker: TS.TypeChecker, alias: TS.Node, raw: string, refused: () => UsageError): Home | null {
  const spec = alias.parent;
  if (!(ts().isExportSpecifier(spec) || ts().isImportSpecifier(spec)) || spec.name !== alias) return null;
  const declaration = ts().isExportSpecifier(spec) ? spec.parent.parent : spec.parent.parent.parent;
  const moduleSpecifier = declaration.moduleSpecifier;
  if (spec.propertyName?.getText() !== raw || moduleSpecifier === undefined) throw refused();
  return { file: moduleFile(checker, moduleSpecifier), specifier: specifierText(moduleSpecifier), exported: raw, local: raw };
}

/** A retarget's target resolved beside its alias (declared or imported in the alias's class or module, or the name a
 * re-export declaring the alias imports), else UsageError; the alias's own declarations recorded. */
export function resolveTarget(r: Refactor, file: string, locator: Locator, shown: string, target: Retarget & { position: number }, raw: string): string {
  const program = r.services(target.file)[0]?.getProgram();
  const source = program?.getSourceFile(file);
  const aliasSource = program?.getSourceFile(target.file);
  if (program === undefined || source === undefined || aliasSource === undefined) throw new RefactorError(message('refactor.ts-outside-project', { path: r.rel(file) }));
  const checker = program.getTypeChecker();
  const refused = (): UsageError => new UsageError(message('refactor.retarget-scope', { target: raw, alias: locator.symbol ?? target.old }));
  const aliasNode = nodeAt(aliasSource, target.position);
  const reexport = reexportHome(checker, aliasNode, raw, refused);
  if (reexport !== null) {
    const symbol = symbolOf(checker, aliasNode);
    target.own.add(keyOf(target.file, aliasNode.getStart(aliasSource)));
    return settle(target, reexport, declarationKeys(symbol, raw), raw) ?? keyOf(target.file, target.position);
  }
  const located = locateSymbol(checker, source, raw, shown, false);
  const targetSource = program.getSourceFile(located.file);
  const alias = symbolOf(checker, aliasNode);
  const node = targetSource === undefined ? undefined : nodeAt(targetSource, located.position);
  const binding = node === undefined ? undefined : checker.getSymbolAtLocation(node);
  const symbol = followed(checker, binding);
  const scopes = (s: TS.Symbol | undefined): TS.Node[] => (s?.declarations ?? []).map(scopeOf);
  const beside = scopes(alias).some((scope) => scopes(binding).includes(scope));
  if (alias === undefined || symbol === undefined || binding === undefined || !beside) throw refused();
  for (const key of declarationKeys(alias, target.old)) target.own.add(key);
  const identity = declarationKeys(symbol, symbol.name);
  const intent = identity[0] ?? keyOf(located.file, located.position);
  if (scopes(alias).some((scope) => !(ts().isSourceFile(scope) || ts().isModuleBlock(scope)))) {
    settle(target, null, identity, symbol.name);
    return intent;
  }
  const imported = binding.declarations?.find((d) => ts().isImportSpecifier(d));
  if (imported !== undefined && inImport(imported)) {
    const declaration = declarationOf(imported);
    const home = { file: moduleFile(checker, declaration.moduleSpecifier), specifier: specifierText(declaration.moduleSpecifier), exported: (imported.propertyName ?? imported.name).getText(), local: imported.name.text };
    settle(target, home, identity, imported.name.text);
  } else {
    if ((binding.flags & ts().SymbolFlags.Alias) !== 0) throw refused(); // NOSONAR(S1529) — SymbolFlags bitmask test
    settle(target, { file: target.file, specifier: null, exported: symbol.name, local: symbol.name }, identity, symbol.name);
  }
  return intent;
}

function settle(target: Retarget, home: Home | null, identity: string[], name: string): string | undefined {
  target.home = home;
  target.identity = new Set(identity);
  target.original = name;
  target.newName = name;
  return identity[0];
}

/** The target's final name where another entry renames it, in its home too. */
export function rename(target: Retarget, final: string): void {
  if (target.home !== null) {
    target.home = {
      ...target.home,
      exported: target.home.exported === target.original ? final : target.home.exported,
      local: target.home.local === target.original ? final : target.home.local,
    };
  }
  target.newName = final;
}

/** An identifier read as a bare name: not a member name, an import or export specifier, or a declaration's name. */
function bareReference(node: TS.Node): boolean {
  const parent = node.parent;
  if (!ts().isIdentifier(node)) return false;
  if (ts().isPropertyAccessExpression(parent) && parent.name === node) return false;
  if (ts().isQualifiedName(parent) && parent.right === node) return false;
  if (ts().isImportSpecifier(parent) || ts().isExportSpecifier(parent) || ts().isImportClause(parent) || ts().isNamespaceImport(parent)) return false;
  return ts().isShorthandPropertyAssignment(parent) || (parent as { name?: TS.Node }).name !== node;
}

/** A use of a name that needs its type meaning only. */
function typeUse(node: TS.Node): boolean {
  let name = node;
  while (ts().isQualifiedName(name.parent) && name.parent.left === name) name = name.parent;
  const parent = name.parent;
  if (ts().isTypeReferenceNode(parent)) return true;
  if (!ts().isExpressionWithTypeArguments(parent) || !ts().isHeritageClause(parent.parent)) return false;
  return parent.parent.token === ts().SyntaxKind.ImplementsKeyword || ts().isInterfaceDeclaration(parent.parent.parent);
}

const isTypeOnly = (specifier: TS.ImportSpecifier): boolean => specifier.isTypeOnly || specifier.parent.parent.isTypeOnly;

/** The import declaration holding `specifier`, which no JSDoc `@import` holds. */
function declarationOf(specifier: TS.ImportSpecifier): TS.ImportDeclaration {
  const declaration = specifier.parent.parent.parent;
  if (!ts().isImportDeclaration(declaration)) throw new RefactorError(message('refactor.cannot-rename'));
  return declaration;
}

const inImport = (node: TS.Node): node is TS.ImportSpecifier => ts().isImportSpecifier(node) && ts().isImportDeclaration(node.parent.parent.parent);

/** The import specifier binding a bare name. */
function bindingOf(checker: TS.TypeChecker, node: TS.Node): TS.ImportSpecifier | null {
  const symbol = ts().isShorthandPropertyAssignment(node.parent) ? checker.getShorthandAssignmentValueSymbol(node.parent) : checker.getSymbolAtLocation(node);
  const found = symbol?.declarations?.find((d) => inImport(d) && d.getSourceFile() === node.getSourceFile());
  return found !== undefined && inImport(found) ? found : null;
}

/** The removal of `specifier` from its list, or of its whole import declaration (and its line) when it binds nothing else. */
export function removeSpecifiers(source: TS.SourceFile, declaration: TS.ImportDeclaration, removed: Set<TS.ImportSpecifier>): Edit[] {
  const clause = declaration.importClause;
  const bindings = clause?.namedBindings;
  if (bindings === undefined || !ts().isNamedImports(bindings)) return [];
  const elements = bindings.elements;
  if (elements.every((e) => removed.has(e)) && clause?.name === undefined) {
    const text = source.text;
    const [start, end] = [declaration.getStart(source), declaration.end];
    const lineStart = text.lastIndexOf('\n', start - 1) + 1;
    const newline = text.indexOf('\n', end);
    const lineEnd = newline === -1 ? text.length : newline + 1;
    const alone = text.slice(lineStart, start).trim() === '' && text.slice(end, lineEnd).trim() === '';
    return [alone ? { path: source.fileName, start: lineStart, length: lineEnd - lineStart, newText: '' } : { path: source.fileName, start, length: end - start, newText: '' }];
  }
  const edits: Edit[] = [];
  for (let i = 0; i < elements.length; ) {
    if (!removed.has(elements[i] as TS.ImportSpecifier)) {
      i += 1;
      continue;
    }
    let j = i;
    while (j < elements.length && removed.has(elements[j] as TS.ImportSpecifier)) j += 1;
    const next = elements[j];
    const [start, end] = next !== undefined ? [(elements[i] as TS.ImportSpecifier).getStart(source), next.getStart(source)] : [(elements[i - 1] as TS.ImportSpecifier).end, (elements[j - 1] as TS.ImportSpecifier).end];
    edits.push({ path: source.fileName, start, length: end - start, newText: '' });
    i = j;
  }
  return edits;
}

/** The file's other import specifiers of `module`'s export `name` under that name. */
function importsOf(checker: TS.TypeChecker, source: TS.SourceFile, module: TS.ImportDeclaration, name: string, skip: TS.ImportSpecifier): TS.ImportSpecifier[] {
  const target = checker.getSymbolAtLocation(module.moduleSpecifier);
  const same = (d: TS.ImportDeclaration): boolean =>
    target !== undefined ? checker.getSymbolAtLocation(d.moduleSpecifier) === target : d.moduleSpecifier.getText(source) === module.moduleSpecifier.getText(source);
  return source.statements
    .filter((s): s is TS.ImportDeclaration => ts().isImportDeclaration(s) && same(s))
    .flatMap((d) => {
      const bindings = d.importClause?.namedBindings;
      return bindings !== undefined && ts().isNamedImports(bindings) ? [...bindings.elements] : [];
    })
    .filter((e) => e !== skip && e.name.text === name && (e.propertyName ?? e.name).text === name);
}

/** The edits replacing a retarget's rename of import specifier `specifier` when the module also imports the target,
 * the later of the two removed so the module keeps its first import's place: the specifier's removal when it is
 * type-only or a value import of the target comes first, else its rename plus the removal of the target's imports;
 * null when the module does not import the target. */
function duplicateImport(source: TS.SourceFile, checker: TS.TypeChecker, specifier: TS.ImportSpecifier, edit: Edit, name: string): Edit[] | null {
  if (specifier.propertyName !== undefined) return null;
  const declaration = declarationOf(specifier);
  const twins = importsOf(checker, source, declaration, name, specifier);
  if (twins.length === 0) return null;
  const earlier = twins.some((t) => !isTypeOnly(t) && t.getStart(source) < specifier.getStart(source));
  if (isTypeOnly(specifier) || earlier) return removeSpecifiers(source, declaration, new Set([specifier]));
  return [edit, ...twins.flatMap((t) => removeSpecifiers(source, declarationOf(t), new Set([t])))];
}

/** Where a file re-exports the alias: its `export { ALIAS }`, `export type { ALIAS }` and `export { ALIAS } from`
 * specifiers and the imports of the locals the local ones export, as spans. */
function reexportSpans(source: TS.SourceFile, name: string): [number, number][] {
  const exported = source.statements.flatMap((s) =>
    ts().isExportDeclaration(s) && s.exportClause !== undefined && ts().isNamedExports(s.exportClause) ? s.exportClause.elements.filter((e) => e.name.text === name) : [],
  );
  const locals = new Set(exported.filter((e) => e.parent.parent.moduleSpecifier === undefined).map((e) => (e.propertyName ?? e.name).text));
  const imported = source.statements.flatMap((s): TS.Node[] => {
    const clause = ts().isImportDeclaration(s) ? s.importClause : undefined;
    const bindings = clause?.namedBindings;
    const named = bindings !== undefined && ts().isNamedImports(bindings) ? bindings.elements.filter((e) => locals.has(e.name.text)) : [];
    return [...(clause?.name !== undefined && locals.has(clause.name.text) ? [clause.name] : []), ...named];
  });
  return [...exported, ...imported].map((node) => [node.getStart(source), node.end]);
}

/** One retarget's rename locations decided site by site. */
class Sites {
  readonly refusals: Finding[] = [];
  readonly needs: Need[] = [];
  private moving = new Set<TS.ImportSpecifier>();

  constructor(
    private readonly session: RetargetSession,
    private readonly target: Retarget & { home: Home },
  ) {}

  /** The target's declarations among `symbol`'s, the symbol followed through imports. */
  private isTarget(checker: TS.TypeChecker, symbol: TS.Symbol | undefined): boolean {
    const resolved = followed(checker, symbol);
    return resolved !== undefined && declarationKeys(resolved, resolved.name).some((k) => this.target.identity.has(k));
  }

  decide(live: Edit[], held: Set<TS.ImportSpecifier>): Edit[] {
    for (const edit of live) {
      const specifier = this.specifierAt(edit);
      if (specifier !== null && !held.has(specifier)) this.moving.add(specifier);
    }
    return live.flatMap((edit) => {
      const found = this.session.sources.get(edit.path);
      if (found === undefined) return [edit];
      const node = nodeAt(found.source, edit.start);
      const specifier = this.specifierAt(edit);
      if (specifier !== null) return this.moving.has(specifier) ? this.importSite(found, edit, specifier) : [];
      if (bareReference(node)) {
        this.use(found, edit, node);
        return [edit];
      }
      return this.member(found, edit, node);
    });
  }

  specifierAt(edit: Edit): TS.ImportSpecifier | null {
    const found = this.session.sources.get(edit.path);
    if (found === undefined) return null;
    const node = nodeAt(found.source, edit.start);
    const parent = node.parent;
    return inImport(parent) && (parent.propertyName ?? parent.name) === node ? parent : null;
  }

  /** The module `declaration` imports from exports the target under its name. */
  private exportsTarget(checker: TS.TypeChecker, declaration: TS.ImportDeclaration): boolean {
    const module = checker.getSymbolAtLocation(declaration.moduleSpecifier);
    return module !== undefined && checker.getExportsOfModule(module).some((e) => e.name === this.target.original && this.isTarget(checker, e));
  }

  /** An import of the alias from a module exporting the target re-pointed to it there; from any other module, the
   * alias left and the target imported from its home. */
  private importSite(found: ProjectSource, edit: Edit, specifier: TS.ImportSpecifier): Edit[] {
    const { source, checker } = found;
    const declaration = declarationOf(specifier);
    if (this.exportsTarget(checker, declaration)) return duplicateImport(source, checker, specifier, edit, this.target.newName) ?? [edit];
    const local = specifier.propertyName !== undefined ? specifier.name.text : this.target.newName;
    const symbol = checker.getSymbolAtLocation(specifier.name);
    const uses = [...walk(source)].filter((n) => ts().isIdentifier(n) && n !== specifier.name && n.text === specifier.name.text && this.local(checker, n) === symbol);
    const type = isTypeOnly(specifier) || (uses.length > 0 && uses.every(typeUse));
    this.need(found, declaration, local, type, specifier);
    return [];
  }

  private local(checker: TS.TypeChecker, node: TS.Node): TS.Symbol | undefined {
    return ts().isShorthandPropertyAssignment(node.parent) && node.parent.name === node ? checker.getShorthandAssignmentValueSymbol(node.parent) : checker.getSymbolAtLocation(node);
  }

  private need(found: ProjectSource, anchor: TS.ImportDeclaration, local: string, type: boolean, leaving: TS.ImportSpecifier | null): void {
    const local0 = local === this.target.newName ? this.target.original : local;
    const [bound, duplicates] = this.bindings(found, anchor, local0, type);
    this.needs.push({ path: found.source.fileName, anchor, home: this.target.home, local, type, bind: !bound, leaving, duplicates });
  }

  /** Whether the anchor's block binds `local` to the target (in the meaning needed) at or before `anchor`; the later
   * imports of the target under `local`. */
  private bindings(found: ProjectSource, anchor: TS.ImportDeclaration, local: string, type: boolean): [boolean, TS.ImportSpecifier[]] {
    const { checker } = found;
    const block = anchor.parent as TS.SourceFile | TS.ModuleBlock;
    const at = block.statements.indexOf(anchor);
    let bound = false;
    const later: TS.ImportSpecifier[] = [];
    for (const [i, statement] of block.statements.entries()) {
      if (ts().isImportDeclaration(statement)) {
        const bindings = statement.importClause?.namedBindings;
        const named = bindings !== undefined && ts().isNamedImports(bindings) ? bindings.elements : [];
        for (const e of named) {
          if (e.name.text !== local || (e.propertyName ?? e.name).text === this.target.old || !this.isTarget(checker, checker.getSymbolAtLocation(e.name))) continue;
          if (i <= at && (type || !isTypeOnly(e))) bound = true;
          else if (i > at) later.push(e);
        }
      } else if (i < at && this.declares(statement, local)) {
        bound = true;
      }
    }
    return [bound, bound ? [] : later];
  }

  private declares(statement: TS.Statement, local: string): boolean {
    const source = statement.getSourceFile();
    const names = ts().isVariableStatement(statement) ? statement.declarationList.declarations.map((d) => d.name) : [(statement as { name?: TS.Node }).name];
    return names.some((n) => n !== undefined && ts().isIdentifier(n) && n.text === local && this.target.identity.has(keyOf(source.fileName, n.getStart(source))));
  }

  /** A bare use: the target imported where its binding import stays; refused where the target's name means
   * something else. */
  private use(found: ProjectSource, edit: Edit, node: TS.Node): void {
    const { checker } = found;
    const binding = bindingOf(checker, node);
    const type = typeUse(node);
    if (binding !== null && !this.moving.has(binding)) this.need(found, declarationOf(binding), this.target.newName, type, null);
    const meaning = type ? ts().SymbolFlags.Type : ts().SymbolFlags.Value;
    const bound = checker.resolveName(this.target.newName, node, meaning, false);
    if (bound !== undefined && !this.isTarget(checker, bound)) {
      this.refusals.push(this.session.finding(edit.path, edit.start, 'refactor.retarget-shadowed', { name: this.target.newName }));
    }
  }

  /** `MOD.ALIAS` through a namespace import rewritten where module `MOD` exports the target under its name; refused
   * otherwise. Any other member access is rewritten. */
  private member(found: ProjectSource, edit: Edit, node: TS.Node): Edit[] {
    const { checker } = found;
    const parent = node.parent;
    const receiver = ts().isPropertyAccessExpression(parent) && parent.name === node ? parent.expression : ts().isQualifiedName(parent) && parent.right === node ? parent.left : undefined;
    const module = receiver === undefined ? undefined : followed(checker, checker.getSymbolAtLocation(receiver));
    const declaration = module?.valueDeclaration ?? module?.declarations?.[0];
    if (module === undefined || declaration === undefined || !ts().isSourceFile(declaration)) return [edit];
    if (checker.getExportsOfModule(module).some((e) => e.name === this.target.original && this.isTarget(checker, e))) return [edit];
    this.refusals.push(this.session.finding(edit.path, edit.start, 'refactor.retarget-unbound', { module: this.session.r.rel(declaration.fileName), name: this.target.newName }));
    return [];
  }
}

/** A retarget's rename locations checked and adjusted: overrides, shadowed and unbound names as findings; its
 * re-export sites and kept lines dropped (its own declarations stay, to classify it as a member); the imports of the
 * target the rest need recorded. */
export function retargetSites(session: RetargetSession, target: Retarget, kept: (path: string, position: number) => boolean, needs: Need[]): Finding[] {
  const findings: Finding[] = [];
  const members = [...session.sources.values()].flatMap(({ source, checker }) => memberDeclarations(checker, source, target.old, source.fileName));
  const located = new Set(target.edits.map((e) => keyOf(e.path, e.start)));
  for (const d of members) {
    if (located.has(keyOf(d.path, d.start)) && !target.own.has(keyOf(d.path, d.start))) {
      findings.push(session.finding(d.path, d.start, 'refactor.retarget-override', { cls: d.owner, name: target.old }));
    }
  }
  const spans = new Map<string, [number, number][]>();
  const reexported = (edit: Edit): boolean => {
    const source = session.sources.get(edit.path)?.source;
    if (source === undefined) return false;
    if (!spans.has(edit.path)) spans.set(edit.path, reexportSpans(source, target.old));
    return (spans.get(edit.path) ?? []).some(([start, end]) => start <= edit.start && edit.start < end);
  };
  const own = target.edits.filter((e) => target.own.has(keyOf(e.path, e.start)));
  const edits = target.edits.filter((e) => !own.includes(e) && !reexported(e));
  const live = edits.filter((e) => !kept(e.path, e.start));
  const home = target.home;
  if (home === null) {
    target.edits = [...own, ...live];
    return findings;
  }
  const held = new Set<TS.ImportSpecifier>();
  for (const edit of edits.filter((e) => !live.includes(e))) {
    const found = session.sources.get(edit.path);
    const binding = found === undefined ? null : bindingOf(found.checker, nodeAt(found.source, edit.start));
    if (binding !== null) held.add(binding);
  }
  const sites = new Sites(session, { ...target, home });
  target.edits = [...own, ...sites.decide(live, held)];
  needs.push(...sites.needs);
  return [...findings, ...sites.refusals];
}

const named = (exported: string, local: string): string => (exported === local ? exported : `${exported} as ${local}`);

/** One file's needs, planned block by block. */
class FilePlan {
  readonly edits: Edit[] = [];
  private readonly leaving = new Map<TS.ImportSpecifier, Need>();
  private readonly inPlace = new Set<TS.ImportDeclaration>();

  constructor(
    private readonly found: ProjectSource,
    private readonly needs: Need[],
  ) {
    for (const need of needs) if (need.leaving !== null) this.leaving.set(need.leaving, need);
  }

  private get source(): TS.SourceFile {
    return this.found.source;
  }

  plan(): Edit[] {
    const ordered = this.needs.toSorted((a, b) => a.anchor.getStart(this.source) - b.anchor.getStart(this.source) || (a.leaving?.getStart(this.source) ?? 0) - (b.leaving?.getStart(this.source) ?? 0));
    const blocks = new Map<TS.Node, Map<string, Need[]>>();
    for (const need of ordered) {
      const homes = blocks.get(need.anchor.parent) ?? new Map<string, Need[]>();
      const key = need.home.file ?? need.home.specifier ?? '';
      homes.set(key, [...(homes.get(key) ?? []), need]);
      blocks.set(need.anchor.parent, homes);
    }
    const duplicates = new Set<TS.ImportSpecifier>();
    for (const homes of blocks.values()) {
      for (const group of homes.values()) {
        const binding = group.filter((n) => n.bind);
        if (binding.length === 0) continue;
        this.place(binding);
        for (const n of binding) for (const d of n.duplicates) duplicates.add(d);
      }
    }
    const removals = new Map<TS.ImportDeclaration, Set<TS.ImportSpecifier>>();
    const remove = (specifier: TS.ImportSpecifier): void => {
      const declaration = declarationOf(specifier);
      removals.set(declaration, (removals.get(declaration) ?? new Set()).add(specifier));
    };
    for (const need of this.needs) if (need.leaving !== null && !this.inPlace.has(need.anchor)) remove(need.leaving);
    for (const d of duplicates) remove(d);
    for (const [declaration, removed] of removals) this.edits.push(...removeSpecifiers(this.source, declaration, removed));
    return this.edits;
  }

  /** The names a group binds, each type-only when every need of it is. */
  private names(group: Need[]): { exported: string; local: string; type: boolean }[] {
    const out = new Map<string, { exported: string; local: string; type: boolean }>();
    for (const n of group) {
      const key = `${n.home.exported}\0${n.local}`;
      const prior = out.get(key);
      out.set(key, { exported: n.home.exported, local: n.local, type: (prior?.type ?? true) && n.type });
    }
    return [...out.values()];
  }

  private place(group: Need[]): void {
    const first = (group[0] as Need).anchor;
    const names = this.names(group);
    const joined = this.joinTarget(group[0] as Need, names.every((n) => n.type));
    if (joined !== null) this.append(joined, names);
    else if (this.replaceable(first, group[0] as Need)) this.replace(first, names);
    else this.insertAfter(first, group[0] as Need, names);
  }

  private sameModule(declaration: TS.ImportDeclaration, home: Home): boolean {
    const file = moduleFile(this.found.checker, declaration.moduleSpecifier);
    return home.file !== null ? file === home.file : specifierText(declaration.moduleSpecifier) === home.specifier;
  }

  /** An earlier import of the anchor's block from the home whose names all stay, and whose type-onliness fits. */
  private joinTarget(need: Need, type: boolean): TS.ImportDeclaration | null {
    const block = need.anchor.parent as TS.SourceFile | TS.ModuleBlock;
    for (const statement of block.statements) {
      if (statement === need.anchor) return null;
      if (!ts().isImportDeclaration(statement) || !this.sameModule(statement, need.home)) continue;
      const bindings = statement.importClause?.namedBindings;
      if (bindings === undefined || !ts().isNamedImports(bindings) || bindings.elements.length === 0) continue;
      if (bindings.elements.some((e) => this.leaving.has(e)) || (statement.importClause?.isTypeOnly === true && !type)) continue;
      return statement;
    }
    return null;
  }

  private elements(declaration: TS.ImportDeclaration): readonly TS.ImportSpecifier[] {
    const bindings = declaration.importClause?.namedBindings;
    return bindings !== undefined && ts().isNamedImports(bindings) ? bindings.elements : [];
  }

  /** Every name of `declaration` leaves it for the need's home, and it binds nothing else. */
  private replaceable(declaration: TS.ImportDeclaration, need: Need): boolean {
    const elements = this.elements(declaration);
    const sameHome = (e: TS.ImportSpecifier): boolean => {
      const home = this.leaving.get(e)?.home;
      return home !== undefined && (home.file ?? home.specifier) === (need.home.file ?? need.home.specifier);
    };
    return !this.inPlace.has(declaration) && declaration.importClause?.name === undefined && elements.length > 0 && elements.every(sameHome);
  }

  private append(declaration: TS.ImportDeclaration, names: { exported: string; local: string; type: boolean }[]): void {
    const elements = this.elements(declaration);
    const present = new Set(elements.map((e) => `${(e.propertyName ?? e.name).text}\0${e.name.text}`));
    const typeOnly = declaration.importClause?.isTypeOnly === true;
    const added = names.filter((n) => !present.has(`${n.exported}\0${n.local}`)).map((n) => `${n.type && !typeOnly ? 'type ' : ''}${named(n.exported, n.local)}`);
    if (added.length === 0) return;
    const end = (elements[elements.length - 1] as TS.ImportSpecifier).end;
    this.edits.push({ path: this.source.fileName, start: end, length: 0, newText: added.map((a) => `, ${a}`).join('') });
  }

  private spell(declaration: TS.ImportDeclaration, home: Home): string {
    if (home.file === null || (home.specifier !== null && !home.specifier.startsWith('.'))) return home.specifier ?? '';
    const anchor = specifierText(declaration.moduleSpecifier) ?? '';
    const extension = /\.[cm]?[jt]sx?$/u.exec(anchor)?.[0] ?? '';
    let path = stripSourceExtension(home.file);
    if (basename(path) === 'index' && home.specifier !== null && !/(^|\/)index(\.\w+)?$/u.test(home.specifier)) path = dirname(path);
    else path = `${path}${extension}`;
    const rel = posix(relative(dirname(this.source.fileName), path));
    return rel.startsWith('.') ? rel : `./${rel}`;
  }

  private replace(declaration: TS.ImportDeclaration, names: { exported: string; local: string; type: boolean }[]): void {
    this.inPlace.add(declaration);
    const path = this.source.fileName;
    const elements = this.elements(declaration);
    const home = (this.leaving.get(elements[0] as TS.ImportSpecifier) as Need).home;
    const specifier = declaration.moduleSpecifier;
    this.edits.push({ path, start: specifier.getStart(this.source) + 1, length: specifier.getWidth(this.source) - 2, newText: this.spell(declaration, home) });
    const clause = declaration.importClause as TS.ImportClause;
    if (names.every((n) => n.type) && !clause.isTypeOnly) this.edits.push({ path, start: clause.getStart(this.source), length: 0, newText: 'type ' });
    const written = new Set<string>();
    for (const e of elements) {
      const need = this.leaving.get(e) as Need;
      const property = e.propertyName ?? e.name;
      const text = e.propertyName !== undefined ? need.home.exported : named(need.home.exported, need.local);
      this.edits.push({ path, start: property.getStart(this.source), length: property.getWidth(this.source), newText: text });
      written.add(`${need.home.exported}\0${need.local}`);
    }
    const rest = names.filter((n) => !written.has(`${n.exported}\0${n.local}`)).map((n) => named(n.exported, n.local));
    if (rest.length > 0) this.edits.push({ path, start: (elements[elements.length - 1] as TS.ImportSpecifier).end, length: 0, newText: rest.map((r) => `, ${r}`).join('') });
  }

  private insertAfter(anchor: TS.ImportDeclaration, need: Need, names: { exported: string; local: string; type: boolean }[]): void {
    const source = this.source;
    const text = source.text;
    const start = anchor.getStart(source);
    const lineStart = text.lastIndexOf('\n', start - 1) + 1;
    const head = text.slice(lineStart, start);
    const indent = head.trim() === '' ? head : head.slice(0, head.length - head.trimStart().length);
    const allType = names.every((n) => n.type);
    const list = names.map((n) => `${n.type && !allType ? 'type ' : ''}${named(n.exported, n.local)}`).join(', ');
    const quote = anchor.moduleSpecifier.getText(source)[0] ?? "'";
    const semicolon = anchor.getText(source).trimEnd().endsWith(';') ? ';' : '';
    const statement = `${indent}import ${allType ? 'type ' : ''}{ ${list} } from ${quote}${this.spell(anchor, need.home)}${quote}${semicolon}`;
    const newline = text.indexOf('\n', anchor.end);
    if (newline === -1) this.edits.push({ path: source.fileName, start: text.length, length: 0, newText: `\n${statement}` });
    else this.edits.push({ path: source.fileName, start: newline + 1, length: 0, newText: `${statement}${text[newline - 1] === '\r' ? '\r\n' : '\n'}` });
  }
}

/** The edits binding every need's target and dropping the alias from the imports it leaves. */
export function planImports(session: RetargetSession, needs: Need[]): Edit[] {
  const byFile = new Map<string, Need[]>();
  for (const need of needs) byFile.set(need.path, [...(byFile.get(need.path) ?? []), need]);
  return [...byFile].flatMap(([path, fileNeeds]) => {
    const found = session.sources.get(path);
    return found === undefined ? [] : new FilePlan(found, fileNeeds).plan();
  });
}
