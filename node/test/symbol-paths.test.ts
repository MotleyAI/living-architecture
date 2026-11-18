// dr-refactor --symbol: a declaration by its path inside --file, through the TypeScript twin.
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { copyProject, entryRefusal, files, lineCol, read, refactor, tsProject } from './refactor-project.js';

const STORE = `export class Store {
  count(): number {
    const total = 1;
    return total;
  }

  getModel(modelName: string): number {
    return modelName.length;
  }

  saveModel(modelName: string): void {
    console.log(modelName);
  }
}

export interface Shape {
  measure(): number;
}

export enum Color {
  Red = 'red',
  Blue = 'blue',
}

export namespace Ns {
  export const value = 1;
}

export type Options = { modelCount: number; other: string };

export type Kind = 'edit_model' | 'drop';

export function build(): number {
  function inner(): number {
    return 1;
  }
  return inner();
}

export function inner(): number {
  return 2;
}

export const make = (): number => {
  const local = 3;
  return local;
};
`;

const USE = `import { Color, Ns, Store, build, inner, make, type Kind, type Options, type Shape } from './store';

export function use(s: Store, o: Options, k: Kind, sh: Shape): number {
  const kind: Kind = 'edit_model';
  const blue = Color.Blue === 'blue' ? 1 : 0;
  return s.getModel('a') + s.count() + o.modelCount + sh.measure() + Ns.value + build() + inner() + make() + blue + (k === kind ? 1 : 0);
}
`;

/** `--symbol` against `--line/--col` at `needle` on two copies of one project: same streams, code and files. */
function expectSameAsLineCol(project: Record<string, string>, symbol: string, needle: string, newName: string, nth = 0, shift = 0): void {
  const bySymbol = tsProject(project);
  const byPosition = copyProject(bySymbol);
  const position = lineCol(byPosition, 'src/store.ts', needle, nth, shift);
  const expected = refactor(byPosition, '--apply', 'rename', '--file', 'src/store.ts', ...position, '--new-name', newName);
  expect(expected.code).toBe(0);
  const actual = refactor(bySymbol, '--apply', 'rename', '--file', 'src/store.ts', '--symbol', symbol, '--new-name', newName);
  expect(actual).toEqual(expected);
  expect(files(bySymbol)).toEqual(files(byPosition));
}

const project = { 'src/store.ts': STORE, 'src/use.ts': USE };

describe('symbol paths', () => {
  it.each([
    ['Store.getModel', 'getModel(modelName', 'loadModel', 0, 0],
    ['Shape.measure', 'measure(): number;', 'area', 0, 0],
    ['Color.Blue', 'Blue =', 'Navy', 0, 0],
    ['Ns.value', 'value = 1', 'amount', 0, 0],
    ['Options.modelCount', 'modelCount: number', 'modelTotal', 0, 0],
    ['build.<locals>.inner', 'inner(): number', 'nested', 0, 0],
    ['inner', 'inner(): number', 'outer', 1, 0],
    ['make.<locals>.local', 'local = 3', 'three', 0, 0],
    ['Store.count.<locals>.total', 'total = 1', 'sum', 0, 0],
    ['Store.getModel(modelName)', 'modelName', 'datasetName', 0, 0],
    ['Store.saveModel(modelName)', 'modelName', 'payload', 2, 0],
    ["Kind['edit_model']", "'edit_model' | 'drop'", 'edit_master', 0, 1],
    ['Kind["edit_model"]', "'edit_model' | 'drop'", 'edit_master', 0, 1],
  ])('%s locates the declaration --line/--col names', (symbol, needle, newName, nth, shift) => {
    expectSameAsLineCol(project, symbol, needle, newName, nth, shift);
  });

  it('an interface method signature parameter locates as --line/--col does', () => {
    const service = 'export interface Service {\n  run(input: string): void;\n}\n';
    expectSameAsLineCol({ 'src/store.ts': service }, 'Service.run(input)', 'input: string', 'payload');
  });

  it('a nested function never renames the same-named top-level one', () => {
    const root = tsProject(project);
    expect(refactor(root, '--apply', 'rename', '--file', 'src/store.ts', '--symbol', 'build.<locals>.inner', '--new-name', 'nested').code).toBe(0);
    expect(read(root, 'src/store.ts')).toContain('export function inner(): number {\n  return 2;');
    expect(read(root, 'src/use.ts')).toBe(USE);
  });

  it('an import binding locates the declaration it imports', () => {
    const viaImport = tsProject(project);
    const viaDeclaration = copyProject(viaImport);
    const atDeclaration = refactor(viaDeclaration, '--apply', 'rename', '--file', 'src/store.ts', '--symbol', 'Store', '--new-name', 'Repo');
    const atImport = refactor(viaImport, '--apply', 'rename', '--file', 'src/use.ts', '--symbol', 'Store', '--new-name', 'Repo');
    expect(atImport).toEqual(atDeclaration);
    expect(files(viaImport)).toEqual(files(viaDeclaration));
  });
});

