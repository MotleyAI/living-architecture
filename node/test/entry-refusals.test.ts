// dr-refactor: a refusal names its entry and locator, is printed once, and site paths resolve against the project;
// the own-scope name check runs before any reference search.
import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { currentFormat } from '../src/config/index.js';
import { message } from '../src/contract/index.js';
import { Site } from '../src/refactor/sites.js';
import { run, tempRepo } from './cli-run.js';
import { TSCONFIG, entryRefusal, finalReport, mapYaml, read, refactor, refactorRaw, tsProject } from './refactor-project.js';

const CHECKS = '[resolve]\n[checks]\n';
const REFERENCES = message('refactor.progress-phase', { phase: 'references' });
const CONFLICTS = message('refactor.progress-phase', { phase: 'conflicts' });
const A = 'export function foo(): number {\n  return 1;\n}\n';
const conflict = (name: string, path: string, line: number): string => message('refactor.name-conflict', { name, path, line });

describe('the entry and its locator', () => {
  it.each([
    [['--line', '1', '--col', '1'], 'src/a.ts:1:1', message('refactor.cannot-rename'), 1],
    [['--line', '99'], 'src/a.ts:99', message('refactor.line-out-of-range', { line: 99, count: 3 }), 1],
    [['--symbol', 'nope'], 'src/a.ts nope', message('refactor.symbol-unresolved', { path: 'src/a.ts', symbol: 'nope', candidates: 'foo' }), 2],
    [['--offset', '999'], 'src/a.ts offset 999', message('refactor.offset-out-of-range', { offset: 999, count: A.length }), 1],
  ])('a rename that does not resolve names entry 1 and its locator (%j)', (locator, shown, finding, code) => {
    const root = tsProject({ 'src/a.ts': A });
    const result = refactorRaw(root, 'rename', '--file', 'src/a.ts', ...locator, '--new-name', 'bar');
    expect(result).toEqual({ code, out: '', err: `${CHECKS}${entryRefusal(shown, finding)}\n` });
  });

  it('prints a locator relative to the project', () => {
    const root = tsProject({ 'src/a.ts': A });
    const result = refactorRaw(root, 'rename', '--file', join(root, 'src', 'a.ts'), '--line', '99', '--new-name', 'bar');
    const refused = entryRefusal('src/a.ts:99', message('refactor.line-out-of-range', { line: 99, count: 3 }));
    expect(result).toEqual({ code: 1, out: '', err: `${CHECKS}${refused}\n` });
  });

  it('names merged entries together, with the first one’s locator', () => {
    const m = 'export const old = 1;\n\nexport function f(): number {\n  const fresh = 2;\n  return old + fresh;\n}\n';
    const map = mapYaml([
      { file: 'src/m.ts', symbol: 'old', new_name: 'fresh' },
      { file: 'src/m.ts', line: 1, col: 14, new_name: 'fresh' },
    ]);
    const root = tsProject({ 'src/m.ts': m, 'map.yaml': map });
    const result = refactor(root, 'rename-map', 'map.yaml');
    expect(result).toEqual({ code: 1, out: '', err: `${entryRefusal('src/m.ts old', conflict('fresh', 'src/m.ts', 4), 1, 2)}\n` });
  });
});

describe('each refusal once', () => {
  const standIn = 'export class A {\n  m(): number {\n    return 1;\n  }\n}\n\nexport class B {\n  m(): number {\n    return 2;\n  }\n}\n';

  it.each([[[]], [['--fail-fast']]])('a refusal printed under its group still sets the exit code (flags %j)', (flags) => {
    const root = tsProject({ 'src/a.ts': standIn });
    const { code, out, err } = refactorRaw(root, '--apply', 'rename', '--file', 'src/a.ts', '--symbol', 'A.m', '--new-name', 'n', ...flags);
    const finding = message('refactor.stand-in', { path: 'src/a.ts', line: 8, cls: 'B', attr: 'm' });
    const refused = message('refactor.progress-refused', {
      phase: 'rules', n: 1, count: 1, entries: message('refactor.progress-entry', { index: 1 }), old: 'm', new: 'n', refusals: 1,
    });
    const tail = flags.length === 0 ? [refused, finding, CONFLICTS] : [refused, finding];
    expect([code, out]).toEqual([1, '']);
    expect(err.trimEnd().split('\n').slice(-tail.length)).toEqual(tail);
    expect(finalReport(err)).toBe(`${finding}\n`);
    expect(read(root, 'src/a.ts')).toBe(standIn);
  });
});

