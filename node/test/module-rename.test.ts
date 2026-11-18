// TypeScript module renames: the new-name rules, the taken check, and the mock calls the shared facts list.
import { describe, expect, it } from 'vitest';
import { language, message } from '../src/contract/index.js';
import { run, type Run } from './cli-run.js';
import { copyProject, files, mapYaml, refactorRaw, tsProject } from './refactor-project.js';

const PHASES = '[resolve]\n[checks]\n';
const A = { 'src/a.ts': 'export const X = 1;\n', 'src/use.ts': "import { X } from './a.js';\n\nexport const shown = X;\n" };
const TEST_TSCONFIG = '{\n  "compilerOptions": {"strict": true, "noEmit": true, "module": "esnext", "moduleResolution": "bundler"},\n  "include": ["src", "test"]\n}\n';
const API = 'export function get(): number {\n  return 1;\n}\n';

const RECEIVERS = [
  { name: 'vi', module: 'vitest' },
  { name: 'jest', module: '@jest/globals' },
];
const MODULE_CALLS = [
  { call: 'mock', factory: 1 },
  { call: 'doMock', factory: 1 },
  { call: 'unstable_mockModule', factory: 1 },
  { call: 'unmock' },
  { call: 'doUnmock' },
  { call: 'dontMock' },
  { call: 'setMock' },
  { call: 'importActual' },
  { call: 'importMock' },
  { call: 'requireActual' },
  { call: 'requireMock' },
  { call: 'createMockFromModule' },
];

const conflict = (path: string): string => `${PHASES}${message('refactor.name-conflict', { name: 'b', path, line: 1 })}\n`;
const renameA = (root: string, name: string): Run => refactorRaw(root, '--apply', 'rename', '--file', 'src/a.ts', '--new-name', name);

describe('module new name', () => {
  it.each(['b.ts', 'b.tsx', 'b.mts', 'b.cts', 'b.js', 'b.jsx', 'b.mjs', 'b.cjs', 'b.d.ts', 'b.d.mts', 'b.d.cts', '.', '..', 'a/b', String.raw`a\b`])(
    'refuses %j at resolution, writing nothing',
    (name) => {
      const root = tsProject(A);
      const before = files(root);
      expect(renameA(root, name)).toEqual({ code: 1, out: '', err: `${PHASES}${message('refactor.cannot-rename')}\n` });
      expect(files(root)).toEqual(before);
    },
  );

  it.each(['', 'a\0b'])('refuses a map entry renaming a module to %j at resolution', (name) => {
    const root = tsProject({ ...A, 'map.yaml': mapYaml([{ module: 'src/a.ts', new_name: name }]) });
    expect(refactorRaw(root, 'rename-map', 'map.yaml')).toEqual({ code: 1, out: '', err: `${PHASES}${message('refactor.cannot-rename')}\n` });
  });

  it.each([
    ['my-module', 'src/my-module.ts'],
    ['a.test', 'src/a.test.ts'],
    ['b.json', 'src/b.json.ts'],
  ])('accepts %j as the new stem, keeping the extension', (name, moved) => {
    const root = tsProject(A);
    const result = renameA(root, name);
    expect(result.code).toBe(0);
    expect(result.out).toContain(`${message('refactor.moved', { old: 'src/a.ts', new: moved })}\n`);
    expect(files(root)[moved]).toBe(A['src/a.ts']);
  });

  it('keeps a declaration file\'s whole extension', () => {
    const root = tsProject({ 'src/x.d.ts': 'export interface T {\n  n: number;\n}\n', 'src/use.ts': "import type { T } from './x';\n\nexport const t: T = { n: 1 };\n" });
    expect(refactorRaw(root, '--apply', 'rename', '--file', 'src/x.d.ts', '--new-name', 'y').code).toBe(0);
    expect(Object.keys(files(root))).toContain('src/y.d.ts');
    expect(files(root)['src/use.ts']).toContain("from './y'");
  });
});

