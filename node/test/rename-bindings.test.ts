// dr-refactor rename keeps every reference's binding: identity by declaration set, per-meaning resolution, check order.
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { files, read, refactor, tsProject } from './refactor-project.js';

const conflict = (name: string, path: string, line: number): string => `${message('refactor.name-conflict', { name, path, line })}\n`;

function renameSymbol(project: Record<string, string>, file: string, symbol: string, newName: string, ...flags: string[]): { root: string; result: ReturnType<typeof refactor> } {
  const root = tsProject(project);
  return { root, result: refactor(root, '--apply', 'rename', '--file', file, '--symbol', symbol, '--new-name', newName, ...flags) };
}

describe('identity by declaration set', () => {
  it('renames a function merged with a namespace as one symbol', () => {
    const m = 'export function old(): number {\n  return old.base;\n}\n\nexport namespace old {\n  export const base = 1;\n}\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'old', 'fresh');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/m.ts')).toBe(m.replace(/\bold\b/gu, 'fresh'));
  });

  it('follows an aliased import to its target: the alias keeps its name beside a local of the new name', () => {
    const use = "import { old as alias } from './m';\n\nconst next = 2;\nexport const total = alias + next;\n";
    const { root, result } = renameSymbol({ 'src/m.ts': 'export const old = 1;\n', 'src/use.ts': use }, 'src/m.ts', 'old', 'next');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/use.ts')).toBe(use.replace('{ old as alias }', '{ next as alias }'));
  });

  it('refuses an overload group renamed onto a function its module declares', () => {
    const m = 'export function old(x: number): number;\nexport function old(x: string): string;\nexport function old(x: number | string): number | string {\n  return x;\n}\n\nexport function next(): number {\n  return 0;\n}\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'old', 'next');
    expect(result).toEqual({ code: 1, out: '', err: conflict('next', 'src/m.ts', 7) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });
});

describe('per-meaning resolution', () => {
  it('lets an interface take the name of a constant: a type and a value', () => {
    const m = 'export interface Old {\n  a: number;\n}\n\nexport const Next = 1;\n\nexport const x: Old = { a: Next };\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'Old', 'Next');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/m.ts')).toBe(m.replace(/\bOld\b/gu, 'Next'));
  });

  it('refuses a type alias renamed onto an interface: one meaning', () => {
    const m = 'export type Old = { a: number };\n\nexport interface Next {\n  b: number;\n}\n\nexport const x: Old = { a: 1 };\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'Old', 'Next');
    expect(result).toEqual({ code: 1, out: '', err: conflict('Next', 'src/m.ts', 3) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });

  it('refuses a type reference captured by a local type of the new name', () => {
    const m = 'export type Old = number;\n\nexport function f(): number {\n  type Next = string;\n  const v: Old = 1;\n  const w: Next = "w";\n  return v + w.length;\n}\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'Old', 'Next');
    expect(result).toEqual({ code: 1, out: '', err: conflict('Next', 'src/m.ts', 4) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });
});

describe('member namespace', () => {
  const method = '\n  old(): number {\n    return 1;\n  }\n}\n';
  it.each([
    ['a field', 'export class C {\n  fresh = 0;\n' + method, 'C.old', 2],
    ['an accessor', 'export class C {\n  get fresh(): number {\n    return 0;\n  }\n' + method, 'C.old', 2],
    ['an interface property', 'export interface I {\n  fresh: number;\n  old(): number;\n}\n', 'I.old', 2],
    ['an enum member', 'export enum E {\n  old,\n  fresh,\n}\n', 'E.old', 3],
  ])('refuses a member renamed onto %s of its type', (_kind, m, symbol, line) => {
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', symbol, 'fresh');
    expect(result).toEqual({ code: 1, out: '', err: conflict('fresh', 'src/m.ts', line) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });
});

describe('check order', () => {
  it('checks after --keep: a kept reference that would have been captured is no conflict', () => {
    const m = 'export const old = 1;\n\nexport function f(): number {\n  const next = 2;\n  return old + next;\n}\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'old', 'next', '--keep', 'src/m.ts:5');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/m.ts')).toBe(m.replace('export const old', 'export const next'));
  });

  it('reports a name conflict before the blind-spot refusal', () => {
    const m = 'export class C {\n  old(): number {\n    return 1;\n  }\n\n  next(): number {\n    return 2;\n  }\n}\n';
    const loose = 'export function g(o: any): number {\n  return o.old();\n}\n';
    const project = { 'src/m.ts': m, 'src/loose.ts': loose };
    const { root, result } = renameSymbol(project, 'src/m.ts', 'C.old', 'next');
    expect(result).toEqual({ code: 1, out: '', err: conflict('next', 'src/m.ts', 6) });
    expect(files(root)).toMatchObject(project);
  });
});

describe('finding site', () => {
  it('names the first site by path, then offset', () => {
    const use = "import { old } from './m';\n\nexport function f(): number {\n  const next = 1;\n  return old + next;\n}\n\nexport function g(): number {\n  const next = 2;\n  return old + next;\n}\n";
    const { result } = renameSymbol({ 'src/m.ts': 'export const old = 1;\n', 'src/z_use.ts': use, 'src/a_use.ts': use }, 'src/m.ts', 'old', 'next');
    expect(result).toEqual({ code: 1, out: '', err: conflict('next', 'src/a_use.ts', 4) });
  });
});
