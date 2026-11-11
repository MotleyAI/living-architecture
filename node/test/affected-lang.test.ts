// TypeScript dependency edges for `la-affected-tests`, through src/lang/index.ts:
// dependencyEdges(repoRoot, files, deleted): [importer, target][] as repo-relative POSIX paths.
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { dependencyEdges } from '../src/lang/index.js';
import { runtimeSpecifiers } from '../src/lang/specifiers.js';
import { ts } from '../src/lang/ts.js';

const roots: string[] = [];
afterAll(() => roots.forEach((root) => rmSync(root, { recursive: true, force: true })));

const BUNDLER = JSON.stringify({ compilerOptions: { module: 'esnext', moduleResolution: 'bundler', jsx: 'react-jsx' } });

/** Targets of `importer` in a temp repo of `files`; graph files are the source files among them. */
function targets(files: Record<string, string>, importer: string, deleted: string[] = [], links: Record<string, string> = {}): string[] {
  const root = mkdtempSync(join(tmpdir(), 'la-edges-'));
  roots.push(root);
  for (const [rel, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, rel)), { recursive: true });
    writeFileSync(join(root, rel), text);
  }
  for (const [link, target] of Object.entries(links)) {
    mkdirSync(dirname(join(root, link)), { recursive: true });
    symlinkSync(target, join(root, link));
  }
  const graph = Object.keys(files).filter((rel) => /\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$/.test(rel)).sort();
  const edges = dependencyEdges(root, graph, [...deleted].sort());
  return [...new Set(edges.filter(([src]) => src === importer).map(([, dst]) => dst))].sort();
}

describe('every specifier form counts', () => {
  it.each([
    ['static import', "import { b } from '../src/b';\n"],
    ['side-effect import', "import '../src/b';\n"],
    ['export from', "export { b } from '../src/b';\n"],
    ['export star', "export * from '../src/b';\n"],
    ['dynamic import', "export const m = import('../src/b');\n"],
    ['import equals require', "import b = require('../src/b');\nexport { b };\n"],
    ['literal require', "const b = require('../src/b');\nexport { b };\n"],
    ['import type', "import type { B } from '../src/b';\nexport type T = B;\n"],
    ['export type', "export type { B } from '../src/b';\n"],
    ['type-only specifier', "import { type B } from '../src/b';\nexport type T = B;\n"],
    ['import type node', "export type T = import('../src/b').B;\n"],
    ['reference path', '/// <reference path="../src/b.ts" />\nexport {};\n'],
  ])('%s', (_name, source) => {
    const files = { 'tsconfig.json': BUNDLER, 'src/b.ts': 'export const b = 1;\nexport type B = 1;\n', 'test/a.test.ts': source };
    expect(targets(files, 'test/a.test.ts')).toEqual(['src/b.ts']);
  });

  it('runtimeSpecifiers still leaves type-only forms out', () => {
    const file = ts().createSourceFile('a.ts', "import type { B } from './b';\nexport type { C } from './c';\n", ts().ScriptTarget.Latest, true);
    expect(runtimeSpecifiers(file)).toEqual([]);
  });
});

