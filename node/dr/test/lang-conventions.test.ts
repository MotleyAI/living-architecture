// The TypeScript adapter's conventions facts, through src/lang/index.ts: one entry per path, as in the facts document.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { conventionsFacts } from '../src/lang/index.js';

const ROOT = mkdtempSync(join(tmpdir(), 'la-lang-conventions-'));
afterAll(() => rmSync(ROOT, { recursive: true, force: true }));

let serial = 0;

/** The facts entry for `content` written to a fresh repo at `rel`. */
function facts(rel: string, content: string | Buffer): any {
  const repo = join(ROOT, String(serial++));
  mkdirSync(dirname(join(repo, rel)), { recursive: true });
  writeFileSync(join(repo, rel), content);
  const [entry] = conventionsFacts(repo, [rel]);
  return entry;
}

/** `line:message_id` per detection. */
function hits(rel: string, content: string): string[] {
  return facts(rel, content).detections.map((d: any) => `${d.line}:${d.message_id}`);
}

const AFTER = 'conventions.ts-import-after-code';
const REQUIRE = 'conventions.ts-require-not-top';
const COMPOSITE = 'conventions.ts-composite-assert';
const THROW = 'conventions.ts-raises-single-throw';

describe('import-not-top', () => {
  it('flags static imports after other statements', () => {
    const src = "const x = 1;\nimport a from 'a';\nimport type { T } from 't';\nimport fs = require('fs');\n";
    expect(hits('a.ts', src)).toEqual([`2:${AFTER}`, `3:${AFTER}`, `4:${AFTER}`]);
  });

  it('allows a directive prologue, but a top-level require or export-from ends it', () => {
    expect(hits('a.ts', "'use client';\n'use strict';\nimport a from 'a';\n")).toEqual([]);
    expect(hits('b.ts', "const fs = require('fs');\nimport a from 'a';\n")).toEqual([`2:${AFTER}`]);
    expect(hits('c.ts', "export * from './c';\nimport a from 'a';\n")).toEqual([`2:${AFTER}`]);
  });

  it('flags require() outside module scope by the global-require ancestors', () => {
    const src = [
      "const a = require('a').b;",
      "module.exports = f(require('c'), x ? require('d') : null);",
      "function g() { return require('e'); }",
      "if (x) { require('f'); }",
      "const o = { p: require('p') };",
      "const h = () => module.require('h');",
      '',
    ].join('\n');
    expect(hits('a.cjs', src)).toEqual([`3:${REQUIRE}`, `4:${REQUIRE}`, `5:${REQUIRE}`]);
  });

  it('never flags dynamic or type-position import(), export-from or declare module bodies', () => {
    const src = [
      "import a from 'a';",
      'export const x = a;',
      "export const lazy = () => import('./lazy');",
      "let t: import('./t').T;",
      "declare module 'm' { import b from 'b'; }",
      "export * from './c';",
      '',
    ].join('\n');
    expect(hits('a.ts', src)).toEqual([]);
  });
});

describe('test-file rules (emitted for every file; the gate filters)', () => {
  it('composite-assert on expect/assert/assert.ok of a parenthesized &&, not ||', () => {
    const src = 'expect(a && b);\nassert((a && b));\nassert.ok(a && b);\nexpect(a || b);\nexpect(a && b || c);\n';
    expect(hits('a.ts', src)).toEqual([`1:${COMPOSITE}`, `2:${COMPOSITE}`, `3:${COMPOSITE}`]);
  });

  it('raises-single-throw counts calls and `new` under toThrow*, rejects and assert.throws/rejects', () => {
    const src = [
      'expect(() => f(g())).toThrow();',
      'expect(() => new F(g())).toThrowErrorMatchingInlineSnapshot();',
      'await expect(f(g())).rejects.toThrow();',
      'assert.throws(() => f(g()));',
      'await assert.rejects(async () => f(g()));',
      'expect(() => {',
      '  f(g());',
      '}).toThrowError();',
      'expect(() => f()).toThrow();',
      'expect(() => f(g())).not.toThrow();',
      '',
    ].join('\n');
    const entry = facts('a.test.ts', src);
    expect(entry.detections.map((d: any) => `${d.line}:${d.message_id}:${d.values.calls}`)).toEqual(
      [1, 2, 3, 4, 5, 6].map((line) => `${line}:${THROW}:2`),
    );
  });
});

describe('detections carry their line text', () => {
  it('keeps a trailing waiver comment for the gate to read', () => {
    const entry = facts('a.ts', "export const x = 1;\nimport a from 'a'; // ALLOW(import-not-top): generated\n");
    expect(entry.detections).toEqual([
      {
        line: 2,
        rule: 'import-not-top',
        message_id: AFTER,
        values: {},
        text: "import a from 'a'; // ALLOW(import-not-top): generated",
      },
    ]);
  });
});

describe('line sets', () => {
  it('text-only lines, totals, comment and doc lines', () => {
    const src = [
      '/**',
      ' * Doc.',
      ' */',
      '/* a',
      '   b */ const x = 1; // trailing',
      "const s = '// not a comment'; /** trailing doc */",
      '/**/',
      '',
    ].join('\n');
    expect(facts('a.ts', src)).toMatchObject({
      status: 'ok',
      text_lines: 5,
      total_lines: 7,
      comment_lines: 3,
      doc_lines: 4,
    });
  });

  it('BOM, CRLF, lone CR and a missing final newline do not change the counts', () => {
    const lf = '// one\nconst a = 1;\n/* two\n   three */\n';
    const counts = (entry: any) => [entry.text_lines, entry.total_lines, entry.comment_lines, entry.doc_lines];
    const expected = counts(facts('lf.ts', lf));
    expect(expected).toEqual([3, 4, 3, 0]);
    expect(counts(facts('crlf.ts', `\uFEFF${lf.replaceAll('\n', '\r\n')}`))).toEqual(expected);
    expect(counts(facts('cr.ts', lf.replaceAll('\n', '\r')))).toEqual(expected);
    expect(counts(facts('eof.ts', lf.trimEnd()))).toEqual(expected);
  });
});

describe('failures', () => {
  it('invalid UTF-8 is unreadable', () => {
    expect(facts('a.ts', Buffer.from([0x78, 0x20, 0xff, 0x0a]))).toEqual({
      path: 'a.ts',
      status: 'unreadable',
      line: 1,
      message: 'not valid UTF-8',
    });
  });

  it('a syntax error reports the first parse diagnostic and still counts comments', () => {
    expect(facts('a.ts', '// one\n/* two */\nconst x = ;\n')).toEqual({
      path: 'a.ts',
      status: 'syntax-error',
      line: 3,
      message: 'Expression expected.',
      comment_lines: 2,
      doc_lines: 0,
    });
  });

  it('a missing path, in input order with the others', () => {
    const repo = join(ROOT, 'missing');
    mkdirSync(repo);
    writeFileSync(join(repo, 'b.ts'), 'export const b = 1;\n');
    expect(conventionsFacts(repo, ['a.ts', 'b.ts']).map((e: any) => [e.path, e.status])).toEqual([
      ['a.ts', 'missing'],
      ['b.ts', 'ok'],
    ]);
  });
});
