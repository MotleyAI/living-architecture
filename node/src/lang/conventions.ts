// TS/JS conventions facts: rule detections with their line text, line counts, and file failures.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type * as TS from 'typescript';
import { message } from '../contract/index.js';
import { sourceExtension } from './files.js';
import { commentRanges, lineCounts, LineMap } from './lines.js';
import { ts } from './ts.js';

export interface Detection {
  line: number;
  rule: string;
  message_id: string;
  values: Record<string, string | number>;
  text: string;
}

export type ConventionsFileFacts =
  | {
      path: string;
      status: 'ok';
      detections: Detection[];
      text_lines: number;
      total_lines: number;
      comment_lines: number;
      doc_lines: number;
    }
  | { path: string; status: 'missing' }
  | { path: string; status: 'unreadable'; line: number; message: string }
  | { path: string; status: 'syntax-error'; line: number; message: string; comment_lines: number; doc_lines: number };

type Hit = { node: TS.Node; rule: string; messageId: string; values?: Record<string, number> };

const THROW_MATCHERS = new Set([
  'toThrow',
  'toThrowError',
  'toThrowErrorMatchingSnapshot',
  'toThrowErrorMatchingInlineSnapshot',
]);

function scriptKind(path: string): TS.ScriptKind {
  const kinds = ts().ScriptKind;
  const ext = sourceExtension(path);
  if (ext === '.tsx') return kinds.TSX;
  if (ext === '.jsx') return kinds.JSX;
  if (ext === '.js' || ext === '.mjs' || ext === '.cjs') return kinds.JS;
  return kinds.TS;
}

const isIdentifier = (node: TS.Node, name: string): boolean => ts().isIdentifier(node) && node.text === name;

function stripParens(node: TS.Expression): TS.Expression {
  let out = node;
  while (ts().isParenthesizedExpression(out)) out = out.expression;
  return out;
}

/** import/first: a static import after any other statement; leading string directives are prologue. */
function importsAfterCode(file: TS.SourceFile): Hit[] {
  const hits: Hit[] = [];
  let prologue = true;
  let code = false;
  for (const statement of file.statements) {
    if (prologue && ts().isExpressionStatement(statement) && ts().isStringLiteral(statement.expression)) continue;
    prologue = false;
    const isImport =
      ts().isImportDeclaration(statement) ||
      (ts().isImportEqualsDeclaration(statement) && ts().isExternalModuleReference(statement.moduleReference));
    if (!isImport) code = true;
    else if (code) {
      hits.push({ node: statement, rule: 'import-not-top', messageId: 'conventions.ts-import-after-code' });
    }
  }
  return hits;
}

/** n/global-require: every ancestor of a `require()` call must be one of these (parentheses are transparent). */
function requireAtTop(call: TS.CallExpression): boolean {
  const k = ts().SyntaxKind;
  for (let node: TS.Node | undefined = call.parent; node !== undefined; node = node.parent) {
    switch (node.kind) {
      case k.ParenthesizedExpression:
      case k.VariableDeclaration:
      case k.VariableDeclarationList:
      case k.VariableStatement:
      case k.PropertyAccessExpression:
      case k.ElementAccessExpression:
      case k.ExpressionStatement:
      case k.CallExpression:
      case k.ConditionalExpression:
        continue;
      case k.SourceFile:
        return true;
      case k.BinaryExpression: {
        const op = (node as TS.BinaryExpression).operatorToken.kind;
        if (op >= k.FirstAssignment && op <= k.LastAssignment) continue;
        return false;
      }
      default:
        return false;
    }
  }
  return true;
}

function countCalls(node: TS.Node | undefined): number {
  if (node === undefined) return 0;
  let count = ts().isCallExpression(node) || ts().isNewExpression(node) ? 1 : 0;
  ts().forEachChild(node, (child) => {
    count += countCalls(child);
  });
  return count;
}

/** The property names chained on `call` up to the call of the last one, or undefined when no call ends the chain. */
function matcherChain(call: TS.CallExpression): string[] | undefined {
  const names: string[] = [];
  let current: TS.Node = call;
  for (;;) {
    const parent: TS.Node = current.parent;
    if (ts().isPropertyAccessExpression(parent) && parent.expression === current) {
      names.push(parent.name.text);
      current = parent;
    } else if (ts().isCallExpression(parent) && parent.expression === current && names.length > 0) {
      return names;
    } else {
      return undefined;
    }
  }
}

