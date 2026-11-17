// dr-refactor rename-map: many renames as one dry-run and one all-or-nothing apply, through the TypeScript twin.
import { chmodSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { message, schema, validate } from '../src/contract/index.js';
import { TSCONFIG, copyProject, expectedOut, files, lineCol, mapYaml, read, refactor, refactorRaw, renameHeader, tsProject } from './refactor-project.js';

const STORE = `export class Store {
  getModel(modelName: string): number {
    return modelName.length;
  }

  getModelSync(modelName: string): number {
    return this.getModel(modelName);
  }
}
`;
const USE = `import { Store } from './store';

export function use(s: Store): number {
  return s.getModel('a') + s.getModelSync('b');
}
`;

function withMap(project: Record<string, string>, entries: Record<string, string | number>[]): string {
  return tsProject({ ...project, 'map.yaml': mapYaml(entries) });
}

describe('rename-map schema', () => {
  it.each([
    [[{ file: 'src/a.ts', symbol: 'A.old', new_name: 'fresh' }]],
    [[{ file: 'src/a.ts', line: 3, new_name: 'fresh' }]],
    [[{ file: 'src/a.ts', line: 3, col: 9, new_name: 'fresh' }]],
    [[{ file: 'src/a.ts', offset: 120, new_name: 'fresh' }]],
    [[{ file: 'src/models.ts', symbol: 'AcmeModel', retarget: 'Model' }]],
    [[{ file: 'src/a.ts', symbol: 'A.old', new_name: 'fresh' }, { file: 'src/a.ts', symbol: "Kind['edit_model']", new_name: 'edit master' }]],
    [[{ module: 'src/a.ts', new_name: 'b' }]],
    [[{ module: 'pkg/sql/__init__.py', new_name: 'db' }, { file: 'pkg/a.py', symbol: 'f', new_name: 'g' }]],
  ])('accepts %j', (document) => {
    expect(validate(schema('rename-map'), document)).toEqual([]);
  });

  it.each([
    [{ file: 'src/a.ts', symbol: 'A.old', new_name: 'fresh' }],
    [[]],
    [[{ file: 'src/a.ts', symbol: 'A.old', line: 3, new_name: 'fresh' }]],
    [[{ file: 'src/a.ts', offset: 1, line: 3, new_name: 'fresh' }]],
    [[{ file: 'src/a.ts', new_name: 'fresh' }]],
    [[{ file: 'src/a.ts', col: 3, new_name: 'fresh' }]],
    [[{ file: 'src/a.ts', symbol: 'A.old', new_name: 'fresh', retarget: 'A.fresh' }]],
    [[{ file: 'src/a.ts', symbol: 'A.old' }]],
    [[{ symbol: 'A.old', new_name: 'fresh' }]],
    [[{ file: 'src/a.ts', symbol: 'A.old', new_name: 'fresh', unsure: 'include' }]],
    [[{ file: 'src/a.ts', line: '3', new_name: 'fresh' }]],
    [[{ module: 'src/a.ts', symbol: 'A', new_name: 'b' }]],
    [[{ module: 'src/a.ts', retarget: 'A' }]],
    [[{ module: 'src/a.ts', file: 'src/a.ts', new_name: 'b' }]],
    [[{ module: 'src/a.ts' }]],
    [[{ module: '', new_name: 'b' }]],
  ])('rejects %j', (document) => {
    expect(validate(schema('rename-map'), document)).not.toEqual([]);
  });
});

describe('rename-map', () => {
  it('applies related renames in one pass: a header per entry, one diff per file', () => {
    const root = withMap({ 'src/store.ts': STORE, 'src/use.ts': USE }, [
      { file: 'src/store.ts', symbol: 'Store.getModel', new_name: 'loadModel' },
      { file: 'src/store.ts', symbol: 'Store.getModelSync', new_name: 'loadModelSync' },
      { file: 'src/store.ts', symbol: 'Store.getModel(modelName)', new_name: 'datasetName' },
    ]);
    const store = `export class Store {
  loadModel(datasetName: string): number {
    return datasetName.length;
  }

  loadModelSync(modelName: string): number {
    return this.loadModel(modelName);
  }
}
`;
    const use = USE.replace("s.getModel('a') + s.getModelSync('b')", "s.loadModel('a') + s.loadModelSync('b')");
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
    const headers = [renameHeader('getModel', 'loadModel'), renameHeader('getModelSync', 'loadModelSync'), renameHeader('modelName', 'datasetName')];
    const changes = [{ path: 'src/store.ts', old: STORE, new: store }, { path: 'src/use.ts', old: USE, new: use }];
    expect(result).toEqual({ code: 0, out: expectedOut(headers, changes, true), err: '' });
    expect([read(root, 'src/store.ts'), read(root, 'src/use.ts')]).toEqual([store, use]);
  });

  it('resolves every entry against the code before the map', () => {
    const a = 'export class A {\n  old(x: number): number {\n    return x;\n  }\n}\n\nexport const r = new A().old(1);\n';
    const root = withMap({ 'src/a.ts': a }, [
      { file: 'src/a.ts', symbol: 'A.old', new_name: 'fresh' },
      { file: 'src/a.ts', symbol: 'A.old(x)', new_name: 'y' },
    ]);
    expect(refactor(root, '--apply', 'rename-map', 'map.yaml').code).toBe(0);
    expect(read(root, 'src/a.ts')).toBe('export class A {\n  fresh(y: number): number {\n    return y;\n  }\n}\n\nexport const r = new A().fresh(1);\n');
  });

  it('reports the blind spots of every member entry in one refusal', () => {
    const loose = 'export function g(a: any, b: any): number {\n  return a.getModelSync() + b.getModel();\n}\n';
    const root = withMap({ 'src/store.ts': STORE, 'src/use.ts': USE, 'src/loose.ts': loose }, [
      { file: 'src/store.ts', symbol: 'Store.getModel', new_name: 'loadModel' },
      { file: 'src/store.ts', symbol: 'Store.getModelSync', new_name: 'loadModelSync' },
    ]);
    const before = files(root);
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
    const lines = result.err.trimEnd().split('\n');
    expect(result.code).toBe(1);
    expect(result.out).toBe('');
    expect(lines.slice(0, 2)).toEqual([
      message('compliance.attr-blindspot', { path: 'src/loose.ts', line: 2, receiver: 'a', attr: 'getModelSync', type: 'any' }),
      message('compliance.attr-blindspot', { path: 'src/loose.ts', line: 2, receiver: 'b', attr: 'getModel', type: 'any' }),
    ]);
    expect(lines).toHaveLength(3);
    expect(lines[2]).toBe(message('refactor.blindspots', { count: 2, attr: 'getModel, .getModelSync' }));
    expect(files(root)).toEqual(before);
  });

  it('merges entries locating one symbol with one change', () => {
    const merged = tsProject({ 'src/store.ts': STORE, 'src/use.ts': USE });
    const single = copyProject(merged);
    writeFileSync(join(merged, 'map.yaml'), mapYaml([
      { file: 'src/store.ts', symbol: 'Store.getModel', new_name: 'loadModel' },
      { file: 'src/store.ts', line: 2, col: 3, new_name: 'loadModel' },
    ]));
    writeFileSync(join(single, 'map.yaml'), mapYaml([{ file: 'src/store.ts', symbol: 'Store.getModel', new_name: 'loadModel' }]));
    expect(refactor(merged, 'rename-map', 'map.yaml')).toEqual(refactor(single, 'rename-map', 'map.yaml'));
  });

  it('refuses one symbol with two different changes', () => {
    const root = withMap({ 'src/store.ts': STORE }, [
      { file: 'src/store.ts', symbol: 'Store.getModel', new_name: 'a' },
      { file: 'src/store.ts', line: 2, col: 3, new_name: 'b' },
    ]);
    const result = refactor(root, 'rename-map', 'map.yaml');
    expect(result).toEqual({ code: 2, out: '', err: `${message('refactor.map-duplicate', { map: 'map.yaml', first: 1, second: 2 })}\n` });
  });

  it('refuses two entries rewriting one site differently', () => {
    const base = `export class Base {
  save(): void {}
}

export class Sub extends Base {
  override save(): void {}
}

export function run(b: Base): void {
  b.save();
}
`;
    const root = withMap({ 'src/base.ts': base }, [
      { file: 'src/base.ts', symbol: 'Base.save', new_name: 'store' },
      { file: 'src/base.ts', symbol: 'Sub.save', new_name: 'keep' },
    ]);
    const before = files(root);
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
    const sites = [2, 6, 10].map((line) => message('refactor.map-conflict', { path: 'src/base.ts', line, first: 1, second: 2 }));
    expect(result).toEqual({ code: 1, out: '', err: sites.map((site) => `${site}\n`).join('') });
    expect(files(root)).toEqual(before);
  });

  it('refuses a swap inside one scope with the name-conflict finding', () => {
    const f = 'export function f(x: number, y: number): number {\n  return x - y;\n}\n';
    const root = withMap({ 'src/f.ts': f }, [
      { file: 'src/f.ts', symbol: 'f(x)', new_name: 'y' },
      { file: 'src/f.ts', symbol: 'f(y)', new_name: 'x' },
    ]);
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
    const conflicts = ['x', 'y'].map((name) => message('refactor.name-conflict', { name, path: 'src/f.ts', line: 1 }));
    expect(result).toEqual({ code: 1, out: '', err: conflicts.map((conflict) => `${conflict}\n`).join('') });
    expect(read(root, 'src/f.ts')).toBe(f);
  });

  it.each([
    ['parameters', 'export function f(x: number, y: number): number {\n  return x - y;\n}\n', 'f(x)', 'f(y)'],
    ['module names', 'export const a = 1;\nexport const b = 2;\n', 'a', 'b'],
  ])('refuses two entries converging on one name (%s)', (_kind, f, first, second) => {
    const root = withMap({ 'src/f.ts': f }, [
      { file: 'src/f.ts', symbol: first, new_name: 'z' },
      { file: 'src/f.ts', symbol: second, new_name: 'z' },
    ]);
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
    expect(result).toEqual({ code: 1, out: '', err: `${message('refactor.name-conflict', { name: 'z', path: 'src/f.ts', line: 1 })}\n` });
    expect(read(root, 'src/f.ts')).toBe(f);
  });

  it.each([
    ['a static and an instance member', 'export class C {\n  static a = 1;\n  b = 2;\n}\n', 'C.a', 'C.b'],
    ['locals of two blocks', 'export function f(): number {\n  {\n    let a = 1;\n    a += 1;\n  }\n  {\n    let b = 2;\n    b += 1;\n  }\n  return 0;\n}\n', 'f.<locals>.a', 'f.<locals>.b'],
    ['destructured locals of two blocks', 'export function f(o: { p: number }): number {\n  {\n    let { p: a } = o;\n    a += 1;\n  }\n  {\n    let { p: b } = o;\n    b += 1;\n  }\n  return 0;\n}\n', 'f.<locals>.a', 'f.<locals>.b'],
    ['type aliases of two blocks', 'export function f(): number {\n  {\n    type a = number;\n    const u: a = 1;\n    void u;\n  }\n  {\n    type b = number;\n    const v: b = 2;\n    void v;\n  }\n  return 0;\n}\n', 'f.<locals>.a', 'f.<locals>.b'],
  ])('lets two entries take one name in different binding scopes (%s)', (_kind, f, first, second) => {
    const root = withMap({ 'src/f.ts': f }, [
      { file: 'src/f.ts', symbol: first, new_name: 'x' },
      { file: 'src/f.ts', symbol: second, new_name: 'x' },
    ]);
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/f.ts')).toBe(f.replace(/\b[ab]\b/gu, 'x'));
  });

  it('renames in a file with a byte-order mark, keeping the mark', () => {
    const root = tsProject({ 'src/a.ts': '\uFEFFexport const a = 1;\nexport const b = a + 1;\n' });
    const result = refactor(root, '--apply', 'rename', '--file', 'src/a.ts', '--symbol', 'a', '--new-name', 'c');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/a.ts')).toBe('\uFEFFexport const c = 1;\nexport const b = c + 1;\n');
  });

  it('rewrites a mention in a prose file with a byte-order mark at the mention', () => {
    const root = tsProject({ 'src/a.ts': 'export class Api {\n  old(): number {\n    return 1;\n  }\n}\n', 'README.md': '\uFEFFCall `Api.old` first.\n' });
    const result = refactor(root, '--apply', 'rename', '--file', 'src/a.ts', '--symbol', 'Api.old', '--new-name', 'modern', '--docs');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'README.md')).toBe('\uFEFFCall `Api.modern` first.\n');
  });

  it('refuses a parameter property and a field converging on one name', () => {
    const f = 'export class C {\n  b = 2;\n\n  constructor(public a: number) {}\n}\n';
    const root = withMap({ 'src/f.ts': f }, [
      { file: 'src/f.ts', symbol: 'C.a', new_name: 'x' },
      { file: 'src/f.ts', symbol: 'C.b', new_name: 'x' },
    ]);
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
    expect(result).toEqual({ code: 1, out: '', err: `${message('refactor.name-conflict', { name: 'x', path: 'src/f.ts', line: 4 })}\n` });
    expect(read(root, 'src/f.ts')).toBe(f);
  });

  it('lets the variables of two catch clauses take one name', () => {
    const f = 'export function f(): number {\n  try {\n    return 1;\n  } catch (one) {\n    void one;\n  }\n  try {\n    return 2;\n  } catch (two) {\n    void two;\n  }\n  return 0;\n}\n';
    const root = withMap({ 'src/f.ts': f }, [
      { file: 'src/f.ts', line: 4, col: 12, new_name: 'err' },
      { file: 'src/f.ts', line: 9, col: 12, new_name: 'err' },
    ]);
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/f.ts')).toBe(f.replace(/\b(one|two)\b/gu, 'err'));
  });

  it('refuses a map of two languages', () => {
    const root = withMap({ 'src/store.ts': STORE, 'pkg/a.py': 'def f() -> None:\n    pass\n' }, [
      { file: 'src/store.ts', symbol: 'Store.getModel', new_name: 'loadModel' },
      { file: 'pkg/a.py', symbol: 'f', new_name: 'g' },
    ]);
    const result = refactor(root, 'rename-map', 'map.yaml');
    const expected = message('refactor.map-mixed-languages', { map: 'map.yaml', languages: 'python, typescript' });
    expect(result).toEqual({ code: 2, out: '', err: `${expected}\n` });
  });

  it('refuses an invalid entry, naming it', () => {
    const root = tsProject({
      'src/store.ts': STORE,
      'map.yaml': '- file: src/store.ts\n  symbol: Store.getModel\n  new_name: loadModel\n- file: src/store.ts\n  symbol: Store.getModelSync\n  new_name: loadModelSync\n  retarget: Store.getModel\n',
    });
    const result = refactor(root, 'rename-map', 'map.yaml');
    expect(result).toEqual({ code: 2, out: '', err: `${message('refactor.map-invalid', { map: 'map.yaml', index: 2 })}\n` });
  });

  it('reads the map from the working directory and its entry files from --project', () => {
    const root = tsProject({ 'proj/tsconfig.json': TSCONFIG, 'proj/src/store.ts': STORE, 'proj/src/use.ts': USE });
    mkdirSync(join(root, 'maps'));
    writeFileSync(join(root, 'maps', 'm.yaml'), mapYaml([{ file: 'src/store.ts', symbol: 'Store.getModel', new_name: 'loadModel' }]));
    expect(refactor(root, '--apply', '--project', 'proj', 'rename-map', 'maps/m.yaml').code).toBe(0);
    expect(read(root, 'proj/src/use.ts')).toContain("s.loadModel('a')");
  });

  it.each([false, true])('rename equals its one-entry map (apply %s)', (apply) => {
    const viaRename = tsProject({ 'src/store.ts': STORE, 'src/use.ts': USE });
    const viaMap = copyProject(viaRename);
    writeFileSync(join(viaMap, 'map.yaml'), mapYaml([{ file: 'src/store.ts', symbol: 'Store.getModel', new_name: 'loadModel' }]));
    const flag = apply ? ['--apply'] : [];
    const renamed = refactor(viaRename, ...flag, 'rename', '--file', 'src/store.ts', '--symbol', 'Store.getModel', '--new-name', 'loadModel');
    expect(renamed.code).toBe(0);
    expect(refactor(viaMap, ...flag, 'rename-map', 'map.yaml')).toEqual(renamed);
    expect(Object.entries(files(viaMap)).filter(([rel]) => rel !== 'map.yaml')).toEqual(Object.entries(files(viaRename)));
  });

  it('a line/col entry equals the same rename by path', () => {
    const root = tsProject({ 'src/store.ts': STORE, 'src/use.ts': USE });
    const [, line, , col] = lineCol(root, 'src/store.ts', 'getModelSync');
    writeFileSync(join(root, 'map.yaml'), mapYaml([{ file: 'src/store.ts', line: Number(line), col: Number(col), new_name: 'sync' }]));
    const copy = copyProject(root);
    expect(refactor(root, 'rename-map', 'map.yaml')).toEqual(
      refactor(copy, 'rename', '--file', 'src/store.ts', '--symbol', 'Store.getModelSync', '--new-name', 'sync'),
    );
  });
});