describe('module rename taken check', () => {
  it.each(['src/b.ts', 'src/b.tsx', 'src/b.mts', 'src/b.cts', 'src/b.js', 'src/b.jsx', 'src/b.mjs', 'src/b.cjs', 'src/b.d.ts', 'src/b.d.mts', 'src/b.d.cts'])(
    'a sibling %s takes the stem: name-conflict naming it in the checks, writing nothing',
    (sibling) => {
      const root = tsProject({ ...A, [sibling]: 'export {};\n' });
      const before = files(root);
      expect(renameA(root, 'b')).toEqual({ code: 1, out: '', err: conflict(sibling) });
      expect(files(root)).toEqual(before);
    },
  );

  it('a directory of the stem with an index source is named by it', () => {
    const root = tsProject({ ...A, 'src/b/aaa.ts': 'export {};\n', 'src/b/index.ts': 'export {};\n' });
    expect(renameA(root, 'b')).toEqual({ code: 1, out: '', err: conflict('src/b/index.ts') });
  });

  it('a directory of the stem without an index source is named by its first file by path', () => {
    const root = tsProject({ ...A, 'src/b/zed.ts': 'export {};\n', 'src/b/util.ts': 'export {};\n' });
    expect(renameA(root, 'b')).toEqual({ code: 1, out: '', err: conflict('src/b/util.ts') });
  });

  it.each(['src/b.json', 'src/b.css', 'src/b.py', 'src/b.md'])('a sibling %s of another language takes nothing', (sibling) => {
    const root = tsProject({ ...A, [sibling]: 'x\n' });
    expect(renameA(root, 'b').code).toBe(0);
    expect(Object.keys(files(root))).toEqual(expect.arrayContaining(['src/b.ts', sibling]));
  });

  it('the module\'s own file does not take its name', () => {
    const root = tsProject(A);
    const before = files(root);
    expect(renameA(root, 'a').code).toBe(0);
    expect(files(root)).toEqual(before);
  });

  it.each(['d.ts', 'd.mts', 'd.cts'])('a declaration file renamed to its stem plus `.d` does not take its own new name (.%s)', (ext) => {
    const root = tsProject({ [`src/x.${ext}`]: 'export interface T {\n  n: number;\n}\n' });
    expect(refactorRaw(root, '--apply', 'rename', '--file', `src/x.${ext}`, '--new-name', 'x.d').code).toBe(0);
    expect(Object.keys(files(root))).toEqual(expect.arrayContaining([`src/x.d.${ext}`]));
  });

  it('a file of the stem in another directory takes nothing', () => {
    const root = tsProject({ ...A, 'src/lib/b.ts': 'export {};\n' });
    expect(renameA(root, 'b').code).toBe(0);
  });
});

describe('module rename without a locator', () => {
  it('equals its one-entry map byte for byte', () => {
    const single = tsProject({ ...A, 'map.yaml': mapYaml([{ module: 'src/a.ts', new_name: 'b' }]) });
    const mapped = copyProject(single);
    const expected = refactorRaw(single, '--apply', 'rename', '--file', 'src/a.ts', '--new-name', 'b');
    expect(expected.code).toBe(0);
    expect(refactorRaw(mapped, '--apply', 'rename-map', 'map.yaml')).toEqual(expected);
    expect(files(mapped)).toEqual(files(single));
  });

  it('retarget still needs a locator', () => {
    const root = tsProject(A);
    expect(refactorRaw(root, 'retarget', '--file', 'src/a.ts', '--target', 'Y')).toEqual({ code: 1, out: '', err: `${PHASES}${message('refactor.no-locator')}\n` });
  });
});

