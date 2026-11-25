// Word tables: the shared schema, loading through trmv-refactor, and every invalid form with its section and index.
import { describe, expect, it } from 'vitest';
import { language, message, schema, validate } from '../src/contract/index.js';
import { files, refactorRaw, tsProject } from './refactor-project.js';

const ROW = { from: 'model', to: 'dataset' };

describe('word-table schema', () => {
  it.each([
    [{ words: [ROW] }],
    [{ words: [ROW, { from: 'v1', to: 'v2' }], carve_outs: [], entries: [] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], annotated: ['BaseModel', '_Private', '$Scope', 'Modèle'] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], paths: ['src/sql/**', '*.ts'] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], symbols: [{ file: 'src/a.ts', symbol: 'f(model)' }] }] }],
    [{ words: [ROW], entries: [{ file: 'src/a.ts', symbol: 'A.model', new_name: 'population' }] }],
  ])('accepts %j', (document) => {
    expect(validate(schema('word-table'), document)).toEqual([]);
  });

  it.each([
    [[ROW]],
    [{}],
    [{ words: [] }],
    [{ words: [ROW], phrases: [] }],
    [{ words: [{ from: 'Model', to: 'dataset' }] }],
    [{ words: [{ from: 'model', to: 'data_set' }] }],
    [{ words: [{ from: '2d', to: 'flat' }] }],
    [{ words: [{ from: 'model', to: 'data set' }] }],
    [{ words: [{ from: 'modèle', to: 'dataset' }] }],
    [{ words: [{ from: 'model' }] }],
    [{ words: [{ from: 'model', to: 'dataset', plural: 'datasets' }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], paths: ['a/**'], annotated: ['T'] }] }],
    [{ words: [ROW], carve_outs: [{ words: [], paths: ['a/**'] }] }],
    [{ words: [ROW], carve_outs: [{ paths: ['a/**'] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], paths: [] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], annotated: ['Model[]'] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], annotated: ['schema.Model'] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], symbols: [{ file: 'a.ts' }] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], paths: ['a/**'], phrase: 'data model' }] }],
    [{ words: [ROW], entries: [{ file: 'a.ts', symbol: 'f', new_name: 'g', retarget: 'h' }] }],
    [{ words: [ROW], entries: [{ file: 'a.ts', new_name: 'g' }] }],
    [{ words: [ROW], entries: [{ module: 'a.ts', symbol: 'f', new_name: 'g' }] }],
    [{ words: [ROW], entries: ['f'] }],
    [{ words: [['model', 'dataset']] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], paths: ['a/**'], symbols: [{ file: 'a.ts', symbol: 'f' }] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], annotated: [] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], annotated: ['2d'] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], paths: [''] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], symbols: [] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], symbols: ['f(model)'] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], symbols: [{ file: '', symbol: 'f' }] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], symbols: [{ file: 'a.ts', symbol: '' }] }] }],
    [{ words: [ROW], carve_outs: [{ words: ['model'], symbols: [{ file: 'a.ts', symbol: 'f', new_name: 'g' }] }] }],
  ])('rejects %j', (document) => {
    expect(validate(schema('word-table'), document)).not.toEqual([]);
  });
});

describe('fixture decorators', () => {
  it('come from the language registry: pytest for Python, none for TypeScript', () => {
    expect([language('python').fixture_decorators, language('typescript').fixture_decorators]).toEqual([['pytest.fixture', 'pytest_asyncio.fixture'], []]);
  });
});

const SOURCE = `export const modelName = 'm';

export function f(model: string): string {
  return model;
}

export const alias = f;
`;
const VALID = 'words:\n- {from: model, to: dataset}\n';

function invalid(...items: [string, number][]): string {
  return items.map(([section, index]) => `${message('refactor.words-invalid', { table: 'words.yaml', section, index })}\n`).join('');
}

function generate(table: string | null): ReturnType<typeof refactorRaw> {
  const root = tsProject({ 'src/a.ts': SOURCE, ...(table === null ? {} : { 'words.yaml': table }) });
  return refactorRaw(root, 'generate-map', 'words.yaml');
}

const UNORDERED = `entries:
- {file: src/a.ts}
carve_outs:
- {words: [model]}
- {words: [model], paths: ['a/**']}
- {words: [x], paths: ['a/**']}
words:
- {from: model, to: dataset}
- {from: A, to: b}
- {from: c, to: c}
`;

