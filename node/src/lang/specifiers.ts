// The module specifiers of a source file's runtime imports; type-only forms are excluded by syntax alone.
import type * as TS from 'typescript';
import { ts } from './ts.js';

function importCounts(node: TS.ImportDeclaration): boolean {
  const clause = node.importClause;
  if (clause === undefined) return true;
  if (clause.phaseModifier === ts().SyntaxKind.TypeKeyword) return false;
  const bindings = clause.namedBindings;
  if (clause.name !== undefined || bindings === undefined || ts().isNamespaceImport(bindings)) return true;
  return bindings.elements.length === 0 || bindings.elements.some((e) => !e.isTypeOnly);
}

function exportCounts(node: TS.ExportDeclaration): boolean {
  if (node.isTypeOnly) return false;
  const clause = node.exportClause;
  if (clause === undefined || ts().isNamespaceExport(clause)) return true;
  return clause.elements.length === 0 || clause.elements.some((e) => !e.isTypeOnly);
}

function callSpecifier(node: TS.CallExpression): TS.StringLiteral | undefined {
  const [arg] = node.arguments;
  if (arg === undefined || !ts().isStringLiteral(arg)) return undefined;
  const callee = node.expression;
  const isImport = callee.kind === ts().SyntaxKind.ImportKeyword;
  const isRequire = ts().isIdentifier(callee) && callee.text === 'require';
  return isImport || isRequire ? arg : undefined;
}

function specifier(node: TS.Node): TS.StringLiteral | undefined {
  if (ts().isImportDeclaration(node)) {
    return importCounts(node) && ts().isStringLiteral(node.moduleSpecifier) ? node.moduleSpecifier : undefined;
  }
  if (ts().isExportDeclaration(node)) {
    const spec = node.moduleSpecifier;
    return spec !== undefined && ts().isStringLiteral(spec) && exportCounts(node) ? spec : undefined;
  }
  if (ts().isImportEqualsDeclaration(node)) {
    const ref = node.moduleReference;
    const counts = !node.isTypeOnly && ts().isExternalModuleReference(ref) && ts().isStringLiteral(ref.expression);
    return counts ? (ref.expression as TS.StringLiteral) : undefined;
  }
  return ts().isCallExpression(node) ? callSpecifier(node) : undefined;
}

/** Specifier literals of static imports/exports, `import x = require()`, and literal `import()`/`require()`. */
export function runtimeSpecifiers(file: TS.SourceFile): TS.StringLiteral[] {
  const found: TS.StringLiteral[] = [];
  const visit = (node: TS.Node): void => {
    const spec = specifier(node);
    if (spec !== undefined) found.push(spec);
    ts().forEachChild(node, visit);
  };
  visit(file);
  return found;
}