/** The expression whose calls a throw assertion counts, or undefined when `call` is not one. */
function throwSubject(call: TS.CallExpression): TS.Node | null | undefined {
  const callee = call.expression;
  const [first] = call.arguments;
  if (ts().isPropertyAccessExpression(callee) && isIdentifier(callee.expression, 'assert')) {
    return ['throws', 'rejects'].includes(callee.name.text) ? (first ?? null) : undefined;
  }
  if (!isIdentifier(callee, 'expect')) return undefined;
  const chain = matcherChain(call);
  if (chain === undefined) return undefined;
  if (chain.includes('rejects')) return first ?? null;
  const matcher = chain[chain.length - 1] ?? '';
  return THROW_MATCHERS.has(matcher) && !chain.includes('not') ? (first ?? null) : undefined;
}

function isCompositeAssert(call: TS.CallExpression): boolean {
  const callee = call.expression;
  const asserting =
    isIdentifier(callee, 'expect') ||
    isIdentifier(callee, 'assert') ||
    (ts().isPropertyAccessExpression(callee) && isIdentifier(callee.expression, 'assert') && callee.name.text === 'ok');
  const [first] = call.arguments;
  if (!asserting || first === undefined) return false;
  const arg = stripParens(first);
  return ts().isBinaryExpression(arg) && arg.operatorToken.kind === ts().SyntaxKind.AmpersandAmpersandToken;
}

function callHits(file: TS.SourceFile): Hit[] {
  const hits: Hit[] = [];
  const visit = (node: TS.Node): void => {
    if (ts().isCallExpression(node)) {
      if (isIdentifier(node.expression, 'require') && !requireAtTop(node)) {
        hits.push({ node, rule: 'import-not-top', messageId: 'conventions.ts-require-not-top' });
      }
      if (isCompositeAssert(node)) {
        hits.push({ node, rule: 'composite-assert', messageId: 'conventions.ts-composite-assert' });
      }
      const subject = throwSubject(node);
      const calls = subject === undefined ? 0 : countCalls(subject ?? undefined);
      if (calls > 1) {
        const messageId = 'conventions.ts-raises-single-throw';
        hits.push({ node, rule: 'raises-single-throw', messageId, values: { calls } });
      }
    }
    ts().forEachChild(node, visit);
  };
  visit(file);
  return hits;
}

function decode(bytes: Buffer): string | undefined {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    return undefined;
  }
}

function analyze(path: string, text: string): ConventionsFileFacts {
  const file = ts().createSourceFile(
    path,
    text,
    { languageVersion: ts().ScriptTarget.Latest, jsDocParsingMode: ts().JSDocParsingMode.ParseNone },
    true,
    scriptKind(path),
  );
  const lines = new LineMap(text);
  const counts = lineCounts(lines, commentRanges(file));
  const [diagnostic] = ((file as any).parseDiagnostics ?? []) as TS.DiagnosticWithLocation[];
  if (diagnostic !== undefined) {
    return {
      path,
      status: 'syntax-error',
      line: lines.lineOf(diagnostic.start),
      message: ts().flattenDiagnosticMessageText(diagnostic.messageText, '\n'),
      comment_lines: counts.comment_lines,
      doc_lines: counts.doc_lines,
    };
  }
  const detections = [...importsAfterCode(file), ...callHits(file)]
    .map((hit) => {
      const line = lines.lineOf(hit.node.getStart(file));
      return { line, rule: hit.rule, message_id: hit.messageId, values: hit.values ?? {}, text: lines.lineText(line) };
    })
    .sort((a, b) => a.line - b.line || (a.rule < b.rule ? -1 : a.rule > b.rule ? 1 : 0));
  return {
    path,
    status: 'ok',
    detections,
    text_lines: counts.text_lines,
    total_lines: lines.count,
    comment_lines: counts.comment_lines,
    doc_lines: counts.doc_lines,
  };
}

function fileFacts(root: string, path: string): ConventionsFileFacts {
  let bytes: Buffer;
  try {
    bytes = readFileSync(resolve(root, path));
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === 'ENOENT' || code === 'ENOTDIR') return { path, status: 'missing' };
    return { path, status: 'unreadable', line: 1, message: (error as Error).message };
  }
  const text = decode(bytes);
  if (text === undefined) return { path, status: 'unreadable', line: 1, message: message('conventions.not-utf8') };
  return analyze(path, text);
}

/** The conventions facts of each path (relative to `root`), in input order. */
export function conventionsFacts(root: string, paths: string[]): ConventionsFileFacts[] {
  return paths.map((path) => fileFacts(root, path));
}
