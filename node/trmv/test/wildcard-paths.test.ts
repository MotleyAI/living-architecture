// trmv-refactor wildcard symbol paths: `*.<locals>.NAME` and `Scope.*.<locals>.NAME` name every local of a name (TypeScript).
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { entryRefusal, files, read, refactor, renameHeader, tsProject } from './refactor-project.js';

const SOURCE = `export function f(name: string): string {
  const model = name.toUpperCase();
  const inner = (): string => {
    const model = name.toLowerCase();
    return model;
  };
  return model + inner();
}

export class Query {
  run(name: string): string {
    const model = name.trim();
    const step = function (): string {
      const model = name.trimEnd();
      return model;
    };
    return model + step();
  }

  plan(name: string): string {
    for (const model of name) {
      console.log(model);
    }
    return name;
  }
}

export function h(model: string): string {
  return model;
}

export const k = (name: string): string => {
  const modle = name;
  return modle;
};
`;
const H = 'export function h(model: string): string {\n  return model;\n}\n';
const renamed = (text: string): string => text.replaceAll('model', 'dataset');
const region = (start: string, end: string): string => SOURCE.slice(SOURCE.indexOf(start), SOURCE.indexOf(end));
const wild = (symbol: string, intent = 'new_name: dataset'): string => `{file: src/l.ts, symbol: '${symbol}', ${intent}}`;

function project(source = SOURCE): string {
  return tsProject({ 'src/l.ts': source, 'src/d.ts': 'export {};\n' });
}

function runMap(root: string, ...entries: string[]): ReturnType<typeof refactor> {
  writeFileSync(join(root, 'map.yaml'), entries.map((entry) => `- ${entry}\n`).join(''));
  return refactor(root, '--apply', 'rename-map', 'map.yaml');
}

describe('a wildcard path', () => {
  it('over a file renames every local of functions, methods, arrow functions and function expressions, and no parameter', () => {
    const root = project();
    const result = runMap(root, wild('*.<locals>.model'));
    expect([result.code, result.err, read(root, 'src/l.ts')]).toEqual([0, '', renamed(SOURCE).replace(renamed(H), H)]);
  });

  it('scoped to a class renames the locals nested at any depth inside it', () => {
    const root = project();
    const result = runMap(root, wild('Query.*.<locals>.model'));
    const query = region('export class Query', 'export function h(');
    expect([result.code, result.err, read(root, 'src/l.ts')]).toEqual([0, '', SOURCE.replace(query, renamed(query))]);
  });

  it('scoped to a function renames the locals of the functions nested inside it only', () => {
    const root = project();
    const result = runMap(root, wild('f.*.<locals>.model'));
    const inner = region('  const inner =', '  return model + inner();');
    expect([result.code, result.err, read(root, 'src/l.ts')]).toEqual([0, '', SOURCE.replace(inner, renamed(inner))]);
  });

  it('equals one entry per local, under one header', () => {
    const left = project();
    const right = project();
    const explicit = ['Query.run', 'Query.run.<locals>.step', 'Query.plan'].map((path) => `{file: src/l.ts, symbol: ${path}.<locals>.model, new_name: dataset}`);
    const expected = runMap(left, ...explicit);
    const actual = runMap(right, wild('Query.*.<locals>.model'));
    const header = `${renameHeader('model', 'dataset')}\n`;
    expect([actual, read(right, 'src/l.ts')]).toEqual([{ code: 0, out: expected.out.replace(header, '').replace(header, ''), err: '' }, read(left, 'src/l.ts')]);
  });

  it('is taken by rename --symbol', () => {
    const root = project();
    const result = refactor(root, '--apply', 'rename', '--file', 'src/l.ts', '--symbol', 'Query.*.<locals>.model', '--new-name', 'dataset');
    expect([result.code, result.out.split(renameHeader('model', 'dataset')).length - 1, result.err, read(root, 'src/l.ts').includes('const dataset = name.trim();')]).toEqual([0, 1, '', true]);
  });

  // A misplaced `*` is unresolved like any path; which scope's names it lists is not pinned.
  it.each<[string, string | null]>([
    ['*.<locals>.modell', 'Query, f, h, k'],
    ['Query.*.<locals>.modle', 'plan, run'],
    ['k.*.<locals>.model', 'modle'],
    ['*.model', null],
    ['f.<locals>.*', null],
    ['*', null],
    ['*.*.<locals>.model', null],
    ['Qu*.<locals>.model', null],
    ['*.<locals>.inner(x)', null],
    ["*.<locals>.model['x']", null],
  ])('%s that locates nothing or is misplaced is unresolved', (symbol, candidates) => {
    const root = project();
    const before = files(root);
    const result = refactor(root, '--apply', 'rename', '--file', 'src/l.ts', '--symbol', symbol, '--new-name', 'dataset');
    const prefix = entryRefusal(`src/l.ts ${symbol}`, message('refactor.symbol-unresolved', { path: 'src/l.ts', symbol, candidates: candidates ?? '' }));
    const matches = candidates === null ? result.err.startsWith(prefix) && result.err.endsWith('\n') : result.err === `${prefix}\n`;
    expect([result.code, result.out, matches, files(root)]).toEqual([2, '', true, before]);
  });
});

