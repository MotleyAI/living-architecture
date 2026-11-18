// `--docs-pick PATH:LINE[=ENTRY]`: the listed mentions of a line are rewritten; a pick that cannot apply refuses.
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { files, mapYaml, read, refactor, tsProject } from './refactor-project.js';
import type { Run } from './cli-run.js';

const A = 'src/a.ts';
const TABLES = [
  '// Every table lists its `columns`.',
  '',
  '/** A table and its `columns`. */',
  'export class Table {',
  '  columns: string[] = [];',
  '}',
  '',
  '/** A result and its `columns`. */',
  'export class Result {',
  '  columns: string[] = [];',
  '}',
  '',
  '// Both keep their `columns` in order.',
  '',
].join('\n');
const TABLE_ENTRIES = [
  { file: A, symbol: 'Table.columns', new_name: 'fields' },
  { file: A, symbol: 'Result.columns', new_name: 'resultColumns' },
];
const XY = "export class A {\n  x = 0;\n}\n\nexport class B {\n  y = '';\n}\n\n// x and y move together; x first\n// x before y\n";
const XY_ENTRIES = [
  { file: 'src/m.ts', symbol: 'A.x', new_name: 'p' },
  { file: 'src/m.ts', symbol: 'B.y', new_name: 'q' },
];
const DS = 'export interface Ds {\n  columns: string[];\n}\n';
const BODY = "export const BODY = '{\"name\": \"orders\", \"columns\": [\"id\"]}';\n";
const API_MD = '# API\n\nSend columns, then read columns back.\nOld clients send columns too.\n';

const leftover = (path: string, line: number, where: string, old = 'columns'): string => message('refactor.leftover', { path, line, where, old });
const unmatched = (site: string): string => `${message('refactor.pick-unmatched', { site })}\n`;
const ambiguous = (site: string): string => `${message('refactor.pick-ambiguous', { site, first: 1, second: 2, old: 'columns' })}\n`;
const picks = (...sites: string[]): string[] => sites.flatMap((site) => ['--docs-pick', site]);

interface Picked {
  root: string;
  before: Record<string, string>;
  result: Run;
}

function mapped(project: Record<string, string>, entries: Record<string, string>[], ...flags: string[]): Picked {
  const root = tsProject({ ...project, 'map.yaml': mapYaml(entries) });
  const before = files(root);
  return { root, before, result: refactor(root, '--apply', 'rename-map', 'map.yaml', ...flags) };
}

const tables = (...flags: string[]): Picked => mapped({ [A]: TABLES }, TABLE_ENTRIES, ...flags);

function renameDs(project: Record<string, string>, ...flags: string[]): Picked {
  const root = tsProject({ 'src/ds.ts': DS, ...project });
  const before = files(root);
  return { root, before, result: refactor(root, '--apply', 'rename', '--file', 'src/ds.ts', '--symbol', 'Ds.columns', '--new-name', 'fields', ...flags) };
}

describe('--docs-pick', () => {
  it('a pick with an entry resolves a mention two entries reach', () => {
    const { root, result } = tables('--docs', ...picks(`${A}:1=1`));
    expect([result.code, result.err]).toEqual([0, `${leftover(A, 13, 'comment')}\n`]);
    expect(read(root, A).split('\n')[0]).toBe('// Every table lists its `fields`.');
  });

  it('the second entry can be picked', () => {
    const { root, result } = tables('--docs', ...picks(`${A}:13=2`));
    expect(result.code).toBe(0);
    expect(read(root, A).split('\n')[12]).toBe('// Both keep their `resultColumns` in order.');
  });

  it.each([['src/body.ts:1'], ['src/body.ts:1=1']])('a bare word in a string is picked in a single rename: %s', (site) => {
    const { root, result } = renameDs({ 'src/body.ts': BODY }, '--docs', ...picks(site));
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/body.ts')).toBe(BODY.replace('columns', 'fields'));
  });

  it('a prose line is picked with every mention on it', () => {
    const { root, result } = renameDs({ 'docs/api.md': API_MD }, '--docs', ...picks('docs/api.md:3'));
    expect([result.code, result.err]).toEqual([0, `${leftover('docs/api.md', 4, 'prose')}\n`]);
    expect(read(root, 'docs/api.md')).toBe(API_MD.replace('Send columns, then read columns', 'Send fields, then read fields'));
  });

  it('a pick without an entry rewrites each old name to its own new name', () => {
    const { root, result } = mapped({ 'src/m.ts': XY }, XY_ENTRIES, '--docs', ...picks('src/m.ts:9'));
    expect(result.code).toBe(0);
    expect(read(root, 'src/m.ts').split('\n').slice(8, 10)).toEqual(['// p and q move together; p first', '// x before y']);
    expect(result.err).toBe(`${leftover('src/m.ts', 10, 'comment', 'x')}\n${leftover('src/m.ts', 10, 'comment', 'y')}\n`);
  });

  it('a pick with an entry leaves the other old name listed', () => {
    const { root, result } = mapped({ 'src/m.ts': XY }, XY_ENTRIES, '--docs', ...picks('src/m.ts:9', 'src/m.ts:10=1'));
    expect([result.code, result.err]).toEqual([0, `${leftover('src/m.ts', 10, 'comment', 'y')}\n`]);
    expect(read(root, 'src/m.ts').split('\n')[9]).toBe('// p before y');
  });

  it('a kept line wins over its pick', () => {
    const { root, result } = tables('--docs', ...picks(`${A}:1=1`), '--keep', `${A}:1`);
    expect([result.code, result.err]).toEqual([0, `${leftover(A, 13, 'comment')}\n`]);
    expect(read(root, A).split('\n')[0]).toBe('// Every table lists its `columns`.');
  });

  it('two picks choosing one entry agree', () => {
    const { root, result } = tables('--docs', ...picks(`${A}:1=1`, `${A}:1=1`));
    expect(result.code).toBe(0);
    expect(read(root, A).split('\n')[0]).toBe('// Every table lists its `fields`.');
  });
});