describe('sites resolve against the project', () => {
  const cwd = process.cwd();
  afterEach(() => process.chdir(cwd));

  const use = "import { foo } from './a';\n\nexport const x = foo();\nexport const y = foo();\n";
  const nested = (): string =>
    tempRepo({
      'living-architecture.yaml': `format: ${currentFormat()}\n`,
      'proj/tsconfig.json': TSCONFIG,
      'proj/src/a.ts': A,
      'proj/src/use.ts': use,
    });

  it('parses a site against the project root, whatever the working directory', () => {
    const parent = realpathSync(mkdtempSync(join(tmpdir(), 'la-sites-')));
    const root = join(parent, 'proj');
    mkdirSync(join(root, 'src'), { recursive: true });
    writeFileSync(join(root, 'src', 'a.ts'), A);
    process.chdir(parent);
    expect(Site.parse('src/a.ts:2', root).covers('src/a.ts', 2)).toBe(true);
    expect(Site.parse('src/a.ts:2', root).missing(root)).toBe(false);
    expect(Site.parse(`${root}/src/a.ts:2`, root).covers('src/a.ts', 2)).toBe(true);
    expect(Site.parse('proj/src/a.ts:2', root).parts).toBeNull();
    expect(Site.parse('proj/src/a.ts:2', root).missing(root)).toBe(true);
  });

  it.each([['relative'], ['absolute']])('takes a %s --keep from another directory', (form) => {
    const root = nested();
    const keep = form === 'absolute' ? `${join(realpathSync(root), 'proj', 'src', 'use.ts')}:3` : 'src/use.ts:3';
    const argv = ['--project', 'proj', '--apply', 'rename', '--file', 'proj/src/a.ts', '--symbol', 'foo', '--new-name', 'bar', '--keep', keep];
    const result = run(root, 'dr-refactor', argv);
    expect([result.code, finalReport(result.err)]).toEqual([0, '']);
    expect(read(root, 'proj/src/use.ts')).toBe("import { bar } from './a';\n\nexport const x = foo();\nexport const y = bar();\n");
  });

  it('refuses a --keep relative to the working directory', () => {
    const root = nested();
    const argv = ['--project', 'proj', 'rename', '--file', 'proj/src/a.ts', '--symbol', 'foo', '--new-name', 'bar', '--keep', 'proj/src/use.ts:3'];
    const missing = message('refactor.site-missing', { option: '--keep', site: 'proj/src/use.ts:3' });
    expect(run(root, 'dr-refactor', argv)).toEqual({ code: 2, out: '', err: `${CHECKS}${missing}\n` });
  });
});

