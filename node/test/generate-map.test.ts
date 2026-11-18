// dr-refactor generate-map: candidates, carve-outs, entries, locals and the map it prints, through the TypeScript twin.
import { parse } from 'yaml';
import { describe, expect, it, vi } from 'vitest';
import { message, schema, validate } from '../src/contract/index.js';
import { Workspace } from '../src/refactor/workspace.js';
import { files, read, refactor, refactorRaw, tsProject } from './refactor-project.js';

const MODEL = 'words:\n- {from: model, to: dataset}\n';
const COLUMNS = 'words:\n- {from: columns, to: fields}\n';
const ANNOTATED = `${COLUMNS}carve_outs:\n- {words: [columns], annotated: [IntrospectedColumn]}\n`;

function generate(project: Record<string, string>, table: string, ...flags: string[]): ReturnType<typeof refactorRaw> {
  return refactorRaw(tsProject({ ...project, 'words.yaml': table }), ...flags, 'generate-map', 'words.yaml');
}

const entry = (file: string, symbol: string, newName: string): string => `- {file: ${file}, symbol: ${symbol}, new_name: ${newName}}\n`;
const carved = (path: string, line: number, name: string, word: string, matcher: string): string => `${message('refactor.carved', { path, line, name, word, matcher })}\n`;

const parameter = (annotation: string): string => `export const columnsTotal = 0;

export function f(columns${annotation}): void {
  console.log(columns);
}
`;

describe('an annotated carve-out', () => {
  it.each<[string, boolean]>([
    [': IntrospectedColumn[]', true],
    [': Array<IntrospectedColumn>', true],
    [': IntrospectedColumn | null', true],
    [': schema.IntrospectedColumn', true],
    [': Record<string, IntrospectedColumn[]>', true],
    [': string[]', false],
    ['', false],
    [': IntrospectedColumns[]', false],
    [': introspectedcolumn[]', false],
    [': unknown = IntrospectedColumn', false],
  ])('matches identifier tokens of the written annotation %j: %s', (annotation, matched) => {
    const total = entry('src/c.ts', 'columnsTotal', 'fieldsTotal');
    const expected = matched
      ? { code: 0, out: total, err: carved('src/c.ts', 3, 'columns', 'columns', 'annotated IntrospectedColumn') }
      : { code: 0, out: total + entry('src/c.ts', 'f(columns)', 'fields'), err: '' };
    expect(generate({ 'src/c.ts': parameter(annotation) }, ANNOTATED)).toEqual(expected);
  });

  it('matches variables, fields, interface members and locals, but no function by its return type', () => {
    const kinds = `export const columns: IntrospectedColumn[] = [];

export class Ds {
  columns: IntrospectedColumn[] = [];
}

export interface Shape {
  allColumns: IntrospectedColumn[];
}

export function f(): void {
  const columns: IntrospectedColumn[] = [];
  console.log(columns);
}

export function getColumns(): IntrospectedColumn[] {
  return [];
}
`;
    const lines: [number, string][] = [[1, 'columns'], [4, 'columns'], [8, 'allColumns'], [12, 'columns']];
    const listed = lines.map(([line, name]) => carved('src/c.ts', line, name, 'columns', 'annotated IntrospectedColumn')).join('');
    expect(generate({ 'src/c.ts': kinds }, ANNOTATED)).toEqual({ code: 0, out: entry('src/c.ts', 'getColumns', 'getFields'), err: listed });
  });

  it('is listed with the first matching carve-out in table order', () => {
    const table = `${COLUMNS}carve_outs:\n- {words: [columns], paths: ['src/*.ts']}\n- {words: [columns], annotated: [IntrospectedColumn]}\n`;
    const project = { 'src/c.ts': parameter(': IntrospectedColumn[]'), 'src/deep/t.ts': 'export const columns = 1;\n' };
    const listed = carved('src/c.ts', 1, 'columnsTotal', 'columns', 'paths src/*.ts') + carved('src/c.ts', 3, 'columns', 'columns', 'paths src/*.ts');
    expect(generate(project, table)).toEqual({ code: 0, out: entry('src/deep/t.ts', 'columns', 'fields'), err: listed });
  });
});

