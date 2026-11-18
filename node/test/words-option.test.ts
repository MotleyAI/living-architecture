// dr-refactor --words TABLE on a rename: carve-outs leave matching stand-ins and list the --docs mentions they cover (TypeScript).
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { read, refactor, tsProject } from './refactor-project.js';

const SOURCE = `/** Holds \`columns\`. */
export class Ds {
  columns: string[] = [];
}

/** Probes \`columns\`. */
export class Probe {
  columns: string[] = [];
}
`;
const RENAME = ['--apply', 'rename', '--file', 'src/c.ts', '--symbol', 'Ds.columns', '--new-name', 'fields'];
const WORDS = 'words:\n- {from: columns, to: fields}\n- {from: rows, to: records}\n';
const PROBE = `${WORDS}carve_outs:\n- words: [columns]\n  symbols:\n  - {file: src/c.ts, symbol: Probe.columns}\n`;
const DS = SOURCE.slice(0, SOURCE.indexOf('\n\n') + 1);
const DS_RENAMED = '/** Holds `fields`. */\nexport class Ds {\n  fields: string[] = [];\n}\n';
const FIELD_ONLY = SOURCE.replace('  columns: string[] = [];\n', '  fields: string[] = [];\n');

const standIn = (line: number, cls: string): string => `${message('refactor.stand-in', { path: 'src/c.ts', line, cls, attr: 'columns' })}\n`;
const leftover = (line: number): string => `${message('refactor.leftover', { path: 'src/c.ts', line, where: 'comment', old: 'columns' })}\n`;

function run(source: string, table: string | null, ...extra: string[]): { result: ReturnType<typeof refactor>; text: string } {
  const root = tsProject({ 'src/c.ts': source, ...(table === null ? {} : { 'words.yaml': table }) });
  const result = refactor(root, ...RENAME, ...(table === null ? [] : ['--words', 'words.yaml']), ...extra);
  return { result, text: read(root, 'src/c.ts') };
}

describe('--words and stand-ins', () => {
  it('leaves a stand-in a symbols carve-out locates', () => {
    const { result, text } = run(SOURCE, PROBE);
    expect([result.code, result.err, text]).toEqual([0, '', FIELD_ONLY]);
  });

  it('reports a stand-in when the carve-out is for another word', () => {
    const { result } = run(SOURCE, `${WORDS}carve_outs:\n- {words: [rows], paths: ['src/**']}\n`);
    expect(result).toEqual({ code: 1, out: '', err: standIn(8, 'Probe') });
  });

  it('renames a carved stand-in named by --with', () => {
    const { result, text } = run(SOURCE, PROBE, '--with', 'src/c.ts:8');
    expect([result.code, result.err, text.split('fields: string[] = [];').length - 1]).toEqual([0, '', 2]);
  });

  it('renames a carved stand-in named by both --with and --without', () => {
    const { result, text } = run(SOURCE, PROBE, '--without', 'src/c.ts:8', '--with', 'src/c.ts:8');
    expect([result.code, result.err, text.split('fields: string[] = [];').length - 1]).toEqual([0, '', 2]);
  });
});

describe('--docs --words', () => {
  it("lists a mention in the JSDoc attached to a carved member's class", () => {
    const { result, text } = run(SOURCE, PROBE, '--docs');
    expect([result.code, result.err, text]).toEqual([0, leftover(6), SOURCE.replace(DS, DS_RENAMED)]);
  });

  it('rewrites a mention in a comment before the class that is no JSDoc of it', () => {
    const source = SOURCE.replace('/** Probes `columns`. */', '// probes `columns`');
    const { result, text } = run(source, PROBE, '--docs');
    expect([result.code, result.err, text]).toEqual([0, '', source.replace(DS, DS_RENAMED).replace('// probes `columns`', '// probes `fields`')]);
  });

  it('lists every mention of the file of a carved module-level name', () => {
    const source = `${SOURCE}\nexport const columns: string[] = [];\n`;
    const table = `${WORDS}carve_outs:\n- words: [columns]\n  symbols:\n  - {file: src/c.ts, symbol: columns}\n`;
    const { result, text } = run(source, table, '--docs', '--without', 'src/c.ts:8');
    expect([result.code, result.err, text]).toEqual([0, leftover(1) + leftover(6), source.replace('  columns: string[] = [];\n', '  fields: string[] = [];\n')]);
  });

  it('rewrites a mention in the scope of a carved declaration whose name only holds the old name', () => {
    const source = `${DS}\nexport function census(allColumns: IntrospectedColumn[]): number {\n  // counts \`columns\`\n  return allColumns.length;\n}\n`;
    const table = `${WORDS}carve_outs:\n- {words: [columns], annotated: [IntrospectedColumn]}\n`;
    const { result, text } = run(source, table, '--docs');
    const compound = `${message('refactor.compound', { path: 'src/c.ts', line: 6, name: 'allColumns', old: 'columns' })}\n`;
    expect([result.code, result.err, text]).toEqual([0, compound, source.replace(DS, DS_RENAMED).replace('// counts `columns`', '// counts `fields`')]);
  });

  it('rewrites every code-marked mention of the declaring file without --words', () => {
    const { result, text } = run(SOURCE, null, '--docs', '--without', 'src/c.ts:8');
    expect([result.code, result.err, text.split('`fields`').length - 1]).toEqual([0, '', 2]);
  });
});
