// `shared/vectors/refactor-text.yaml` through the npm twin's text primitives.
import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import type * as TS from 'typescript';
import { describe, expect, it } from 'vitest';
import { ts } from '../src/lang/index.js';
import { Lines } from '../src/refactor/lines.js';
import { memberDeclarations } from '../src/refactor/members.js';
import { mentions, qualifierSegments } from '../src/refactor/mentions.js';
import { Site } from '../src/refactor/sites.js';
import { vectors } from './helpers.js';

type Vector = Record<string, any> & { name: string; typescript?: Record<string, unknown> };

const VECTORS = vectors('refactor-text.yaml');
const expected = (v: Vector, key: string): any => v.typescript?.[key] ?? v[key];
/** The UTF-16 offset of code point offset `points` in `text`. */
const utf16 = (text: string, points: number): number => [...text].slice(0, points).join('').length;
const points = (text: string, offset: number): number => [...text.slice(0, offset)].length;

describe('lines', () => {
  for (const v of VECTORS.lines as Vector[]) {
    it(v.name, () => {
      const lines = new Lines(v.text);
      const offsets = (v.offsets as number[]).map((o) => utf16(v.text, o));
      expect(offsets.map((o) => lines.lineOf(o))).toEqual(expected(v, 'lines'));
      expect(lines.count).toBe(expected(v, 'count'));
      const compiler = ts().createSourceFile('a.ts', v.text, ts().ScriptTarget.Latest, true);
      expect(offsets.map((o) => compiler.getLineAndCharacterOfPosition(o).line + 1)).toEqual(expected(v, 'lines'));
    });
  }
});

describe('mentions', () => {
  for (const v of VECTORS.mentions as Vector[]) {
    it(v.name, () => {
      const text: string = v.text;
      const regions = ((v.regions as [number, number][] | undefined) ?? [[0, [...text].length]]).map(([s, e]) => ({
        start: utf16(text, s),
        end: utf16(text, e),
        where: 'string' as const,
        opens: false,
      }));
      expect(mentions(text, v.old, regions).map((m) => points(text, m.start))).toEqual(expected(v, 'starts'));
    });
  }
});

describe('qualifiers', () => {
  for (const v of VECTORS.qualifiers as Vector[]) {
    it(v.name, () => {
      expect(qualifierSegments(v.text, utf16(v.text, v.at))).toEqual(expected(v, 'segments'));
    });
  }
});

describe('sites', () => {
  for (const v of VECTORS.sites as Vector[]) {
    it(v.name, () => {
      const root = join(realpathSync(mkdtempSync(join(tmpdir(), 'la-site-vectors-'))), 'project');
      mkdirSync(root);
      for (const rel of v.files as string[]) {
        mkdirSync(dirname(join(root, rel)), { recursive: true });
        writeFileSync(join(root, rel), '');
      }
      const site = Site.parse(v.site, root, root);
      expect((v.checks as [string, number, boolean][]).map(([path, line]) => [path, line, site.covers(path, line)])).toEqual(v.checks);
    });
  }
});

describe('the line index users', () => {
  it('a stand-in declaration and a finding on a CR-only file agree on lines', () => {
    const text = 'export class A {\r  a = 1;\r  saveModel(): void {}\r}\r';
    const dir = realpathSync(mkdtempSync(join(tmpdir(), 'la-cr-lines-')));
    writeFileSync(join(dir, 'a.ts'), text);
    const program = ts().createProgram([join(dir, 'a.ts')], { noEmit: true });
    const source = program.getSourceFile(join(dir, 'a.ts')) as TS.SourceFile;
    const [declared] = memberDeclarations(program.getTypeChecker(), source, 'saveModel', 'a.ts');
    expect(declared?.line).toBe(3);
    expect(new Lines(text).lineOf(text.indexOf('saveModel'))).toBe(3);
  });
});
