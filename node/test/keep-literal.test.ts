// `--keep-literal KEY`: an object literal holding the property is kept whole from every rewrite.
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { mapYaml, read, refactor, tsProject } from './refactor-project.js';
import type { Run } from './cli-run.js';

const DS = 'export interface Member {\n  version?: number;\n  type: string;\n}\n\nexport interface Ds {\n  version?: number;\n  columns: Member[];\n}\n';
const DS_AFTER = DS.replace('  columns:', '  fields:');
const HEAD = "import type { Ds } from './ds';\n\n";
const USE = 'src/use.ts';
const unneeded = (key: string): string => `${message('refactor.keep-literal-unneeded', { key })}\n`;

/** `Ds.columns -> fields --keep-literal version` over `use` at src/use.ts. */
function kept(use: string, ...flags: string[]): { root: string; result: Run } {
  const root = tsProject({ 'src/ds.ts': DS, [USE]: use });
  const argv = ['--apply', 'rename', '--file', 'src/ds.ts', '--symbol', 'Ds.columns', '--new-name', 'fields', '--keep-literal', 'version', ...flags];
  return { root, result: refactor(root, ...argv) };
}

const typed = (...literals: string[]): string => HEAD + literals.map((literal, i) => `export const d${i}: Ds = ${literal};\n`).join('');

describe('--keep-literal', () => {
  it.each([['{ version: 3, columns: [] }'], ["{ 'version': 3, columns: [] }"], ['{ "version": 3, columns: [] }'], ['{ version, columns: [] }']])(
    'keeps a literal naming the property: %s',
    (literal) => {
      const use = `const version = 3;\n${typed(literal, '{ columns: [] }')}`;
      const { root, result } = kept(use);
      expect([result.code, result.err]).toEqual([0, '']);
      expect(read(root, USE)).toBe(`const version = 3;\n${typed(literal, '{ fields: [] }')}`);
      expect(read(root, 'src/ds.ts')).toBe(DS_AFTER);
    },
  );

  it.each([
    ['a computed key', '{ [key]: 3, columns: [] }'],
    ['a spread', '{ ...{ version: 3 }, columns: [] }'],
    ['another property', '{ columns: [], ...versions }'],
    ['a value', "{ columns: [{ type: 'version' }] }"],
  ])('does not match %s', (_name, literal) => {
    const use = `const key = 'version';\nconst versions = {};\n${typed(literal, '{ version: 1, columns: [] }')}`;
    const { root, result } = kept(use);
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, USE)).toBe(`const key = 'version';\nconst versions = {};\n${typed(literal.replace('columns', 'fields'), '{ version: 1, columns: [] }')}`);
  });

  it('keeps nested literals with a kept literal; a nested match keeps only itself', () => {
    const use = typed("{ version: 2, columns: [{ type: 'INT' }] }", "{ columns: [{ version: 1, type: 'INT' }, { type: 'TEXT' }] }");
    const entries = [
      { file: 'src/ds.ts', symbol: 'Ds.columns', new_name: 'fields' },
      { file: 'src/ds.ts', symbol: 'Member.type', new_name: 'kind' },
    ];
    const root = tsProject({ 'src/ds.ts': DS, [USE]: use, 'map.yaml': mapYaml(entries) });
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml', '--keep-literal', 'version');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, USE)).toBe(typed("{ version: 2, columns: [{ type: 'INT' }] }", "{ fields: [{ version: 1, type: 'INT' }, { kind: 'TEXT' }] }"));
  });

  it('drops an edit overlapping a kept literal whatever made it', () => {
    const use = `${HEAD}export function dump(d: Ds): object {\n  return { version: 3, count: d.columns.length };\n}\n`;
    const { root, result } = kept(use);
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, USE)).toBe(use);
  });

  it('the key is repeatable', () => {
    const use = `${HEAD}export const a: Ds & { schema: number } = { schema: 1, columns: [] };\n${typed('{ version: 3, columns: [] }', '{ columns: [] }').slice(HEAD.length)}`;
    const { root, result } = kept(use, '--keep-literal', 'schema');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, USE)).toBe(use.replace('= { columns: [] }', '= { fields: [] }'));
  });

  it('a blind spot inside a kept literal does not block', () => {
    const use = `${typed('{ columns: [] }')}\nexport function dump(x: any): object {\n  return { version: 1, count: x.columns };\n}\n`;
    const { root, result } = kept(use);
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, USE)).toBe(use.replace('= { columns: [] }', '= { fields: [] }'));
  });

  it('a blind spot outside a kept literal still blocks', () => {
    const use = `${typed('{ version: 1, columns: [] }')}\nexport function dump(x: any): object {\n  return { count: x.columns };\n}\n`;
    const { root, result } = kept(use);
    expect(result.code).toBe(1);
    expect(result.err).toContain(`${USE}:6: attr-blindspot`);
    expect(read(root, 'src/ds.ts')).toBe(DS);
  });

  it('a listed mention inside a kept literal is not listed', () => {
    const notes = "export const NOTES = [{ version: 1, note: 'columns here' }, { note: 'columns there' }];\n";
    const root = tsProject({ 'src/ds.ts': DS, [USE]: typed('{ version: 1, columns: [] }'), 'src/notes.ts': notes });
    const argv = ['--apply', 'rename', '--file', 'src/ds.ts', '--symbol', 'Ds.columns', '--new-name', 'fields', '--docs', '--keep-literal', 'version'];
    const result = refactor(root, ...argv);
    const listed = message('refactor.leftover', { path: 'src/notes.ts', line: 1, where: 'string', old: 'columns' });
    expect([result.code, result.err]).toEqual([0, `${listed}\n`]);
    expect(read(root, 'src/notes.ts')).toBe(notes);
  });

  it('a key matching nothing touched warns and the rename is written', () => {
    const use = `${typed('{ columns: [] }')}export const META = { schema_version: 2 };\n`;
    const root = tsProject({ 'src/ds.ts': DS, [USE]: use });
    const result = refactor(root, '--apply', 'rename', '--file', 'src/ds.ts', '--symbol', 'Ds.columns', '--new-name', 'fields', '--keep-literal', 'schema_version');
    expect([result.code, result.err]).toEqual([0, unneeded('schema_version')]);
    expect(read(root, USE)).toBe(use.replace('= { columns: [] }', '= { fields: [] }'));
  });

  it('each unneeded key warns in command-line order', () => {
    const { result } = kept(typed('{ version: 3, columns: [] }'), '--keep-literal', 'b', '--keep-literal', 'a');
    expect([result.code, result.err]).toEqual([0, unneeded('b') + unneeded('a')]);
  });

  it('a kept literal wins over a pick on its line', () => {
    const notes = "export const NOTES = [{ version: 1, note: 'columns here' }];\n";
    const root = tsProject({ 'src/ds.ts': DS, [USE]: typed('{ version: 1, columns: [] }'), 'src/notes.ts': notes });
    const argv = ['--apply', 'rename', '--file', 'src/ds.ts', '--symbol', 'Ds.columns', '--new-name', 'fields', '--docs', '--keep-literal', 'version'];
    const result = refactor(root, ...argv, '--docs-pick', 'src/notes.ts:1');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/notes.ts')).toBe(notes);
  });
});