const WILDCARD = message('refactor.symbol-wildcard', { path: 'src/l.ts', symbol: '*.<locals>.model' });
// The refusal of entry 1 located by the entry's own symbol.
const BY_WILDCARD = `${entryRefusal('src/l.ts *.<locals>.model', WILDCARD)}\n`;
const BY_F = `${entryRefusal('src/l.ts f', WILDCARD)}\n`;

describe('only a rename takes a wildcard', () => {
  it.each<[string, string[], string]>([
    ['retarget --symbol', ['retarget', '--file', 'src/l.ts', '--symbol', '*.<locals>.model', '--target', 'f'], BY_WILDCARD],
    ['retarget --target', ['retarget', '--file', 'src/l.ts', '--symbol', 'f', '--target', '*.<locals>.model'], BY_F],
    ['move-symbol --symbol', ['move-symbol', '--file', 'src/l.ts', '--symbol', '*.<locals>.model', '--dest', 'src/d.ts'], `${WILDCARD}\n`],
  ])('%s refuses it', (_name, argv, err) => {
    const root = project();
    const before = files(root);
    expect([refactor(root, '--apply', ...argv), files(root)]).toEqual([{ code: 2, out: '', err }, before]);
  });

  it.each([
    ['symbol', wild('*.<locals>.model', 'retarget: f'), BY_WILDCARD],
    ['retarget', "{file: src/l.ts, symbol: f, retarget: '*.<locals>.model'}", BY_F],
  ])('a retarget entry refuses it as its %s', (_name, entry, err) => {
    expect(runMap(project(), entry)).toEqual({ code: 2, out: '', err });
  });
});

describe('a wildcard entry beside other entries', () => {
  const one = (next: string): string => `{file: src/l.ts, symbol: Query.run.<locals>.model, new_name: ${next}}`;
  const duplicate = `${message('refactor.map-duplicate', { map: 'map.yaml', first: 1, second: 2 })}\n`;

  it('is a duplicate of an entry renaming one of its locals differently', () => {
    expect(runMap(project(), wild('Query.*.<locals>.model'), one('table'))).toEqual({ code: 2, out: '', err: duplicate });
  });

  it('merges with an entry renaming one of its locals to the same name', () => {
    const root = project();
    const result = runMap(root, wild('Query.*.<locals>.model'), one('dataset'));
    const query = region('export class Query', 'export function h(');
    expect([result.code, result.err, read(root, 'src/l.ts')]).toEqual([0, '', SOURCE.replace(query, renamed(query))]);
  });

  it('is a duplicate of another wildcard reaching one of its locals with another name', () => {
    expect(runMap(project(), wild('*.<locals>.model'), wild('Query.*.<locals>.model', 'new_name: table'))).toEqual({ code: 2, out: '', err: duplicate });
  });

  it('is refused whole when one of its locals meets a name its function binds', () => {
    const root = project(`${SOURCE}\nexport function taken(name: string): string {\n  const dataset = name;\n  const model = name;\n  return model + dataset;\n}\n`);
    const before = files(root);
    const result = runMap(root, wild('*.<locals>.model'));
    const expected = `${entryRefusal('src/l.ts *.<locals>.model', message('refactor.name-conflict', { name: 'dataset', path: 'src/l.ts', line: 38 }))}\n`;
    expect([result, files(root)]).toEqual([{ code: 1, out: '', err: expected }, { ...before, 'map.yaml': read(root, 'map.yaml') }]);
  });
});