const CANDIDATES = `export interface ModelShape {
  modelName: string;
}

export type ModelKind = 'fast' | 'slow';

export enum ModelColor {
  RedModel = 'red',
}

export class ModelStore {
  modelCount = 0;

  getModel(modelName: string): string {
    return modelName;
  }
}

export const loadModel = (model: string): string => {
  const innerModel = model;
  return innerModel;
};
`;
const CANDIDATE_ENTRIES = [
  ['ModelShape', 'DatasetShape'],
  ['ModelShape.modelName', 'datasetName'],
  ['ModelKind', 'DatasetKind'],
  ['ModelColor', 'DatasetColor'],
  ['ModelColor.RedModel', 'RedDataset'],
  ['ModelStore', 'DatasetStore'],
  ['ModelStore.modelCount', 'datasetCount'],
  ['ModelStore.getModel', 'getDataset'],
  ['ModelStore.getModel(modelName)', 'datasetName'],
  ['loadModel', 'loadDataset'],
  ['loadModel(model)', 'dataset'],
  ['loadModel.<locals>.innerModel', 'innerDataset'],
]
  .map(([symbol, next]) => entry('src/a.ts', symbol!, next!))
  .join('');

const LOCALS = `export function f(name: string): string {
  const model = name.toUpperCase();
  return model;
}

export const g = (name: string): string => {
  const model = name.toLowerCase();
  return model;
};

export function h(name: string, model: string): string {
  const models = name + model;
  return models;
}
`;
const THREE = `${LOCALS}
export const k = function (name: string): string {
  const model = name.trim();
  return model;
};
`;

describe('generate-map candidates', () => {
  it('are written by path in source order', () => {
    expect(generate({ 'src/a.ts': CANDIDATES }, MODEL)).toEqual({ code: 0, out: CANDIDATE_ENTRIES, err: '' });
  });

  it('are one per symbol, at its first declaration (merged interfaces, overloads)', () => {
    const source = `export interface Model {
  a: number;
}

export interface Model {
  b: number;
}

export function loadModel(a: string): string;
export function loadModel(a: number): number;
export function loadModel(a: string | number): string | number {
  return a;
}
`;
    expect(generate({ 'src/a.ts': source }, MODEL)).toEqual({ code: 0, out: entry('src/a.ts', 'Model', 'Dataset') + entry('src/a.ts', 'loadModel', 'loadDataset'), err: '' });
  });

  it('are written by line and column when their path names more than one symbol', () => {
    const source = 'export function build(): void {\n  {\n    const model = 1;\n    console.log(model);\n  }\n  {\n    const model = 2;\n    console.log(model);\n  }\n}\n';
    const expected = '- {file: src/a.ts, line: 3, col: 11, new_name: dataset}\n- {file: src/a.ts, line: 7, col: 11, new_name: dataset}\n';
    expect(generate({ 'src/a.ts': source }, MODEL)).toEqual({ code: 0, out: expected, err: '' });
  });

  it('are found without a language service', () => {
    const started = (): never => {
      throw new Error('a language service was started');
    };
    const spies = [vi.spyOn(Workspace.prototype, 'service').mockImplementation(started), vi.spyOn(Workspace.prototype, 'servicesOf').mockImplementation(started)];
    try {
      expect(generate({ 'src/a.ts': 'export const model = 1;\n' }, MODEL)).toEqual({ code: 0, out: entry('src/a.ts', 'model', 'dataset'), err: '' });
    } finally {
      for (const spy of spies) spy.mockRestore();
    }
  });

  it('skip declaration files and installed dependencies', () => {
    const project = { 'src/a.ts': 'export const model = 1;\n', 'src/api.d.ts': 'export declare const model: number;\n', 'node_modules/dep/model.ts': 'export const model = 1;\n' };
    expect(generate(project, MODEL)).toEqual({ code: 0, out: entry('src/a.ts', 'model', 'dataset'), err: '' });
  });

  it('list each source file whose name holds a word, before the listings of its declarations', () => {
    const table = `${MODEL}carve_outs:\n- {words: [model], annotated: [Kept]}\n`;
    const project = { 'src/model.ts': 'export const model: Kept = 1;\nexport const modelCount = 2;\n', 'src/modelStore.tsx': 'export const x = 1;\n' };
    const listed = `${message('refactor.not-generated-module', { path: 'src/model.ts', word: 'model' })}\n${carved('src/model.ts', 1, 'model', 'model', 'annotated Kept')}${message('refactor.not-generated-module', { path: 'src/modelStore.tsx', word: 'model' })}\n`;
    expect(generate(project, table)).toEqual({ code: 0, out: entry('src/model.ts', 'modelCount', 'datasetCount'), err: listed });
  });
});