describe('--docs-pick refusals', () => {
  it('a pick without --docs is refused in checks', () => {
    const { root, before, result } = tables(...picks(`${A}:1=1`));
    expect(result).toEqual({ code: 2, out: '', err: `${message('refactor.pick-needs-docs')}\n` });
    expect(files(root)).toEqual(before);
  });

  it.each([['src/gone.ts:1'], [`${A}:99`], [`${A}:99=1`]])('a pick naming no file or line is refused: %s', (site) => {
    const { root, before, result } = tables('--docs', ...picks(site));
    expect(result).toEqual({ code: 2, out: '', err: `${message('refactor.site-missing', { option: '--docs-pick', site })}\n` });
    expect(files(root)).toEqual(before);
  });

  it.each([
    ['no mention', `${A}:2`],
    ['a mention its class already rewrote', `${A}:3`],
    ['a code edit', `${A}:5`],
    ['an entry past the map', `${A}:1=3`],
    ['entry zero', `${A}:1=0`],
  ])('a pick matching no listed mention is refused: %s', (_name, site) => {
    const { root, before, result } = tables('--docs', ...picks(site));
    expect(result).toEqual({ code: 2, out: '', err: unmatched(site) });
    expect(files(root)).toEqual(before);
  });

  it('a pick for an entry whose old name the line lacks is refused', () => {
    const { root, before, result } = mapped({ 'src/m.ts': `${XY}// only x here\n` }, XY_ENTRIES, '--docs', ...picks('src/m.ts:11=2'));
    expect([result.code, result.err]).toEqual([2, unmatched('src/m.ts:11=2')]);
    expect(files(root)).toEqual(before);
  });

  it('a pick without an entry where two entries differ is refused', () => {
    const { root, before, result } = tables('--docs', ...picks(`${A}:1`));
    expect(result).toEqual({ code: 2, out: '', err: ambiguous(`${A}:1`) });
    expect(files(root)).toEqual(before);
  });

  it('two picks choosing different entries refuse naming the later', () => {
    const { root, before, result } = tables('--docs', ...picks(`${A}:1=1`, `${A}:1=2`));
    expect([result.code, result.err]).toEqual([2, ambiguous(`${A}:1=2`)]);
    expect(files(root)).toEqual(before);
  });

  it('every refused pick is reported in pick order', () => {
    const { result } = tables('--docs', ...picks(`${A}:13`, `${A}:2`, `${A}:1=1`, `${A}:1=2`));
    expect([result.code, result.err]).toEqual([2, ambiguous(`${A}:13`) + unmatched(`${A}:2`) + ambiguous(`${A}:1=2`)]);
  });

  it('a compound declaration line is not picked', () => {
    const root = tsProject({ 'src/model.ts': 'export class Model {}\n', 'src/names.ts': 'export class ModelMeasures {}\n' });
    const result = refactor(root, '--apply', 'rename', '--file', 'src/model.ts', '--symbol', 'Model', '--new-name', 'Dataset', '--docs', ...picks('src/names.ts:1'));
    expect([result.code, result.err]).toEqual([2, unmatched('src/names.ts:1')]);
    expect(read(root, 'src/model.ts')).toBe('export class Model {}\n');
  });
});
