// dr-refactor rename keeps every reference's binding: identity by declaration set, per-meaning resolution, check order.
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { identifierText } from '../src/refactor/bindings.js';
import { files, lineCol, read, refactor, tsProject } from './refactor-project.js';

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

  it("refuses a rename that rebinds a re-export's re-exported name", () => {
    const project = {
      'src/other.ts': "export const next = 'other';\n",
      'src/m.ts': "export * from './other';\nexport const old = 1;\n",
      'src/barrel.ts': "export { next as q } from './m';\n",
      'src/use.ts': "import { q } from './barrel';\n\nexport const v = q;\n",
    };
    const { root, result } = renameSymbol(project, 'src/m.ts', 'old', 'next');
    expect(result).toEqual({ code: 1, out: '', err: conflict('next', 'src/barrel.ts', 1) });
    expect(files(root)).toMatchObject(project);
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

  it('refuses a member renamed onto a computed key of its type, by the key value', () => {
    const m = 'const key = "next";\n\nexport class C {\n  old(): number {\n    return 1;\n  }\n\n  [key](): number {\n    return 2;\n  }\n}\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'C.old', 'next');
    expect(result).toEqual({ code: 1, out: '', err: conflict('next', 'src/m.ts', 8) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });

  it('renames a variable read in a computed key: no member rename', () => {
    const m = 'export const old = "actual";\n\nexport class C {\n  [old](): number {\n    return 1;\n  }\n\n  next(): number {\n    return 2;\n  }\n}\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'old', 'next');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/m.ts')).toBe(m.replace('const old', 'const next').replace('[old]', '[next]'));
  });

  it('refuses a shorthand property renamed onto a property of its object', () => {
    const m = 'const old = 1;\n\nexport const obj = { old, next: 2 };\nexport const v = obj.old;\n';
    const root = tsProject({ 'src/m.ts': m });
    const result = refactor(root, '--apply', 'rename', '--file', 'src/m.ts', ...lineCol(root, 'src/m.ts', 'obj.old', 0, 4), '--new-name', 'next');
    expect(result).toEqual({ code: 1, out: '', err: conflict('next', 'src/m.ts', 3) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });
});

describe('quoted and escaped names', () => {
  it.each([
    [String.raw`o\u006cd`, 'old'],
    [String.raw`o\u{6c}d`, 'old'],
    ['old', 'old'],
    [String.raw`o\u{110000}d`, String.raw`o\u{110000}d`],
  ])('decodes the identifier %s', (raw, name) => {
    expect(identifierText(raw)).toBe(name);
  });

  it('refuses a reference in a destructuring default captured by a local of the new name', () => {
    const m = 'export const old = 1;\n\nexport function f(): number {\n  const next = 2;\n  const { x = old } = {} as { x?: number };\n  return x + next;\n}\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'old', 'next');
    expect(result).toEqual({ code: 1, out: '', err: conflict('next', 'src/m.ts', 4) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });

  it('refuses a map renaming two members of a class onto one name, one of them spelled with an escape', () => {
    const m = 'export class C {\n  a(): number {\n    return 1;\n  }\n\n  b(): number {\n    return 2;\n  }\n}\n';
    const map = String.raw`- {file: src/m.ts, symbol: C.a, new_name: next}
- {file: src/m.ts, symbol: C.b, new_name: n\u0065xt}
`;
    const root = tsProject({ 'src/m.ts': m, 'renames.yaml': map });
    const result = refactor(root, '--apply', 'rename-map', 'renames.yaml');
    expect(result).toEqual({ code: 1, out: '', err: conflict('next', 'src/m.ts', 2) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });

  it('refuses a map renaming members of two declarations of one merged interface onto one name', () => {
    const m = 'export interface I {\n  a: number;\n}\n\nexport interface I {\n  b: string;\n}\n';
    const map = '- {file: src/m.ts, symbol: I.a, new_name: next}\n- {file: src/m.ts, symbol: I.b, new_name: next}\n';
    const root = tsProject({ 'src/m.ts': m, 'renames.yaml': map });
    const result = refactor(root, '--apply', 'rename-map', 'renames.yaml');
    expect(result).toEqual({ code: 1, out: '', err: conflict('next', 'src/m.ts', 2) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });

  it("refuses a member renamed onto a name another declaration of a descendant's merged interface declares", () => {
    const m = 'export interface Base {\n  a: number;\n}\n\nexport interface Mid extends Base {\n  c: number;\n}\n\nexport interface Mid {\n  b: string;\n}\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'Base.a', 'b');
    expect(result).toEqual({ code: 1, out: '', err: conflict('b', 'src/m.ts', 10) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });

  it('refuses a static member renamed onto the implicit prototype', () => {
    const m = 'export class C {\n  static old(): number {\n    return 1;\n  }\n}\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'C.old', 'prototype');
    expect(result).toEqual({ code: 1, out: '', err: conflict('prototype', 'src/m.ts', 2) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });

  it('checks a declaration spelled with a unicode escape by the name it spells', () => {
    const m = String.raw`export const o\u006cd = 1;

export function f(): number {
  const next = 2;
  return old + next;
}
`;
    const root = tsProject({ 'src/m.ts': m });
    const result = refactor(root, '--apply', 'rename', '--file', 'src/m.ts', ...lineCol(root, 'src/m.ts', String.raw`o\u`), '--new-name', 'next');
    expect(result).toEqual({ code: 1, out: '', err: conflict('next', 'src/m.ts', 4) });
    expect(read(root, 'src/m.ts')).toBe(m);
  });

  it('accepts a map retargeting onto a quoted enum member', () => {
    const m = 'export enum E {\n  "tgt" = 1,\n  als = 1,\n  z = als,\n}\n\nexport const other = 1;\n';
    const map = '- {file: src/m.ts, symbol: E.als, retarget: E.tgt}\n- {file: src/m.ts, symbol: other, new_name: other2}\n';
    const root = tsProject({ 'src/m.ts': m, 'renames.yaml': map });
    const result = refactor(root, '--apply', 'rename-map', 'renames.yaml');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/m.ts')).toBe(m.replace('z = als', 'z = tgt').replace('const other', 'const other2'));
  });

  it('checks a source spelling the new name only with a unicode escape', () => {
    const b = String.raw`namespace N {
  export function f(): string {
    return n\u0065xt;
  }
}
`;
    const project = { 'src/a.ts': 'namespace N {\n  export const old = 1;\n}\n', 'src/b.ts': b, 'src/c.ts': "const next = 'outer';\n" };
    const { root, result } = renameSymbol(project, 'src/a.ts', 'N.old', 'next');
    expect(result).toEqual({ code: 1, out: '', err: conflict('next', 'src/b.ts', 3) });
    expect(files(root)).toMatchObject(project);
  });
});

describe('check order', () => {
  it('checks after --keep: a kept reference that would have been captured is no conflict', () => {
    const m = 'export const old = 1;\n\nexport function f(): number {\n  const next = 2;\n  return old + next;\n}\n';
    const { root, result } = renameSymbol({ 'src/m.ts': m }, 'src/m.ts', 'old', 'next', '--keep', 'src/m.ts:5');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/m.ts')).toBe(m.replace('export const old', 'export const next'));
  });

  it('reports a name conflict with the blind-spot refusal', () => {
    const m = 'export class C {\n  old(): number {\n    return 1;\n  }\n\n  next(): number {\n    return 2;\n  }\n}\n';
    const loose = 'export function g(o: any): number {\n  return o.old();\n}\n';
    const project = { 'src/m.ts': m, 'src/loose.ts': loose };
    const { root, result } = renameSymbol(project, 'src/m.ts', 'C.old', 'next');
    const blindspot = message('compliance.attr-blindspot', { path: 'src/loose.ts', line: 2, receiver: 'o', attr: 'old', type: 'any' });
    const closing = message('refactor.blindspots', { count: 1, attr: 'old' });
    expect(result).toEqual({ code: 1, out: '', err: `${blindspot}\n${conflict('next', 'src/m.ts', 6)}${closing}\n` });
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