describe('resolution under the nearest tsconfig', () => {
  it('a paths alias', () => {
    const tsconfig = JSON.stringify({ compilerOptions: { module: 'esnext', moduleResolution: 'bundler', paths: { '@lib/*': ['./src/lib/*'] } } });
    const files = { 'tsconfig.json': tsconfig, 'src/lib/util.ts': 'export const u = 1;\n', 'test/a.test.ts': "import { u } from '@lib/util';\n" };
    expect(targets(files, 'test/a.test.ts')).toEqual(['src/lib/util.ts']);
  });

  it('baseUrl', () => {
    const tsconfig = JSON.stringify({ compilerOptions: { module: 'esnext', moduleResolution: 'bundler', baseUrl: '.' } });
    const files = { 'tsconfig.json': tsconfig, 'src/lib/util.ts': 'export const u = 1;\n', 'test/a.test.ts': "import { u } from 'src/lib/util';\n" };
    expect(targets(files, 'test/a.test.ts')).toEqual(['src/lib/util.ts']);
  });

  it('project references: the referenced project owning the file', () => {
    const root = JSON.stringify({ files: [], references: [{ path: './tsconfig.app.json' }, { path: './tsconfig.test.json' }] });
    const app = JSON.stringify({ compilerOptions: { composite: true, module: 'esnext', moduleResolution: 'bundler' }, include: ['src'] });
    const test = JSON.stringify({
      compilerOptions: { composite: true, module: 'esnext', moduleResolution: 'bundler', paths: { '@app/*': ['./src/*'] } },
      include: ['test'],
    });
    const files = {
      'tsconfig.json': root,
      'tsconfig.app.json': app,
      'tsconfig.test.json': test,
      'src/u.ts': 'export const u = 1;\n',
      'test/a.test.ts': "import { u } from '@app/u';\n",
    };
    expect(targets(files, 'test/a.test.ts')).toEqual(['src/u.ts']);
  });

  it('nested configs with different paths', () => {
    const config = JSON.stringify({ compilerOptions: { module: 'esnext', moduleResolution: 'bundler', paths: { '@x/*': ['./src/*'] } } });
    const files = {
      'packages/a/tsconfig.json': config,
      'packages/a/src/u.ts': 'export const u = 1;\n',
      'packages/b/tsconfig.json': config,
      'packages/b/src/u.ts': 'export const u = 2;\n',
      'packages/b/test/u.test.ts': "import { u } from '@x/u';\n",
    };
    expect(targets(files, 'packages/b/test/u.test.ts')).toEqual(['packages/b/src/u.ts']);
  });

  it('a test excluded from its tsconfig still resolves under it', () => {
    const tsconfig = JSON.stringify({ compilerOptions: { module: 'esnext', moduleResolution: 'bundler', paths: { '@lib/*': ['./src/lib/*'] } }, include: ['src'] });
    const files = { 'tsconfig.json': tsconfig, 'src/lib/util.ts': 'export const u = 1;\n', 'test/a.test.ts': "import { u } from '@lib/util';\n" };
    expect(targets(files, 'test/a.test.ts')).toEqual(['src/lib/util.ts']);
  });

  it('NodeNext .js specifiers resolve to .ts sources', () => {
    const tsconfig = JSON.stringify({ compilerOptions: { module: 'nodenext', moduleResolution: 'nodenext' } });
    const files = {
      'tsconfig.json': tsconfig,
      'package.json': '{"type": "module"}\n',
      'src/b.ts': 'export const b = 1;\n',
      'src/a.ts': "import { b } from './b.js';\nexport const a = b;\n",
    };
    expect(targets(files, 'src/a.ts')).toEqual(['src/b.ts']);
  });

  it('JSX sources', () => {
    const files = {
      'tsconfig.json': BUNDLER,
      'src/b.ts': 'export const b = 1;\n',
      'src/c.tsx': "import { b } from './b';\nexport const C = () => <div>{b}</div>;\n",
      'test/c.test.tsx': "import { C } from '../src/c';\nexport const t = <C />;\n",
    };
    expect([targets(files, 'test/c.test.tsx'), targets(files, 'src/c.tsx')]).toEqual([['src/c.tsx'], ['src/b.ts']]);
  });

  it('a JSON module', () => {
    const tsconfig = JSON.stringify({ compilerOptions: { module: 'esnext', moduleResolution: 'bundler', resolveJsonModule: true } });
    const files = { 'tsconfig.json': tsconfig, 'src/data.json': '{}\n', 'test/a.test.ts': "import data from '../src/data.json';\nexport { data };\n" };
    expect(targets(files, 'test/a.test.ts')).toEqual(['src/data.json']);
  });

  it('without any tsconfig', () => {
    const files = { 'src/b.ts': 'export const b = 1;\n', 'test/a.test.ts': "import { b } from '../src/b';\n" };
    expect(targets(files, 'test/a.test.ts')).toEqual(['src/b.ts']);
  });
});

