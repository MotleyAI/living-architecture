// `refactor.string_forms`: strings of a declared mini-language are respelled with a class or module-level symbol.
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ConfigError, loadConfig } from '../src/config/index.js';
import { message } from '../src/contract/index.js';
import { mapYaml, read, refactor, tsProject } from './refactor-project.js';
import type { Run } from './cli-run.js';

const FORMS = [String.raw`NODE TABLE (\w+)`, String.raw`\(\w*:(\w+)\)`];
const CONFIG = `refactor:\n  string_forms:\n${FORMS.map((form) => `  - '${form}'\n`).join('')}`;
const G = 'src/g.ts';
const MODEL = "export class Model {\n  name = '';\n}\n\n";
const MODEL_AFTER = MODEL.replace('class Model', 'class Dataset');
const SCHEMA = "export const SCHEMA = 'CREATE NODE TABLE Model(name STRING, PRIMARY KEY(name))';\n";
const FIND = 'export const FIND = "MATCH (m:Model) RETURN m.name";\n';
const renamed = (text: string): string => text.replaceAll('Model', 'Dataset');
const leftover = (line: number): string => `${message('refactor.leftover', { path: G, line, where: 'string', old: 'Model' })}\n`;

/** `Model -> Dataset` under the Cypher forms. */
function forms(project: Record<string, string>, ...flags: string[]): { root: string; result: Run } {
  const root = tsProject(project, CONFIG);
  return { root, result: refactor(root, '--apply', 'rename', '--file', G, '--symbol', 'Model', '--new-name', 'Dataset', ...flags) };
}

describe('refactor.string_forms', () => {
  it('labels follow the class without --docs', () => {
    const { root, result } = forms({ [G]: MODEL + SCHEMA + FIND });
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, G)).toBe(MODEL_AFTER + renamed(SCHEMA) + renamed(FIND));
  });

  it('a form in another file follows the class', () => {
    const { root, result } = forms({ [G]: MODEL, 'src/q.ts': FIND });
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/q.ts')).toBe(renamed(FIND));
  });

  it('template text holds form sites, each part searched', () => {
    const text = 'export const find = (i: number): string => `MATCH (m:Model) WHERE m.id = ${i} RETURN (n:Model)`;\nexport const PLAIN = `MATCH (a:Model)-[:HAS]->(b:Model)`;\n';
    const { root, result } = forms({ [G]: MODEL + text });
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, G)).toBe(MODEL_AFTER + renamed(text));
  });

  it.each([[false], [true]])('another symbol in the form and a plain word are unchanged (--docs %j)', (docs) => {
    const text = "export const OTHER = 'MATCH (m:ModelColumn)';\nexport const PROSE = 'a Model in prose';\n";
    const { root, result } = forms({ [G]: MODEL + text }, ...(docs ? ['--docs'] : []));
    expect([result.code, result.err]).toEqual([0, docs ? leftover(6) : '']);
    expect(read(root, G)).toBe(MODEL_AFTER + text);
  });

  it('a rewritten form site is not listed as a --docs mention', () => {
    const { root, result } = forms({ [G]: MODEL + FIND }, '--docs');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, G)).toBe(MODEL_AFTER + renamed(FIND));
  });

  it.each([[false], [true]])('a simple-name collision lists every form site (--docs %j)', (docs) => {
    const { root, result } = forms({ [G]: MODEL + SCHEMA + FIND, 'src/other.ts': MODEL }, ...(docs ? ['--docs'] : []));
    expect([result.code, result.err]).toEqual([0, leftover(5) + leftover(6)]);
    expect(read(root, G)).toBe(MODEL_AFTER + SCHEMA + FIND);
  });

  it('a collision renamed to the same name by the run rewrites the sites', () => {
    const entries = [
      { file: G, symbol: 'Model', new_name: 'Dataset' },
      { file: 'src/other.ts', symbol: 'Model', new_name: 'Dataset' },
    ];
    const root = tsProject({ [G]: MODEL + FIND, 'src/other.ts': MODEL, 'map.yaml': mapYaml(entries) }, CONFIG);
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, G)).toBe(MODEL_AFTER + renamed(FIND));
  });

  it('a pick rewrites a listed form site', () => {
    const { root, result } = forms({ [G]: MODEL + SCHEMA + FIND, 'src/other.ts': MODEL }, '--docs', '--docs-pick', `${G}:5`);
    expect([result.code, result.err]).toEqual([0, leftover(6)]);
    expect(read(root, G)).toBe(MODEL_AFTER + renamed(SCHEMA) + FIND);
  });

  it('a kept line and a kept literal keep their form sites', () => {
    const queries = "export const QUERIES = { version: 1, find: 'MATCH (m:Model)' };\n";
    const { root, result } = forms({ [G]: MODEL + SCHEMA + queries + FIND }, '--keep', `${G}:5`, '--keep-literal', 'version');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, G)).toBe(MODEL_AFTER + SCHEMA + queries + renamed(FIND));
  });

  it.each([
    ['an escape', String.raw`export const ESCAPED = 'MATCH (m:\x4dodel)';` + '\n'],
    ['a non-ASCII literal', "export const ACCENT = 'MATCH (m:Model) // mod\u00e8le';\n"],
  ])('the raw source text is matched: %s', (_name, text) => {
    const { root, result } = forms({ [G]: MODEL + text });
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, G)).toBe(MODEL_AFTER + text);
  });

  it('a non-ASCII literal is a --docs mention only', () => {
    const text = "export const ACCENT = 'MATCH (m:Model) // mod\u00e8le';\n";
    const { root, result } = forms({ [G]: MODEL + text }, '--docs');
    expect([result.code, result.err]).toEqual([0, leftover(5)]);
    expect(read(root, G)).toBe(MODEL_AFTER + text);
  });

  it('a non-ASCII template part does not hide an ASCII one', () => {
    const text = 'export const find = (i: number): string => `MATCH (m:Model) ${i} // mod\u00e8le (n:Model)`;\n';
    const { root, result } = forms({ [G]: MODEL + text });
    expect(result.code).toBe(0);
    expect(read(root, G)).toBe(MODEL_AFTER + text.replace('`MATCH (m:Model)', '`MATCH (m:Dataset)'));
  });

  it('a module-level function uses the forms', () => {
    const text = "export function lookup(): number {\n  return 1;\n}\n\nexport const CALL = 'RETURN (x:lookup)';\n";
    const root = tsProject({ [G]: text }, CONFIG);
    const result = refactor(root, '--apply', 'rename', '--file', G, '--symbol', 'lookup', '--new-name', 'search');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, G)).toBe(text.replaceAll('lookup', 'search'));
  });

  it.each([
    ['a member', 'Model.name', `${MODEL}export const FIND = 'MATCH (m:name)';\n`],
    ['a parameter', 'find(name)', "export function find(name: string): string {\n  return name + 'MATCH (m:name)';\n}\n"],
    ['a local', 'find.<locals>.name', "export function find(): string {\n  const name = 'x';\n  return name + 'MATCH (m:name)';\n}\n"],
  ])('%s rename ignores the forms', (_name, symbol, text) => {
    const root = tsProject({ [G]: text }, CONFIG);
    const result = refactor(root, '--apply', 'rename', '--file', G, '--symbol', symbol, '--new-name', 'title');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, G)).toContain("'MATCH (m:name)'");
    expect(read(root, G)).toContain('title');
  });
});

