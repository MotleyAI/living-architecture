// `rename --docs`: a code-marked bare mention is decided by its owning class, once over all entries.
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { lineCol, mapYaml, read, refactor, tsProject } from './refactor-project.js';
import type { Run } from './cli-run.js';

const A = 'src/a.ts';
const TABLE = '/** Lists its `columns`. */\nexport class Table {\n  columns: string[] = [];\n}\n';
const TABLE_AFTER = '/** Lists its `fields`. */\nexport class Table {\n  fields: string[] = [];\n}\n';
const RESULT = '\n/** Carries `columns`; another class. */\nexport class Result {\n  columns: string[] = [];\n}\n';

const leftover = (line: number, where: string, old = 'columns', path = A): string => message('refactor.leftover', { path, line, where, old });
const lines = (...items: string[]): string => items.map((item) => `${item}\n`).join('');

/** `Table.columns -> fields --docs` over `text` at src/a.ts. */
function renameTable(text: string, ...flags: string[]): { root: string; result: Run } {
  const root = tsProject({ [A]: text });
  return { root, result: refactor(root, '--apply', 'rename', '--file', A, '--symbol', 'Table.columns', '--new-name', 'fields', '--docs', ...flags) };
}

/** The declaration at the `nth` `columns` of `text` renamed to `fields` with `--docs`. */
function renameAt(text: string, nth: number, ...flags: string[]): { root: string; result: Run } {
  const root = tsProject({ [A]: text });
  return { root, result: refactor(root, '--apply', 'rename', '--file', A, ...lineCol(root, A, 'columns', nth), '--new-name', 'fields', '--docs', ...flags) };
}

describe('--docs owning class', () => {
  it('lists the JSDoc of another class declaring the member', () => {
    const { root, result } = renameTable(TABLE + RESULT, '--without', `${A}:8`);
    expect([result.code, result.err]).toEqual([0, lines(leftover(6, 'comment'))]);
    expect(read(root, A)).toBe(TABLE_AFTER + RESULT);
  });

  it('rewrites a JSDoc and a comment inside the class body', () => {
    const body = '\n  /** Counts the `columns`. */\n  size(): number {\n    // `columns` are counted\n    return this.columns.length;\n  }\n}\n';
    const { root, result } = renameTable(TABLE.replace(/\}\n$/u, body) + RESULT, '--without', `${A}:14`);
    expect([result.code, result.err]).toEqual([0, lines(leftover(12, 'comment'))]);
    expect(read(root, A)).toBe(TABLE_AFTER.replace(/\}\n$/u, body.replaceAll('columns', 'fields')) + RESULT);
  });

  it('a line comment before a class is not owned by it', () => {
    const text = `// \`columns\` of the table\n${TABLE}${RESULT}`;
    const { root, result } = renameTable(text, '--without', `${A}:9`);
    expect([result.code, result.err]).toEqual([0, lines(leftover(1, 'comment'), leftover(7, 'comment'))]);
    expect(read(root, A)).toBe(`// \`columns\` of the table\n${TABLE_AFTER}${RESULT}`);
  });

  it('an interface owns its JSDoc', () => {
    const row = '/** Has `columns`. */\nexport interface Row {\n  columns: string[];\n}\n';
    const other = '\n/** Has `columns` too. */\nexport interface Other {\n  columns: number;\n}\n';
    const { root, result } = renameAt(row + other, 1, '--without', `${A}:8`);
    expect([result.code, result.err]).toEqual([0, lines(leftover(6, 'comment'))]);
    expect(read(root, A)).toBe(row.replaceAll('columns', 'fields') + other);
  });

  it('a type literal owns the JSDoc of its declaration', () => {
    const shape = '/** Has `columns`. */\nexport type Shape = {\n  columns: string[];\n};\n';
    const other = '\n/** Has `columns` too. */\nexport type Other = {\n  columns: number;\n};\n';
    const { root, result } = renameAt(shape + other, 1, '--without', `${A}:8`);
    expect([result.code, result.err]).toEqual([0, lines(leftover(6, 'comment'))]);
    expect(read(root, A)).toBe(shape.replaceAll('columns', 'fields') + other);
  });

  it('every declaration of a merged interface owns its JSDoc', () => {
    const merged = 'export interface Row {\n  columns: string[];\n}\n\n/** More beside `columns`. */\nexport interface Row {\n  size: number;\n}\n';
    const other = '\n/** Has `columns` too. */\nexport interface Other {\n  columns: number;\n}\n';
    const { root, result } = renameAt(merged + other, 0, '--without', `${A}:12`);
    expect([result.code, result.err]).toEqual([0, lines(leftover(10, 'comment'))]);
    expect(read(root, A)).toBe(merged.replaceAll('columns', 'fields') + other);
  });

  it('a subclass inheriting the member owns its mention', () => {
    const sub = '\n/** Reads `columns`. */\nexport class Sub extends Table {}\n';
    const { root, result } = renameTable(TABLE + sub + RESULT, '--without', `${A}:11`);
    expect([result.code, result.err]).toEqual([0, lines(leftover(9, 'comment'))]);
    expect(read(root, A)).toBe(TABLE_AFTER + sub.replace('columns', 'fields') + RESULT);
  });

  it('lists a mention whose lookup lands on an unchanged declaration', () => {
    const wrapper = '\n/** Reads `columns`. */\nexport class Wrapper extends Result {}\n';
    const { root, result } = renameTable(TABLE + RESULT + wrapper, '--without', `${A}:8`);
    expect([result.code, result.err]).toEqual([0, lines(leftover(6, 'comment'), leftover(11, 'comment'))]);
    expect(read(root, A)).toBe(TABLE_AFTER + RESULT + wrapper);
  });

  it('lists a mention whose lookup cannot be completed', () => {
    const unknown = '\ndeclare const Unknown: any;\n\n/** Reads `columns`. */\nexport class C extends Unknown {}\n';
    const { root, result } = renameTable(TABLE + unknown);
    expect(result.code).toBe(0);
    expect(result.err.split('\n')).toContain(leftover(8, 'comment'));
    expect(read(root, A)).toBe(TABLE_AFTER + unknown);
  });

  it('a class without the member falls back to the file', () => {
    const helper = '\n/** Formats `columns` values. */\nexport class Helper {}\n';
    const { root, result } = renameTable(TABLE + helper);
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, A)).toBe(TABLE_AFTER + helper.replace('columns', 'fields'));
  });
});