describe('mock module paths from the shared facts', () => {
  it('the shared facts list the framework receivers and the calls taking a module path', () => {
    const facts = language('typescript') as { mock_receivers?: unknown; mock_module_calls?: unknown };
    expect(facts.mock_receivers).toEqual(RECEIVERS);
    expect(facts.mock_module_calls).toEqual(MODULE_CALLS);
  });

  /** `src/api.ts` renamed to `client` with `test/m.test.ts` holding `test`: the test file's text afterwards. */
  function renamedTest(test: string): string {
    const root = tsProject({ 'tsconfig.json': TEST_TSCONFIG, 'src/api.ts': API, 'test/m.test.ts': test });
    const result = refactorRaw(root, '--apply', 'rename', '--file', 'src/api.ts', '--new-name', 'client');
    expect(result.code).toBe(0);
    return files(root)['test/m.test.ts'] ?? '';
  }

  const forms = RECEIVERS.flatMap(({ name, module }) => [
    [`${name} imported`, `import { ${name} } from '${module}';\n\n`, name],
    [`${name} imported under an alias`, `import { ${name} as r } from '${module}';\n\n`, 'r'],
    [`${name} as the undeclared global`, '', name],
  ]);

  it.each(forms)('rewrites the module path of every listed call on %s, each in its own extension style', (_, prelude, receiver) => {
    const calls = MODULE_CALLS.map(({ call }) => `${receiver}.${call}('../src/api');\n${receiver}.${call}('../src/api.js');\n`).join('');
    const test = `${prelude}${calls}\nexport {};\n`;
    expect(renamedTest(test)).toBe(test.replaceAll('/src/api', '/src/client'));
  });

  it.each([
    ['a local of the receiver\'s name', "export function f(): string {\n  const vi = { mock: (p: string): string => p };\n  return vi.mock('../src/api');\n}\n"],
    ['a namespace import\'s member', "import * as vitest from 'vitest';\n\nvitest.vi.mock('../src/api');\n"],
    ['a call the facts do not list', "import { vi } from 'vitest';\n\nvi.spyOn('../src/api', 'get');\n"],
    ['an import of the receiver from another module', "import { vi } from './fake.js';\n\nvi.mock('../src/api');\n"],
    ['a path naming another module', "import { vi } from 'vitest';\n\nvi.mock('../src/apix');\n"],
  ])('leaves the path of %s', (_, test) => {
    expect(renamedTest(test)).toBe(test);
  });

  it('rewrites a paths-mapped mock path as an import of the same specifier', () => {
    const tsconfig = '{\n  "compilerOptions": {"strict": true, "noEmit": true, "module": "esnext", "moduleResolution": "bundler", "paths": {"@/*": ["./src/*"]}},\n  "include": ["src", "test"]\n}\n';
    const test = "import { vi } from 'vitest';\nimport { get } from '@/api';\n\nvi.mock('@/api');\n\nexport const shown = get();\n";
    const root = tsProject({ 'tsconfig.json': tsconfig, 'src/api.ts': API, 'test/m.test.ts': test });
    expect(refactorRaw(root, '--apply', 'rename', '--file', 'src/api.ts', '--new-name', 'client').code).toBe(0);
    expect(files(root)['test/m.test.ts']).toBe(test.replaceAll('@/api', '@/client'));
  });

  it('move-module rewrites a mock path naming the moved file', () => {
    const test = "import { vi } from 'vitest';\n\nvi.mock('../src/api');\n";
    const root = tsProject({ 'tsconfig.json': TEST_TSCONFIG, 'src/api.ts': API, 'src/lib/keep.ts': 'export {};\n', 'test/m.test.ts': test });
    expect(refactorRaw(root, '--apply', 'move-module', '--module', 'src/api.ts', '--dest', 'src/lib').code).toBe(0);
    expect(files(root)['test/m.test.ts']).toBe(test.replace('../src/api', '../src/lib/api'));
  });
});

describe('dr-mock-lint reads the factory-taking calls from the shared facts', () => {
  const lint = (root: string, ...argv: string[]): Run => run(root, 'dr-mock-lint', argv);
  const project = (test: string): string => tsProject({ 'tsconfig.json': TEST_TSCONFIG, 'src/api.ts': API, 'test/m.test.ts': test });

  it.each(MODULE_CALLS.filter((c) => c.factory !== undefined).map(({ call }) => call))('an untyped factory of vi.%s is a finding', (call) => {
    const root = project(`import { vi } from 'vitest';\n\nvi.${call}('../src/api', () => ({ get: () => 2 }));\n`);
    expect(lint(root, 'test/m.test.ts')).toEqual({ code: 1, out: `${message('mock-lint.module', { path: 'test/m.test.ts', line: 3, call: `vi.${call}` })}\n`, err: '' });
  });

  it.each(MODULE_CALLS.filter((c) => c.factory === undefined).map(({ call }) => call))('a second argument of vi.%s is no factory', (call) => {
    const root = project(`import { vi } from 'vitest';\n\nvi.${call}('../src/api', () => ({ get: () => 2 }));\n`);
    expect(lint(root, 'test/m.test.ts')).toEqual({ code: 0, out: '', err: '' });
  });
});
