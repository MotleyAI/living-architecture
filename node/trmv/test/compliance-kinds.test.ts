// Every kind a trmv-compliance finding prints is a check id `--select` accepts (parse-error aside).
import { describe, expect, it } from 'vitest';
import { findings, language, languageIds, message } from '../src/contract/index.js';
import { run } from './cli-run.js';
import { tsProject } from './refactor-project.js';

describe('trmv-compliance kinds', () => {
  const checks = new Set(languageIds().flatMap((id) => language(id).compliance_checks as string[]));
  const kinds = new Set(
    Object.entries(findings())
      .filter(([id]) => id.startsWith('compliance.'))
      .map(([, text]) => /^\{path\}(?::\{line\})?: ([a-z-]+):/.exec(text)?.[1])
      .filter((kind): kind is string => kind !== undefined),
  );

  it('prints attr-blindspot', () => {
    expect(kinds.has('attr-blindspot')).toBe(true);
  });

  it('selects every printed kind', () => {
    expect([...kinds].filter((kind) => kind !== 'parse-error' && !checks.has(kind))).toEqual([]);
  });

  it('lists attr-blindspot for both languages', () => {
    for (const id of ['python', 'typescript']) expect(language(id).compliance_checks).toContain('attr-blindspot');
  });

  it('prints string-blindspot, with and without the silent variant', () => {
    expect(kinds.has('string-blindspot')).toBe(true);
    for (const id of ['compliance.string-blindspot', 'compliance.string-blindspot-silent']) expect(findings()[id]).toMatch(/^\{path\}:\{line\}: string-blindspot: \{site\} /);
  });

  it('lists the attribute checks of each language', () => {
    const sorted = (id: string): string[] => (language(id).compliance_checks as string[]).toSorted();
    expect(sorted('python')).toEqual(['attr-blindspot', 'explicit-any', 'mock', 'rope-walk', 'string-blindspot', 'unannotated-attr', 'untyped-def']);
    expect(sorted('typescript')).toEqual(['attr-blindspot', 'explicit-any', 'mock', 'string-blindspot', 'tsconfig', 'untyped-def']);
  });
});

describe('trmv-compliance --attr, repeated', () => {
  it('reports every name in one block sorted by path, line and column', () => {
    const loose = 'export function f(a: any, b: any): number {\n  return b.saveModel() + a.getModel();\n}\n\nexport function g(c: any): number {\n  return c.getModel();\n}\n';
    const root = tsProject({ 'src/m.ts': loose, 'src/a.ts': 'export function h(d: any): number {\n  return d.saveModel();\n}\n' });
    const result = run(root, 'trmv-compliance', ['--select', 'attr-blindspot', '--attr', 'saveModel', '--attr', 'getModel', 'src']);
    const spot = (path: string, line: number, receiver: string, attr: string): string =>
      message('compliance.attr-blindspot', { path, line, receiver, attr, type: 'any' });
    const lines = [
      spot('src/a.ts', 2, 'd', 'saveModel'),
      spot('src/m.ts', 2, 'b', 'saveModel'),
      spot('src/m.ts', 2, 'a', 'getModel'),
      spot('src/m.ts', 6, 'c', 'getModel'),
    ];
    expect(result).toEqual({ code: 1, out: lines.map((line) => `${line}\n`).join(''), err: '' });
  });
});

describe('trmv-compliance --attr, receiver text', () => {
  it('keeps the parentheses written around a receiver and collapses its whitespace', () => {
    const loose = 'export function g(a: unknown, o: any): number {\n  return (a as any).id + (\n    o\n  ).id;\n}\n';
    const root = tsProject({ 'src/m.ts': loose });
    const result = run(root, 'trmv-compliance', ['--select', 'attr-blindspot', '--attr', 'id', 'src']);
    const spot = (receiver: string): string =>
      message('compliance.attr-blindspot', { path: 'src/m.ts', line: 2, receiver, attr: 'id', type: 'any' });
    expect(result).toEqual({ code: 1, out: `${spot('(a as any)')}\n${spot('( o )')}\n`, err: '' });
  });
});

describe('trmv-compliance string-blindspot', () => {
  const loose = [
    'export function f(x: any): unknown[] {',
    '  return [',
    '    x.columns,',
    "    x['columns'],",
    '    x["columns"],',
    "    Reflect.get(x, 'columns'),",
    "    Reflect.set(x, 'columns', 1),",
    '    Reflect.has(',
    '      x',
    '        .inner,',
    "      'columns',",
    '    ),',
    '  ];',
    '}',
    '',
  ].join('\n');
  const values = { path: 'src/m.ts', attr: 'columns', type: 'any' };
  const access = `${message('compliance.attr-blindspot', { ...values, line: 3, receiver: 'x' })}\n`;
  const named = (): string =>
    [
      message('compliance.string-blindspot', { ...values, line: 4, receiver: 'x', site: "x['columns']" }),
      message('compliance.string-blindspot', { ...values, line: 5, receiver: 'x', site: "x['columns']" }),
      message('compliance.string-blindspot', { ...values, line: 6, receiver: 'x', site: "Reflect.get(x, 'columns')" }),
      message('compliance.string-blindspot', { ...values, line: 7, receiver: 'x', site: "Reflect.set(x, 'columns', …)" }),
      message('compliance.string-blindspot', { ...values, line: 8, receiver: 'x .inner', site: "Reflect.has(x .inner, 'columns')" }),
    ]
      .map((line) => `${line}\n`)
      .join('');
  const compliance = (...argv: string[]) => run(tsProject({ 'src/m.ts': loose }), 'trmv-compliance', [...argv, 'src']);

  it('reports both attribute checks without --select, sorted by position', () => {
    const any = `${message('compliance.explicit-any', { path: 'src/m.ts', line: 1, any: 'any', top: 'unknown' })}\n`;
    expect(compliance('--attr', 'columns')).toEqual({ code: 1, out: any + access + named(), err: '' });
  });

  it('reports only the string-named accesses when selected', () => {
    expect(compliance('--select', 'string-blindspot', '--attr', 'columns')).toEqual({ code: 1, out: named(), err: '' });
  });

  it('leaves the string-named accesses out of attr-blindspot', () => {
    expect(compliance('--select', 'attr-blindspot', '--attr', 'columns')).toEqual({ code: 1, out: access, err: '' });
  });

  it.each([['string-blindspot'], ['string-blindspot,attr-blindspot'], ['untyped-def,string-blindspot']])('--select %s needs --attr, naming the first attribute check', (select) => {
    const err = `${message('compliance.attr-required', { check: 'string-blindspot' })}\n`;
    expect(compliance('--select', select)).toEqual({ code: 2, out: '', err });
  });

  it('takes --attr with string-blindspot alone selected', () => {
    expect(compliance('--select', 'string-blindspot', '--attr', 'missing')).toEqual({ code: 0, out: '', err: '' });
  });
});