describe('generate-map locals', () => {
  it('of one name in a file are one wildcard entry; a parameter is its own entry', () => {
    const expected = entry('src/l.ts', "'*.<locals>.model'", 'dataset') + entry('src/l.ts', 'h(model)', 'dataset');
    expect(generate({ 'src/l.ts': LOCALS }, MODEL)).toEqual({ code: 0, out: expected, err: '' });
  });

  it('are each written alone when an entry locates one of them', () => {
    const table = `${MODEL}entries:\n- {file: src/l.ts, symbol: g.<locals>.model, new_name: population}\n`;
    const expected =
      entry('src/l.ts', 'g.<locals>.model', 'population') +
      entry('src/l.ts', 'f.<locals>.model', 'dataset') +
      entry('src/l.ts', 'h(model)', 'dataset') +
      entry('src/l.ts', 'k.<locals>.model', 'dataset');
    expect(generate({ 'src/l.ts': THREE }, table)).toEqual({ code: 0, out: expected, err: '' });
  });

  it('of two files are never one entry', () => {
    const one = "export function f(): string {\n  const model = 'x';\n  return model;\n}\n";
    const expected = entry('src/a.ts', 'f.<locals>.model', 'dataset') + entry('src/b.ts', 'f.<locals>.model', 'dataset');
    expect(generate({ 'src/a.ts': one, 'src/b.ts': one }, MODEL)).toEqual({ code: 0, out: expected, err: '' });
  });
});

const KIND = `export type Kind = 'fast' | 'slow';
export const LIMIT = 3;

export function load(): number {
  return 1;
}

export function save(): number {
  return 2;
}

export const alias = load;
`;
const ODD_ENTRIES = `entries:
- {new_name: 'yes', symbol: load, file: src/a.ts}
- {file: src/a.ts, symbol: "Kind['fast']", new_name: '123'}
- {col: 17, line: 8, file: src/a.ts, new_name: store}
- {file: src/a.ts, offset: 49, new_name: CAP}
- {retarget: load, symbol: alias, file: src/a.ts}
`;
// A value is written plain unless YAML would read it as something else or it holds a character outside
// `A-Za-z0-9_$./<>()-`; then it is single-quoted, a quote doubled.
const ODD_OUTPUT = `- {file: src/a.ts, symbol: load, new_name: 'yes'}
- {file: src/a.ts, symbol: 'Kind[''fast'']', new_name: '123'}
- {file: src/a.ts, line: 8, col: 17, new_name: store}
- {file: src/a.ts, offset: 49, new_name: CAP}
- {file: src/a.ts, symbol: alias, retarget: load}
`;

describe("generate-map and the table's entries", () => {
  it('writes them first, in table order, with keys in schema order', () => {
    const project = { 'src/a.ts': KIND, 'src/b.ts': 'export const model = 1;\n' };
    expect(generate(project, MODEL + ODD_ENTRIES)).toEqual({ code: 0, out: ODD_OUTPUT + entry('src/b.ts', 'model', 'dataset'), err: '' });
  });

  it("refuses one that does not resolve with its locator's finding", () => {
    const table = `${MODEL}entries:\n- {file: src/a.ts, symbol: laod, new_name: read}\n`;
    const expected = `${message('refactor.symbol-unresolved', { path: 'src/a.ts', symbol: 'laod', candidates: 'Kind, LIMIT, alias, load, save' })}\n`;
    expect(generate({ 'src/a.ts': KIND, 'src/b.ts': 'export const model = 1;\n' }, table)).toEqual({ code: 2, out: '', err: expected });
  });
});

