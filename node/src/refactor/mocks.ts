// TypeScript mock lint: Vitest/Jest doubles bound to a type, module factories typed against a resolvable module.
import { relative } from 'node:path';
import type * as TS from 'typescript';
import { globMatch, language, message } from '../contract/index.js';
import { posix, ts } from '../lang/index.js';

/** A finding at a UTF-16 position of its file. */
export interface Finding {
  position: number;
  text: string;
}

type Framework = 'vitest' | 'jest';

const FRAMEWORK_MODULES: Record<string, Framework> = { vitest: 'vitest', '@jest/globals': 'jest' };
const GLOBALS: Record<string, Framework> = { vi: 'vitest', jest: 'jest' };
const MODULE_MOCKS = new Set(['mock', 'doMock', 'unstable_mockModule']);

/** The framework `receiver` is bound to: an import of `vi`/`jest` from its module, or the unshadowed global. */
function framework(checker: TS.TypeChecker, receiver: TS.Identifier): Framework | null {
  const symbol = checker.getSymbolAtLocation(receiver);
  const declarations = symbol?.declarations ?? [];
  if (declarations.length === 0 || declarations.every((d) => d.getSourceFile().isDeclarationFile)) {
    return GLOBALS[receiver.text] ?? null;
  }
  const [declaration] = declarations;
  if (declaration === undefined || !ts().isImportSpecifier(declaration)) return null;
  const specifier = declaration.parent.parent.parent.moduleSpecifier;
  const from = ts().isStringLiteral(specifier) ? FRAMEWORK_MODULES[specifier.text] : undefined;
  return from !== undefined && GLOBALS[(declaration.propertyName ?? declaration.name).text] === from ? from : null;
}

function resolves(program: TS.Program, file: TS.SourceFile, specifier: string): boolean {
  const resolved = ts().resolveModuleName(specifier, file.fileName, program.getCompilerOptions(), ts().sys);
  return resolved.resolvedModule !== undefined;
}

/** The module the factory is typed against (Vitest: `import('m')` first argument; Jest: `<typeof import('m')>`). */
function typedModule(call: TS.CallExpression, kind: Framework): string | null {
  if (kind === 'vitest') {
    const [first] = call.arguments;
    const isImport = first !== undefined && ts().isCallExpression(first) && first.expression.kind === ts().SyntaxKind.ImportKeyword;
    const [module] = isImport ? first.arguments : [];
    return module !== undefined && ts().isStringLiteral(module) ? module.text : null;
  }
  const [type] = call.typeArguments ?? [];
  if (type === undefined || !ts().isImportTypeNode(type) || !type.isTypeOf) return null;
  const literal = ts().isLiteralTypeNode(type.argument) ? type.argument.literal : undefined;
  return literal !== undefined && ts().isStringLiteral(literal) ? literal.text : null;
}

function* walk(node: TS.Node): Generator<TS.Node> {
  yield node;
  for (const child of node.getChildren()) yield* walk(child);
}

const unwrap = (node: TS.Expression): TS.Expression => (ts().isParenthesizedExpression(node) ? unwrap(node.expression) : node);

/** A double assertion `x as unknown as T` / `x as any as T`: the keyword it passes through. */
function doubleAssertion(node: TS.Node): string | null {
  if (!ts().isAsExpression(node)) return null;
  const inner = unwrap(node.expression);
  if (!ts().isAsExpression(inner)) return null;
  if (inner.type.kind === ts().SyntaxKind.UnknownKeyword) return 'unknown';
  return inner.type.kind === ts().SyntaxKind.AnyKeyword ? 'any' : null;
}

/** `shown`'s mock-lint findings (`shown` is the path as printed; casts only in test-glob files under `repoRoot`). */
export function mockFindings(program: TS.Program, file: string, shown: string, repoRoot: string): Finding[] {
  const source = program.getSourceFile(file);
  if (source === undefined) return [];
  const checker = program.getTypeChecker();
  const testGlobs: string[] = language('typescript').test_globs;
  const inTests = testGlobs.some((glob) => globMatch(glob, posix(relative(repoRoot, file))));
  const line = (node: TS.Node): number => source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
  const out: Finding[] = [];
  for (const node of walk(source)) {
    const via = inTests ? doubleAssertion(node) : null;
    if (via !== null) out.push({ position: node.getStart(source), text: message('mock-lint.cast', { path: shown, line: line(node), via }) });
    if (!ts().isCallExpression(node) || !ts().isPropertyAccessExpression(node.expression)) continue;
    const { expression: receiver, name } = node.expression;
    if (!ts().isIdentifier(receiver)) continue;
    const kind = framework(checker, receiver);
    if (kind === null) continue;
    const call = `${receiver.text}.${name.text}`;
    const values = { path: shown, line: line(node), call };
    if (name.text === 'fn' && node.typeArguments === undefined && node.arguments.length === 0) {
      out.push({ position: node.getStart(source), text: message('mock-lint.fn', values) });
    }
    const factory = node.arguments[1];
    if (MODULE_MOCKS.has(name.text) && factory !== undefined && !ts().isObjectLiteralExpression(factory)) {
      const module = typedModule(node, kind);
      if (module === null || !resolves(program, source, module)) {
        out.push({ position: node.getStart(source), text: message('mock-lint.module', values) });
      }
    }
  }
  return out;
}
