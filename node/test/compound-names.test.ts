// With --docs, declarations whose name holds the old name as a word sequence are listed, never renamed.
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { mapYaml, read, refactor, tsProject } from './refactor-project.js';

const MODEL = `export class Model {}

export class ModelMeasures {}

export const SlayerModels = [new Model()];

export function TestModelMeasurePosition(): void {}

export const model_name = 'm';

export const Modelling = 2;
`;
const COLUMNS = `export function column(): number {
  return 1;
}

export function get_columns(): number[] {
  return [column()];
}

export class ColumnCycleError extends Error {}

export function box(): number {
  return 2;
}

export const all_boxes = [box()];
`;

const compound = (path: string, line: number, name: string, old: string): string => message('refactor.compound', { path, line, name, old });
const rename = (root: string, symbol: string, newName: string, ...flags: string[]) =>
  refactor(root, 'rename', '--file', 'src/model.ts', '--symbol', symbol, '--new-name', newName, ...flags);

describe('compound names', () => {
  it('lists CamelCase, plural and snake_case compounds, not a longer word', () => {
    const root = tsProject({ 'src/model.ts': MODEL });
    const result = rename(root, 'Model', 'Dataset', '--docs');
    expect(result.code).toBe(0);
    expect(result.err).toBe(
      [
        compound('src/model.ts', 3, 'ModelMeasures', 'Model'),
        compound('src/model.ts', 5, 'SlayerModels', 'Model'),
        compound('src/model.ts', 7, 'TestModelMeasurePosition', 'Model'),
        compound('src/model.ts', 9, 'model_name', 'Model'),
        '',
      ].join('\n'),
    );
  });

  it('matches a snake_case old name with an s or es suffix', () => {
    const root = tsProject({ 'src/model.ts': COLUMNS });
    expect(rename(root, 'column', 'field', '--docs').err).toBe(
      [compound('src/model.ts', 5, 'get_columns', 'column'), compound('src/model.ts', 9, 'ColumnCycleError', 'column'), ''].join('\n'),
    );
    expect(rename(root, 'box', 'crate', '--docs').err).toBe(`${compound('src/model.ts', 15, 'all_boxes', 'box')}\n`);
  });

  it('lists nothing without --docs', () => {
    const root = tsProject({ 'src/model.ts': MODEL });
    expect(rename(root, 'Model', 'Dataset')).toMatchObject({ code: 0, err: '' });
  });

  it('a map does not list a name it renames', () => {
    const root = tsProject({
      'src/model.ts': MODEL,
      'map.yaml': mapYaml([
        { file: 'src/model.ts', symbol: 'Model', new_name: 'Dataset' },
        { file: 'src/model.ts', symbol: 'ModelMeasures', new_name: 'DatasetMeasures' },
      ]),
    });
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml', '--docs');
    expect(result.code).toBe(0);
    expect(result.err.split('\n')).not.toContain(compound('src/model.ts', 3, 'ModelMeasures', 'Model'));
    expect(result.err.split('\n')).toContain(compound('src/model.ts', 5, 'SlayerModels', 'Model'));
    expect(read(root, 'src/model.ts')).toContain('export const SlayerModels = [new Dataset()];');
  });
});
