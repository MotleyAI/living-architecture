// Every kind a dr-compliance finding prints is a check id `--select` accepts (parse-error aside).
import { describe, expect, it } from 'vitest';
import { findings, language, languageIds, message } from '../src/contract/index.js';
import { run } from './cli-run.js';
import { tsProject } from './refactor-project.js';

describe('dr-compliance kinds', () => {
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
});

describe('dr-compliance --attr, repeated', () => {
  it('reports every name in one block sorted by path, line and column', () => {
    const loose = 'export function f(a: any, b: any): number {\n  return b.saveModel() + a.getModel();\n}\n\nexport function g(c: any): number {\n  return c.getModel();\n}\n';
    const root = tsProject({ 'src/m.ts': loose, 'src/a.ts': 'export function h(d: any): number {\n  return d.saveModel();\n}\n' });
    const result = run(root, 'dr-compliance', ['--select', 'attr-blindspot', '--attr', 'saveModel', '--attr', 'getModel', 'src']);
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

describe('dr-compliance --attr, receiver text', () => {
  it('keeps the parentheses written around a receiver and collapses its whitespace', () => {
    const loose = 'export function g(a: unknown, o: any): number {\n  return (a as any).id + (\n    o\n  ).id;\n}\n';
    const root = tsProject({ 'src/m.ts': loose });
    const result = run(root, 'dr-compliance', ['--select', 'attr-blindspot', '--attr', 'id', 'src']);
    const spot = (receiver: string): string =>
      message('compliance.attr-blindspot', { path: 'src/m.ts', line: 2, receiver, attr: 'id', type: 'any' });
    expect(result).toEqual({ code: 1, out: `${spot('(a as any)')}\n${spot('( o )')}\n`, err: '' });
  });
});