const V = `export class Query {
  measures: string[] = [];
}

export function addMeasures(q: Query, measures: string[]): void {
  q.measures.push(...measures);
}
`;
const H = `export class Base {
  measures(): number {
    return 1;
  }
}

export class Sub extends Base {
  override measures(): number {
    return 2;
  }
}

export function total(b: Base): number {
  return b.measures();
}
`;
const MEASURES = 'words:\n- {from: measures, to: metrics}\n';

describe('the generated map', () => {
  it('is a valid rename map, one flow mapping per line', () => {
    const { out } = generate({ 'src/a.ts': CANDIDATES, 'src/l.ts': LOCALS }, MODEL);
    const lines = out.split('\n').slice(0, -1);
    expect([lines.length, lines.filter((line) => !/^- \{.+\}$/.test(line)), validate(schema('rename-map'), parse(out))]).toEqual([14, [], []]);
  });

  it('is the same on every run, and nothing is written, with or without --apply', () => {
    const root = tsProject({ 'src/a.ts': CANDIDATES, 'src/l.ts': LOCALS, 'words.yaml': MODEL });
    const before = files(root);
    const first = refactorRaw(root, '--apply', 'generate-map', 'words.yaml');
    const second = refactorRaw(root, 'generate-map', 'words.yaml');
    expect([first, first.code, files(root)]).toEqual([second, 0, before]);
  });

  it.each<[string, string, string[]]>([
    ['a field, a function and its parameter', V, ['metrics: string[] = [];', 'export function addMetrics(q: Query, metrics: string[]): void {\n  q.metrics.push(...metrics);']],
    ['a member and its override', H, ['export class Base {\n  metrics()', 'override metrics()', 'return b.metrics();']],
  ])('is applied by rename-map: %s', (_name, source, renamed) => {
    const root = tsProject({ 'src/v.ts': source, 'words.yaml': MEASURES });
    const { out } = refactorRaw(root, 'generate-map', 'words.yaml');
    const mapped = tsProject({ 'src/v.ts': source, 'map.yaml': out });
    const result = refactor(mapped, '--apply', 'rename-map', 'map.yaml');
    const text = read(mapped, 'src/v.ts');
    expect([result.code, result.err, renamed.filter((part) => !text.includes(part))]).toEqual([0, '', []]);
  });

  it('is empty with generate-empty when nothing holds a word and the table has no entries', () => {
    expect(generate({ 'src/a.ts': KIND }, MODEL)).toEqual({ code: 1, out: '', err: `${message('refactor.generate-empty', { table: 'words.yaml' })}\n` });
  });

  it('ends with generate-empty when carve-outs keep every candidate', () => {
    const table = `${MODEL}carve_outs:\n- {words: [model], paths: ['src/**']}\n`;
    const expected = `${carved('src/b.ts', 1, 'model', 'model', 'paths src/**')}${message('refactor.generate-empty', { table: 'words.yaml' })}\n`;
    expect(generate({ 'src/b.ts': 'export const model = 1;\n' }, table)).toEqual({ code: 1, out: '', err: expected });
  });

  it('needs --language when the project also holds Python sources', () => {
    const project = { 'src/b.ts': 'export const model = 1;\n', 'pkg/b.py': 'model = 1\n' };
    expect(generate(project, MODEL)).toEqual({ code: 2, out: '', err: `${message('refactor.generate-language', { languages: 'python, typescript' })}\n` });
  });

  it('is the TypeScript map of a mixed project with --language typescript', () => {
    const root = tsProject({ 'src/b.ts': 'export const model = 1;\n', 'pkg/b.py': 'model = 1\n', 'words.yaml': MODEL });
    expect(refactorRaw(root, 'generate-map', 'words.yaml', '--language', 'typescript')).toEqual({ code: 0, out: entry('src/b.ts', 'model', 'dataset'), err: '' });
  });
});