describe('an apply writes every file or none', () => {
  it.skipIf(process.getuid?.() === 0)('restores the files written before a failed write', () => {
    const root = withMap(
      {
        'src/a.ts': 'export function foo(): number {\n  return 1;\n}\n',
        'src/b.ts': "import { foo } from './a';\n\nexport const b = foo();\n",
        'src/z/c.ts': "import { foo } from '../a';\n\nexport const c = foo();\n",
      },
      [{ file: 'src/a.ts', symbol: 'foo', new_name: 'bar' }],
    );
    const before = files(root);
    chmodSync(join(root, 'src', 'z'), 0o555);
    try {
      const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
      expect(result.code).toBe(1);
      expect(result.err).toContain(`${message('refactor.write-failed', { path: 'src/z/c.ts' })}\n`);
      expect(result.out).not.toContain(message('refactor.applied', { count: 3 }).trim());
    } finally {
      chmodSync(join(root, 'src', 'z'), 0o755);
    }
    expect(files(root)).toEqual(before);
  });
});

describe('rename-map module entries', () => {
  const unsupported = (index: number): string => message('refactor.map-module-unsupported', { map: 'map.yaml', index });

  it('refuses every module entry in index order before any phase line, writing nothing', () => {
    const root = withMap({ 'src/a.ts': 'export const x = 1;\n', 'src/c.ts': 'export const y = 2;\n' }, [
      { module: 'src/a.ts', new_name: 'b' },
      { module: 'src/c.ts', new_name: 'd' },
    ]);
    const before = files(root);
    expect(refactorRaw(root, '--apply', 'rename-map', 'map.yaml')).toEqual({ code: 2, out: '', err: `${unsupported(1)}\n${unsupported(2)}\n` });
    expect(files(root)).toEqual(before);
  });

  it('refuses only the module entries of a map that also renames symbols', () => {
    const root = withMap({ 'src/store.ts': STORE, 'src/use.ts': USE }, [
      { file: 'src/store.ts', symbol: 'Store.getModel', new_name: 'loadModel' },
      { module: 'src/use.ts', new_name: 'usage' },
    ]);
    const before = files(root);
    expect(refactorRaw(root, '--apply', 'rename-map', 'map.yaml')).toEqual({ code: 2, out: '', err: `${unsupported(2)}\n` });
    expect(files(root)).toEqual(before);
  });
});