describe('refactor.string_forms in the config', () => {
  const repo = (patterns: unknown): string => {
    const root = mkdtempSync(join(tmpdir(), 'la-forms-'));
    writeFileSync(join(root, 'living-architecture.yaml'), `refactor:\n  string_forms: ${JSON.stringify(patterns)}\n`);
    return root;
  };
  const error = (root: string): string => {
    try {
      loadConfig(root);
    } catch (caught) {
      if (caught instanceof ConfigError) return caught.message;
      throw caught;
    }
    return '';
  };

  it('is read from the refactor section, empty by default', () => {
    expect(loadConfig(repo(FORMS)).refactor.string_forms).toEqual(FORMS);
    expect(loadConfig(mkdtempSync(join(tmpdir(), 'la-forms-'))).refactor.string_forms).toEqual([]);
  });

  it.each([
    ['no group', String.raw`NODE TABLE \w+`],
    ['a non-capturing group only', String.raw`NODE TABLE (?:\w+)`],
    ['two groups', String.raw`(\w+) TABLE (\w+)`],
    ['a named group', String.raw`NODE TABLE (?<name>\w+)`],
    ['a lookahead', String.raw`NODE TABLE (\w+)(?=\()`],
    ['a pattern that does not compile', String.raw`NODE TABLE (\w+`],
  ])('rejects %s, naming the key and the pattern', (_name, pattern) => {
    const message_ = error(repo([FORMS[0], pattern]));
    expect(message_).toContain('refactor.string_forms');
    expect(message_).toContain(pattern);
  });

  it.each([['NODE (\\w+)'], [[3]], [[null]]])('must be a list of strings: %j', (value) => {
    expect(error(repo(value))).toContain('string_forms');
  });

  it.each([[String.raw`(?:NODE|REL) TABLE (\w+)`], [String.raw`[(](\w+)[)]`], [String.raw`\((\w+)\)`]])('accepts one capturing group: %s', (pattern) => {
    expect(loadConfig(repo([pattern])).refactor.string_forms).toEqual([pattern]);
  });

  it('dr-refactor exits 2 on an invalid form', () => {
    const root = tsProject({ [G]: MODEL + FIND }, "refactor:\n  string_forms: ['(a)(b)']\n");
    const result = refactor(root, '--apply', 'rename', '--file', G, '--symbol', 'Model', '--new-name', 'Dataset');
    expect([result.code, result.out]).toEqual([2, '']);
    expect(result.err).toContain('refactor.string_forms');
    expect(result.err).toContain('(a)(b)');
    expect(read(root, G)).toBe(MODEL + FIND);
  });
});
