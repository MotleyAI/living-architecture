// The map engine's rules over the whole symbol set and the one file universe: stand-ins another entry renames,
// computed names, and sources in an excluded directory or outside every program.
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { run } from './cli-run.js';
import { files, mapYaml, read, refactor, tsProject } from './refactor-project.js';

const COMPUTED = `const KEY = 'getModel';

export interface Store {
  getModel(name: string): number;
}

export class Keyed {
  [KEY](name: string): number {
    return name.length;
  }
}
`;

describe('computed names', () => {
  it('a member declared by a computed name is no path candidate', () => {
    const root = tsProject({ 'src/store.ts': COMPUTED });
    const result = refactor(root, 'rename', '--file', 'src/store.ts', '--symbol', 'Keyed.getModel', '--new-name', 'x');
    const expected = message('refactor.symbol-unresolved', { path: 'src/store.ts', symbol: 'Keyed.getModel', candidates: '' });
    expect(result).toEqual({ code: 2, out: '', err: `${expected}\n` });
  });

  it('a map --with on a computed-name stand-in exits 2, --without leaves it', () => {
    const entries = [{ file: 'src/store.ts', symbol: 'Store.getModel', new_name: 'getDataset' }];
    const root = tsProject({ 'src/store.ts': COMPUTED, 'map.yaml': mapYaml(entries) });
    const values = { path: 'src/store.ts', line: 8, cls: 'Keyed', attr: 'getModel' };
    const refused = refactor(root, 'rename-map', 'map.yaml', '--with', 'src/store.ts:8');
    expect(refused).toEqual({ code: 2, out: '', err: `${message('refactor.computed-stand-in', { site: 'src/store.ts:8', ...values })}\n` });
    const left = refactor(root, '--apply', 'rename-map', 'map.yaml', '--without', 'src/store.ts:8');
    expect(left.code).toBe(0);
    expect(read(root, 'src/store.ts')).toBe(COMPUTED.replace('getModel(name: string): number;', 'getDataset(name: string): number;'));
  });
});

describe('rules over the whole symbol set', () => {
  const TWO = `export class A {
  save(): number {
    return 1;
  }
}

export class B {
  save(): number {
    return 2;
  }
}
`;

  it('a declaration another entry renames is no stand-in', () => {
    const alone = tsProject({ 'src/two.ts': TWO });
    expect(refactor(alone, 'rename', '--file', 'src/two.ts', '--symbol', 'A.save', '--new-name', 'store')).toMatchObject({
      code: 1,
      err: `${message('refactor.stand-in', { path: 'src/two.ts', line: 8, cls: 'B', attr: 'save' })}\n`,
    });
    const both = tsProject({
      'src/two.ts': TWO,
      'map.yaml': mapYaml([
        { file: 'src/two.ts', symbol: 'A.save', new_name: 'store' },
        { file: 'src/two.ts', symbol: 'B.save', new_name: 'keep' },
      ]),
    });
    expect(refactor(both, '--apply', 'rename-map', 'map.yaml')).toMatchObject({ code: 0, err: '' });
    expect(read(both, 'src/two.ts')).toBe(TWO.replace('save(): number {\n    return 1;', 'store(): number {\n    return 1;').replace('save(): number {\n    return 2;', 'keep(): number {\n    return 2;'));
  });
});

describe('one file universe', () => {
  const KINDS = "export type Kind = 'edit_model' | 'drop';\n";
  const LOOSE = "export const plain: string = 'edit_model';\nexport class ModelCache {}\n";
  const universe = { 'scripts/tool.ts': LOOSE, 'node_modules/dep/x.ts': LOOSE, 'src/node_modules/y.ts': LOOSE };

  it('a literal rename lists an equal string outside every program, none in an excluded directory', () => {
    const root = tsProject({ 'src/kinds.ts': KINDS, ...universe });
    const result = refactor(root, 'rename', '--file', 'src/kinds.ts', '--symbol', "Kind['edit_model']", '--new-name', 'edit_master');
    const leftover = message('refactor.leftover', { path: 'scripts/tool.ts', line: 1, where: 'string', old: 'edit_model' });
    expect(result).toMatchObject({ code: 0, err: `${leftover}\n` });
  });

  it('compound names are listed outside every program, none in an excluded directory', () => {
    const root = tsProject({ 'src/model.ts': 'export class Model {}\n', ...universe });
    const result = refactor(root, 'rename', '--file', 'src/model.ts', '--symbol', 'Model', '--new-name', 'Dataset', '--docs');
    const compound = message('refactor.compound', { path: 'scripts/tool.ts', line: 2, name: 'ModelCache', old: 'Model' });
    expect(result).toMatchObject({ code: 0, err: `${compound}\n` });
  });

  it('a retarget refuses on an any receiver outside every program, not on one in an excluded directory', () => {
    const engine = 'export class Engine {\n  saveModel(): void {}\n\n  /** @deprecated */\n  save(): void {\n    this.saveModel();\n  }\n}\n';
    const any = 'export function g(o: any): void {\n  o.save();\n}\n';
    const root = tsProject({ 'src/engine.ts': engine, 'scripts/tool.ts': any, 'node_modules/dep/x.ts': any });
    const before = files(root);
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/engine.ts', '--symbol', 'Engine.save', '--target', 'Engine.saveModel');
    expect(result.code).toBe(1);
    expect(result.err).toBe(
      [
        message('compliance.attr-blindspot', { path: 'scripts/tool.ts', line: 2, receiver: 'o', attr: 'save', type: 'any' }),
        message('refactor.blindspots', { count: 1, attr: 'save' }),
        '',
      ].join('\n'),
    );
    expect(files(root)).toEqual(before);
  });
});

describe('dr-compliance --attr over every access form', () => {
  it('reports an element access and a property access on any receivers, per name, in one scan', () => {
    const loose = "export function f(a: any, b: any): number {\n  return a['getModel']() + b.saveModel();\n}\n";
    const root = tsProject({ 'src/m.ts': loose });
    const result = run(root, 'dr-compliance', ['--select', 'attr-blindspot,string-blindspot', '--attr', 'saveModel', '--attr', 'getModel', 'src']);
    const named = message('compliance.string-blindspot', { path: 'src/m.ts', line: 2, site: "a['getModel']", receiver: 'a', attr: 'getModel', type: 'any' });
    const access = message('compliance.attr-blindspot', { path: 'src/m.ts', line: 2, receiver: 'b', attr: 'saveModel', type: 'any' });
    expect(result).toEqual({ code: 1, out: `${named}\n${access}\n`, err: '' });
  });
});
