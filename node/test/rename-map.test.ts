// dr-refactor rename-map: many renames as one dry-run and one all-or-nothing apply, through the TypeScript twin.
import { chmodSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { message, schema, validate } from '../src/contract/index.js';
import { TSCONFIG, copyProject, expectedOut, files, lineCol, mapYaml, read, refactor, renameHeader, tsProject } from './refactor-project.js';

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
    expect(lines[2]).toMatch(/^2 untyped receiver\(s\) of /);
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
    expect(result.code).toBe(1);
    expect(result.out).toBe('');
    expect(sites).toContain(result.err.trimEnd());
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
    expect(result.code).toBe(1);
    expect(conflicts).toContain(result.err.trimEnd());
    expect(read(root, 'src/f.ts')).toBe(f);
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