describe('declarations of one symbol', () => {
  const GROUPED = `export function pick(x: string): string;
export function pick(x: number): number;
export function pick(x: string | number): string | number {
  return x;
}

export class Box {
  private n = 0;

  get size(): number {
    return this.n;
  }

  set size(v: number) {
    this.n = v;
  }
}

export namespace Box {
  export const empty = new Box();
}

export interface Merged {
  a: number;
}

export interface Merged {
  b: number;
}

export namespace Ns {
  export const value = 1;
}

export namespace Ns {
  export const other = 2;
}
`;
  const USE_GROUPED = `import { Box, Ns, pick, type Merged } from './store';

export const m: Merged = { a: 1, b: 2 };
export const picked = [pick('a'), pick(1)];
const box = new Box();
box.size = 3;
export const sizes = [box.size, Box.empty.size, Ns.value + Ns.other];
`;
  const grouped = { 'src/store.ts': GROUPED, 'src/use.ts': USE_GROUPED };

  it.each([
    ['pick', 'pick(x: string)', 'choose'],
    ['Box.size', 'size(): number', 'length'],
    ['Box.empty', 'empty =', 'blank'],
    ['Merged', 'Merged {', 'Joined'],
    ['Ns', 'Ns {', 'Space'],
    ['Ns.other', 'other = 2', 'second'],
  ])('%s is one symbol, located at its first declaration', (symbol, needle, newName) => {
    expectSameAsLineCol(grouped, symbol, needle, newName);
  });

  it('renames every declaration of an overloaded function and of an accessor pair', () => {
    const root = tsProject(grouped);
    expect(refactor(root, '--apply', 'rename', '--file', 'src/store.ts', '--symbol', 'pick', '--new-name', 'choose').code).toBe(0);
    expect(refactor(root, '--apply', 'rename', '--file', 'src/store.ts', '--symbol', 'Box.size', '--new-name', 'length').code).toBe(0);
    const text = read(root, 'src/store.ts');
    expect(text.match(/function choose\(/g)).toHaveLength(3);
    expect(text).toContain('get length(): number');
    expect(text).toContain('set length(v: number)');
    expect(read(root, 'src/use.ts')).toContain('box.length = 3;');
  });
});

describe('locator failures', () => {
  it('an unresolved path exits 2 listing the declarations of its deepest resolved scope', () => {
    const root = tsProject(project);
    const before = files(root);
    const result = refactor(root, 'rename', '--file', 'src/store.ts', '--symbol', 'Store.getModle', '--new-name', 'x');
    const expected = message('refactor.symbol-unresolved', { path: 'src/store.ts', symbol: 'Store.getModle', candidates: 'count, getModel, saveModel' });
    expect(result).toEqual({ code: 2, out: '', err: `${entryRefusal('src/store.ts Store.getModle', expected)}\n` });
    expect(files(root)).toEqual(before);
  });

  it('a path reaching two symbols exits 2 listing each site', () => {
    const root = tsProject({ 'src/store.ts': 'export function f(): number {\n  {\n    const x = 1;\n  }\n  {\n    const x = 2;\n    return x;\n  }\n}\n' });
    const result = refactor(root, 'rename', '--file', 'src/store.ts', '--symbol', 'f.<locals>.x', '--new-name', 'y');
    const expected = message('refactor.symbol-ambiguous', { path: 'src/store.ts', symbol: 'f.<locals>.x', candidates: 'src/store.ts:3, src/store.ts:6' });
    expect(result).toEqual({ code: 2, out: '', err: `${entryRefusal('src/store.ts f.<locals>.x', expected)}\n` });
  });

  it.each([
    ['rename', ['--new-name', 'bar']],
    ['move-symbol', ['--dest', 'src/use.ts']],
    ['retarget', ['--target', 'Store']],
  ])('%s refuses two locators as a usage error naming both', (subcommand, rest) => {
    const root = tsProject(project);
    const result = refactor(root, subcommand, '--file', 'src/store.ts', '--line', '1', '--symbol', 'Store', ...rest);
    expect(result.code).toBe(2);
    expect(result.out).toBe('');
    expect(result.err).toContain('--line');
    expect(result.err).toContain('--symbol');
  });

  it('--name is gone', () => {
    const root = tsProject(project);
    expect(refactor(root, 'rename', '--file', 'src/store.ts', '--name', 'Store', '--new-name', 'Repo').code).toBe(2);
  });

  it('no locator exits 1 with the no-locator finding naming --symbol', () => {
    const root = tsProject(project);
    const result = refactor(root, 'rename', '--file', 'src/store.ts', '--new-name', 'Repo');
    expect(result).toEqual({ code: 1, out: '', err: `${entryRefusal('src/store.ts', message('refactor.no-locator'))}\n` });
    expect(result.err).toContain('--symbol');
  });
});

describe('move-symbol --symbol', () => {
  it('moves a top-level declaration as --line/--col does', () => {
    const bySymbol = tsProject({ ...project, 'src/dest.ts': 'export {};\n' });
    const byPosition = copyProject(bySymbol);
    const expected = refactor(byPosition, '--apply', 'move-symbol', '--file', 'src/store.ts', ...lineCol(byPosition, 'src/store.ts', 'make ='), '--dest', 'src/dest.ts');
    expect(expected.code).toBe(0);
    expect(refactor(bySymbol, '--apply', 'move-symbol', '--file', 'src/store.ts', '--symbol', 'make', '--dest', 'src/dest.ts')).toEqual(expected);
    expect(files(bySymbol)).toEqual(files(byPosition));
  });

  it('refuses a member path', () => {
    const root = tsProject({ ...project, 'src/dest.ts': 'export {};\n' });
    const result = refactor(root, 'move-symbol', '--file', 'src/store.ts', '--symbol', 'Store.getModel', '--dest', 'src/dest.ts');
    expect(result).toEqual({ code: 1, out: '', err: `${message('refactor.not-movable', { path: 'src/store.ts' })}\n` });
  });
});