describe('--docs outside every owning class', () => {
  const HEAD = '// Rows carry `columns`; see {@link columns}.\nexport const ROWS = 1;\n\n';
  const SHOW = '\n/** Returns `columns`. */\nexport function show(t: Table): string[] {\n  return t.columns;\n}\n';

  it('rewrites when the only declaration of the old name in the file is renamed', () => {
    const { root, result } = renameTable(HEAD + TABLE + SHOW);
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, A)).toBe((HEAD + TABLE + SHOW).replaceAll('columns', 'fields'));
  });

  it.each([
    ['a class member', RESULT, ['--without', `${A}:11`]],
    ['a module-level constant', '\nexport const columns = 1;\n', []],
    ['a module-level function', '\nexport function columns(): number {\n  return 1;\n}\n', []],
  ])('lists beside an unchanged declaration: %s', (_name, other, flags) => {
    const head = '// Rows carry `columns`.\nexport const ROWS = 1;\n\n';
    const { root, result } = renameTable(head + TABLE + other, ...flags);
    expect(result.code).toBe(0);
    expect(result.err.split('\n')[0]).toBe(leftover(1, 'comment'));
    expect(read(root, A)).toBe(head + TABLE_AFTER + other);
  });

  it('rewrites when a stand-in is renamed with the member', () => {
    const { root, result } = renameTable(HEAD + TABLE + RESULT, '--with', `${A}:11`);
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, A)).toBe((HEAD + TABLE + RESULT).replaceAll('columns', 'fields'));
  });

  it('lists a plain word', () => {
    const { root, result } = renameTable(`// columns are plain here\n${TABLE}`);
    expect([result.code, result.err]).toEqual([0, lines(leftover(1, 'comment'))]);
    expect(read(root, A)).toBe(`// columns are plain here\n${TABLE_AFTER}`);
  });

  it.each(["'columns: missing'", "'columns (unset)'", '"columns of a row"', '`columns: ${1}`'])('lists a plain word opening %s', (literal) => {
    const use = `\nexport const MESSAGE = ${literal};\n`;
    const { root, result } = renameTable(TABLE + use);
    expect([result.code, result.err]).toEqual([0, lines(leftover(6, 'string'))]);
    expect(read(root, A)).toBe(TABLE_AFTER + use);
  });

  it('lists a code-marked mention in a file declaring nothing renamed', () => {
    const use = "import { Table } from './a';\n\n/** Shows `columns`. */\nexport class View extends Table {}\n";
    const root = tsProject({ [A]: TABLE, 'src/use.ts': use });
    const result = refactor(root, '--apply', 'rename', '--file', A, '--symbol', 'Table.columns', '--new-name', 'fields', '--docs');
    expect([result.code, result.err]).toEqual([0, lines(leftover(3, 'comment', 'columns', 'src/use.ts'))]);
    expect(read(root, 'src/use.ts')).toBe(use);
  });
});

describe('--docs over a map', () => {
  const TABLES = `// Every table lists its \`columns\`.\n\n${TABLE}\n/** A result and its \`columns\`. */\nexport class Result {\n  columns: string[] = [];\n}\n`;
  const entries = (second: string): Record<string, string>[] => [
    { file: A, symbol: 'Table.columns', new_name: 'fields' },
    { file: A, symbol: 'Result.columns', new_name: second },
  ];
  const mapped = (second: string, ...flags: string[]): { root: string; result: Run } => {
    const root = tsProject({ [A]: TABLES, 'map.yaml': mapYaml(entries(second)) });
    return { root, result: refactor(root, '--apply', 'rename-map', 'map.yaml', '--docs', ...flags) };
  };

  it('each class takes its own entry and a mention outside both is listed once', () => {
    const { root, result } = mapped('resultColumns');
    expect([result.code, result.err]).toEqual([0, lines(leftover(1, 'comment'))]);
    const after = read(root, A).split('\n');
    expect([after[0], after[2], after[4], after[7], after[9]]).toEqual([
      '// Every table lists its `columns`.',
      '/** Lists its `fields`. */',
      '  fields: string[] = [];',
      '/** A result and its `resultColumns`. */',
      '  resultColumns: string[] = [];',
    ]);
  });

  it('a lookup through two renamed bases takes the first', () => {
    const rows = 'export interface Table {\n  columns: string[];\n}\n\nexport interface Result {\n  columns: string[];\n}\n';
    const both = '\n/** Reads `columns`. */\nexport interface Both extends Table, Result {}\n';
    const root = tsProject({ [A]: rows + both, 'map.yaml': mapYaml(entries('resultColumns')) });
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml', '--docs');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, A).split('\n')[8]).toBe('/** Reads `fields`. */');
  });

  it('entries converging on one name rewrite the mention outside both', () => {
    const { root, result } = mapped('fields');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, A)).toBe(TABLES.replaceAll('columns', 'fields'));
  });
});