describe('an invalid word table', () => {
  it.each<[string, string, [string, number][]]>([
    ['an uppercase from', 'words:\n- {from: model, to: dataset}\n- {from: Columns, to: fields}\n', [['words', 2]]],
    ['a from equal to its to', 'words:\n- {from: model, to: model}\n', [['words', 1]]],
    ['a from given twice', 'words:\n- {from: model, to: dataset}\n- {from: model, to: table}\n', [['words', 2]]],
    ['a row without a to', 'words:\n- {from: model}\n', [['words', 1]]],
    ['a YAML boolean as a word', 'words:\n- {from: model, to: dataset}\n- {from: off, to: on}\n', [['words', 2]]],
    ['an empty words list', 'words: []\n', [['words', 1]]],
    ['no words', 'carve_outs: []\n', [['words', 1]]],
    ['words that are no list', 'words: {model: dataset}\n', [['words', 1]]],
    ['a list', '- {from: model, to: dataset}\n', [['words', 1]]],
    ['text that is no YAML', 'words: [\n', [['words', 1]]],
    ['two matchers', `${VALID}carve_outs:\n- {words: [model], paths: ['a/**'], annotated: [T]}\n`, [['carve_outs', 1]]],
    ['no matcher', `${VALID}carve_outs:\n- {words: [model], paths: ['a/**']}\n- {words: [model]}\n`, [['carve_outs', 2]]],
    ['a carve-out word that is no from', `${VALID}carve_outs:\n- {words: [model, columns], paths: ['a/**']}\n`, [['carve_outs', 1]]],
    ['a carve-out word that is a to', `${VALID}carve_outs:\n- {words: [dataset], paths: ['a/**']}\n`, [['carve_outs', 1]]],
    ['an annotated name that is no identifier', `${VALID}carve_outs:\n- {words: [model], annotated: ['Model[]']}\n`, [['carve_outs', 1]]],
    ['an entry with both intents', `${VALID}entries:\n- {file: src/a.ts, symbol: f, new_name: g, retarget: h}\n`, [['entries', 1]]],
    ['an entry without a locator', `${VALID}entries:\n- {file: src/a.ts, symbol: f, new_name: g}\n- {file: src/a.ts, new_name: g}\n`, [['entries', 2]]],
    ['every section, in the order words, carve_outs, entries', UNORDERED, [['words', 2], ['words', 3], ['carve_outs', 1], ['carve_outs', 3], ['entries', 1]]],
  ])('%s names each item by section and index', (_name, table, items) => {
    expect(generate(table)).toEqual({ code: 2, out: '', err: invalid(...items) });
  });

  it('that does not exist names words item 1', () => {
    expect(generate(null)).toEqual({ code: 2, out: '', err: invalid(['words', 1]) });
  });
});

const COMMANDS: [string, string[]][] = [
  ['rename', ['rename', '--file', 'src/a.ts', '--symbol', 'f', '--new-name', 'g']],
  ['rename-map', ['rename-map', 'renames.yaml']],
  ['retarget', ['retarget', '--file', 'src/a.ts', '--symbol', 'alias', '--target', 'f']],
];
const RENAMES = '- {file: src/a.ts, symbol: f, new_name: g}\n';
const UNRESOLVED = `${VALID}carve_outs:\n- words: [model]\n  symbols:\n  - {file: src/a.ts, symbol: 'f(modle)'}\n`;
const UNRESOLVED_LINE = `${message('refactor.symbol-unresolved', { path: 'src/a.ts', symbol: 'f(modle)', candidates: 'model' })}\n`;

describe('--words TABLE', () => {
  it.each(COMMANDS)('on %s refuses an invalid table before any reference search', (_name, argv) => {
    const root = tsProject({ 'src/a.ts': SOURCE, 'renames.yaml': RENAMES, 'words.yaml': 'words:\n- {from: Model, to: dataset}\n' });
    const before = files(root);
    const result = refactorRaw(root, '--apply', ...argv, '--words', 'words.yaml');
    expect([result.code, result.out, result.err.includes('[references]'), result.err.endsWith(invalid(['words', 1])), files(root)]).toEqual([2, '', false, true, before]);
  });

  it.each(COMMANDS)('on %s refuses a carve-out symbol that resolves to nothing', (_name, argv) => {
    const root = tsProject({ 'src/a.ts': SOURCE, 'renames.yaml': RENAMES, 'words.yaml': UNRESOLVED });
    const result = refactorRaw(root, ...argv, '--words', 'words.yaml');
    expect([result.code, result.out, result.err.includes('[references]'), result.err.endsWith(UNRESOLVED_LINE)]).toEqual([2, '', false, true]);
  });

  it('generate-map refuses a carve-out symbol that resolves to nothing', () => {
    expect(generate(UNRESOLVED)).toEqual({ code: 2, out: '', err: UNRESOLVED_LINE });
  });
});