describe('the own-scope check', () => {
  const method = '  old(): number {\n    return 1;\n  }\n}\n';
  it.each([
    ['a method', `export class C {\n  fresh(): number {\n    return 2;\n  }\n${method}`, 'C.old', 2],
    ['a field', `export class C {\n  fresh = 0;\n${method}`, 'C.old', 2],
    ['an accessor', `export class C {\n  get fresh(): number {\n    return 0;\n  }\n${method}`, 'C.old', 2],
    ['a parameter property', `export class C {\n  constructor(public fresh: number) {}\n${method}`, 'C.old', 2],
    ['a static member, for a static one', 'export class C {\n  static fresh = 1;\n  static old = 2;\n}\n', 'C.old', 2],
    ['an interface property', 'export interface I {\n  fresh: number;\n  old(): number;\n}\n', 'I.old', 2],
    ['another parameter', 'export function f(old: number, fresh: number): number {\n  return old - fresh;\n}\n', 'f(old)', 1],
    ['a local of the function', 'export function f(old: number): number {\n  const fresh = 2;\n  return old - fresh;\n}\n', 'f(old)', 2],
    ['a top-level constant', 'export const old = 1;\nexport const fresh = 2;\n', 'old', 2],
    ['a top-level function', 'export const old = 1;\n\nexport function fresh(): number {\n  return 2;\n}\n', 'old', 3],
  ])('refuses a new name the declaring scope holds before any reference search (%s)', (_kind, m, symbol, line) => {
    const root = tsProject({ 'src/m.ts': m });
    const result = refactorRaw(root, 'rename', '--file', 'src/m.ts', '--symbol', symbol, '--new-name', 'fresh');
    const refused = entryRefusal(`src/m.ts ${symbol}`, conflict('fresh', 'src/m.ts', line));
    expect(result).toEqual({ code: 1, out: '', err: `${CHECKS}${refused}\n` });
  });

  it.each([
    ['a static member, for an instance one', 'export class C {\n  static fresh = 1;\n  old = 2;\n}\n', 'C.old'],
    ['a type, for a value', 'export type fresh = number;\nexport const old = 1;\n', 'old'],
    ['a nested function', 'export function f(old: number): number {\n  const inner = (): number => {\n    const fresh = 2;\n    return fresh;\n  };\n  return old + inner();\n}\n', 'f(old)'],
    ['another function', 'export function f(old: number): number {\n  return old;\n}\n\nexport function g(fresh: number): number {\n  return fresh;\n}\n', 'f(old)'],
  ])('lets a new name another scope or meaning holds pass the checks (%s)', (_kind, m, symbol) => {
    const root = tsProject({ 'src/m.ts': m });
    const { code, err } = refactorRaw(root, '--apply', 'rename', '--file', 'src/m.ts', '--symbol', symbol, '--new-name', 'fresh');
    expect(code).toBe(0);
    expect(err.split('\n')).toContain(REFERENCES);
  });

  it.each([
    ['an inherited member', 'export class Base {\n  fresh(): number {\n    return 2;\n  }\n}\n\nexport class C extends Base {\n  old(): number {\n    return 1;\n  }\n}\n', 'C.old', 2],
    ['a captured read', 'export const old = 1;\n\nexport function f(): number {\n  const fresh = 2;\n  return old + fresh;\n}\n', 'old', 4],
    ['a class merging with an interface', 'export interface old {\n  a: number;\n}\n\nexport class fresh {\n  b = 1;\n}\n\nexport const x: old = { a: 1 };\n', 'old', 5],
  ])('leaves a conflict outside the declaring scope to the conflicts phase (%s)', (_kind, m, symbol, line) => {
    const root = tsProject({ 'src/m.ts': m });
    const { code, out, err } = refactorRaw(root, 'rename', '--file', 'src/m.ts', '--symbol', symbol, '--new-name', 'fresh');
    expect([code, out]).toEqual([1, '']);
    expect(err.trimEnd().split('\n').slice(-2)).toEqual([CONFLICTS, entryRefusal(`src/m.ts ${symbol}`, conflict('fresh', 'src/m.ts', line))]);
  });

  it('does not refuse a name another entry frees', () => {
    const f = 'export function f(x: number, y: number): number {\n  return x - y;\n}\n';
    const map = mapYaml([
      { file: 'src/f.ts', symbol: 'f(x)', new_name: 'y' },
      { file: 'src/f.ts', symbol: 'f(y)', new_name: 'z' },
    ]);
    const root = tsProject({ 'src/f.ts': f, 'map.yaml': map });
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/f.ts')).toBe('export function f(y: number, z: number): number {\n  return y - z;\n}\n');
  });
});

describe('a --with stand-in two entries reach', () => {
  it('is refused at its declaration and at a read through it', () => {
    const q =
      'export class Query {\n  rootModel(): string {\n    return "q";\n  }\n}\n\nexport class Plan {\n  rootModel(): string {\n    return "p";\n  }\n}\n\n' +
      'export class Fake {\n  rootModel(): string {\n    return "f";\n  }\n}\n\nexport function read(f: Fake): string {\n  return f.rootModel();\n}\n';
    const map = mapYaml([
      { file: 'src/q.ts', symbol: 'Query.rootModel', new_name: 'population' },
      { file: 'src/q.ts', symbol: 'Plan.rootModel', new_name: 'rootDataset' },
    ]);
    const root = tsProject({ 'src/q.ts': q, 'map.yaml': map });
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml', '--with', 'src/q.ts:14');
    const sites = [14, 20].map((line) => message('refactor.map-conflict', { path: 'src/q.ts', line, first: 1, second: 2 }));
    expect(result).toEqual({ code: 1, out: '', err: sites.map((site) => `${site}\n`).join('') });
    expect(read(root, 'src/q.ts')).toBe(q);
  });
});