describe('deleted targets', () => {
  it('behind a paths alias', () => {
    const tsconfig = JSON.stringify({ compilerOptions: { module: 'esnext', moduleResolution: 'bundler', paths: { '@lib/*': ['./src/lib/*'] } } });
    const files = { 'tsconfig.json': tsconfig, 'src/lib/kept.ts': '', 'test/a.test.ts': "import { g } from '@lib/gone';\n" };
    expect(targets(files, 'test/a.test.ts', ['src/lib/gone.ts'])).toEqual(['src/lib/gone.ts']);
  });

  it('a deleted directory index', () => {
    const files = { 'tsconfig.json': BUNDLER, 'test/a.test.ts': "import { f } from '../src/feature';\n" };
    expect(targets(files, 'test/a.test.ts', ['src/feature/index.ts'])).toEqual(['src/feature/index.ts']);
  });

  it('a deleted file named with a .js specifier', () => {
    const files = { 'tsconfig.json': BUNDLER, 'src/a.ts': "import { b } from './b.js';\nexport const a = b;\n" };
    expect(targets(files, 'src/a.ts', ['src/b.ts'])).toEqual(['src/b.ts']);
  });
});

describe('the extension fallback for a relative specifier the resolver rejects', () => {
  const NODENEXT = { 'tsconfig.json': JSON.stringify({ compilerOptions: { module: 'nodenext', moduleResolution: 'nodenext' } }), 'package.json': '{"type": "module"}\n' };

  it.each([
    ['an extensionless specifier gets a source extension', "import { b } from './b';\n", 'src/b.ts'],
    ['a foreign source extension is stripped and replaced', "import { b } from './b.mjs';\n", 'src/b.ts'],
    ['a directory specifier falls back to its index', "import { f } from './feature';\n", 'src/feature/index.ts'],
  ])('%s', (_name, source, target) => {
    const files = { ...NODENEXT, 'src/b.ts': 'export const b = 1;\n', 'src/feature/index.ts': 'export const f = 1;\n', 'src/a.ts': source };
    expect(targets(files, 'src/a.ts')).toEqual([target]);
  });
});

describe('edge targets', () => {
  it('a workspace package symlinked under node_modules resolves to its in-repo source', () => {
    const files = {
      'tsconfig.json': BUNDLER,
      'packages/lib/package.json': '{"name": "@ws/lib", "main": "src/index.ts", "types": "src/index.ts"}\n',
      'packages/lib/src/index.ts': 'export const l = 1;\n',
      'test/a.test.ts': "import { l } from '@ws/lib';\n",
    };
    expect(targets(files, 'test/a.test.ts', [], { 'node_modules/@ws/lib': '../../packages/lib' })).toEqual(['packages/lib/src/index.ts']);
  });

  it('an installed dependency is no edge', () => {
    const files = {
      'tsconfig.json': BUNDLER,
      'node_modules/dep/package.json': '{"name": "dep", "main": "index.js", "types": "index.d.ts"}\n',
      'node_modules/dep/index.js': 'exports.d = 1;\n',
      'node_modules/dep/index.d.ts': 'export declare const d: number;\n',
      'test/a.test.ts': "import { d } from 'dep';\n",
    };
    expect(targets(files, 'test/a.test.ts')).toEqual([]);
  });

  it('an import cycle yields both edges', () => {
    const files = {
      'tsconfig.json': BUNDLER,
      'src/a.ts': "import { b } from './b';\nexport const a = 1;\nexport const x = b;\n",
      'src/b.ts': "import { a } from './a';\nexport const b = 1;\nexport const y = a;\n",
    };
    expect([targets(files, 'src/a.ts'), targets(files, 'src/b.ts')]).toEqual([['src/b.ts'], ['src/a.ts']]);
  });
});
