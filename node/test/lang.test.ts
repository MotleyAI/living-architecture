// The TypeScript adapter, through src/lang/index.ts, on the conformance cases' repos and on small inline repos.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import ts from 'typescript';
import { afterAll, describe, expect, it } from 'vitest';
import { LangError, moduleImports, topLevelUnits, unitStatus, type TsLayout } from '../src/lang/index.js';
import { runtimeSpecifiers } from '../src/lang/specifiers.js';
import { cleanup, materialize } from './lang-fixtures.js';

const layouts: TsLayout[] = [];
afterAll(() => layouts.forEach(cleanup));

function repo(caseName: string): TsLayout {
  const layout = materialize(caseName);
  layouts.push(layout);
  return layout;
}

/** module -> targets, for sources with at least one target, minus the fixture's root barrel. */
function edges(layout: TsLayout): Record<string, string[]> {
  return Object.fromEntries(
    moduleImports(layout)
      .filter((m) => m.targets.length > 0 && m.module !== layout.rootPackage)
      .map((m) => [m.module, m.targets]),
  );
}

const FIXTURE_EDGES = {
  'src/api': ['src/store/db'],
  'src/api/handlers': ['src/core/service'],
  'src/core/service': ['src/store/db', 'src/util'],
  'src/old': ['src/util'],
};

describe('units', () => {
  it('a directory, a module file and a missing unit', () => {
    const layout = repo('arch-check-ts-ok');
    expect(['src/api', 'src/util', 'src/gone'].map((u) => unitStatus(layout, u).status)).toEqual([
      'present',
      'present',
      'missing',
    ]);
  });

  it('one module file of any source extension', () => {
    const layout = repo('arch-check-ts-unit-module-file');
    const units = ['src/util', 'src/view', 'src/esm', 'src/cjs', 'src/plain', 'src/comp', 'src/shim'];
    expect(units.map((u) => unitStatus(layout, u).status)).toEqual(units.map(() => 'present'));
  });

  it('a file and a directory, or two extensions, are ambiguous with sorted candidates', () => {
    const layout = repo('arch-check-ts-unit-ambiguous-declared');
    expect(unitStatus(layout, 'src/util')).toEqual({ status: 'ambiguous', candidates: ['src/util.ts', 'src/util/'] });
    expect(unitStatus(layout, 'src/dup')).toEqual({ status: 'ambiguous', candidates: ['src/dup.js', 'src/dup.ts'] });
  });

  it('derived units are ambiguous the same way', () => {
    const layout = repo('arch-check-ts-unit-ambiguous-derived');
    expect(unitStatus(layout, 'src/api/handlers').candidates).toEqual(['src/api/handlers.ts', 'src/api/handlers/']);
    expect(unitStatus(layout, 'src/core/fmt').candidates).toEqual(['src/core/fmt.ts', 'src/core/fmt.tsx']);
  });

  it('invisible files make no unit', () => {
    const layout = repo('arch-check-ts-units-missing');
    expect(unitStatus(layout, 'src/daemon/pty').status).toBe('missing');
    expect(unitStatus(layout, 'src/daemon').status).toBe('present');
  });

  it('test globs, *.d.ts and node_modules are neither units nor sources', () => {
    const layout = repo('arch-check-ts-invisible-files');
    expect(unitStatus(layout, 'src/a').status).toBe('missing');
    expect(topLevelUnits(layout)).toEqual(['src/api', 'src/core', 'src/old', 'src/store', 'src/util']);
    expect(moduleImports(layout).map((m) => m.module)).not.toContain('src/store/db.test');
    expect(edges(layout)).toEqual(FIXTURE_EDGES);
  });

  it('top-level units: files and dirs with a visible source, not the root barrel', () => {
    expect(topLevelUnits(repo('arch-check-ts-unclaimed-top-level'))).toEqual([
      'src/api',
      'src/core',
      'src/extra',
      'src/old',
      'src/store',
      'src/tools',
      'src/util',
    ]);
    expect(topLevelUnits(repo('arch-check-ts-facts'))).toContain('src/dup');
  });

  it('the facts case: every declared and derived unit status', () => {
    const layout = repo('arch-check-ts-facts');
    const units = ['src/api', 'src/core', 'src/util', 'src/gone', 'src/dup', 'src/store', 'src/old', 'src/api/handlers', 'src/core/fmt'];
    expect(units.map((u) => unitStatus(layout, u).status)).toEqual([
      'present', 'present', 'present', 'missing', 'ambiguous', 'present', 'present', 'present', 'missing',
    ]);
    expect(unitStatus(layout, 'src/dup').candidates).toEqual(['src/dup.ts', 'src/dup/']);
  });

  it('symlinks are followed while they stay under source_root; a cycle is walked once', () => {
    const layout = repo('arch-check-ts-symlinks');
    expect(topLevelUnits(layout)).toEqual(['src/core', 'src/cyc', 'src/f', 'src/linked']);
    expect(['src/linked', 'src/f', 'src/esc', 'src/cyc'].map((u) => unitStatus(layout, u).status)).toEqual([
      'present',
      'present',
      'missing',
      'present',
    ]);
    expect(moduleImports(layout).map((m) => m.module)).toEqual(['src/core/a', 'src/cyc/c', 'src/f', 'src/linked/x']);
  });
});

describe('import edges', () => {
  it('the fixture: index barrels as directory module ids, type-only imports excluded', () => {
    expect(edges(repo('arch-check-ts-ok'))).toEqual(FIXTURE_EDGES);
  });

  it('every static form counts', () => {
    const forms = ['dflt', 'dflttype', 'emptyexport', 'emptyimport', 'importeq', 'mixed', 'mixedexport', 'named',
      'nsimport', 'reexport', 'sideeffect', 'starexport', 'starns', 'typeuse'];
    expect(edges(repo('arch-check-ts-edges-static-forms'))).toEqual(
      Object.fromEntries(forms.map((f) => [`src/a/${f}`, [`src/${f}/m`]])),
    );
  });

  it('literal import() and require() count, non-literal and member calls do not', () => {
    expect(edges(repo('arch-check-ts-edges-dynamic-forms'))).toEqual({
      'src/a/dyn': ['src/dyn/m'],
      'src/a/req': ['src/req/m'],
      'src/c/z': ['src/cjs/m'],
    });
  });

  it('type-only forms never count', () => {
    expect(edges(repo('arch-check-ts-edges-type-only'))).toEqual({ 'src/a/control': ['src/c/z'] });
  });

  it('externals, targets outside root_package and the root barrel give no attributable target', () => {
    expect(edges(repo('arch-check-ts-externals'))).toEqual({ 'src/a/x': ['src', 'src/b/y'] });
  });

  it('unresolved relative specifiers are lexical unless they leave root_package', () => {
    expect(edges(repo('arch-check-ts-unresolved-relative'))).toEqual({
      'src/a/x': ['src/b/missing', 'src/c/q', 'src/d/logo.svg', 'src/e/s', 'src/f/u'],
    });
  });

  it('JS units and targets resolve with allowJs off', () => {
    expect(edges(repo('arch-check-ts-allowjs-off'))).toEqual({ 'src/a/x': ['src/b/y'], 'src/b/y': ['src/c'] });
  });
});

describe('resolution', () => {
  it('bundler by default: .js/.mjs name TS sources, extensionless and directory imports resolve', () => {
    expect(edges(repo('arch-check-ts-resolve-bundler-default'))).toEqual({
      'src/a/x': ['src/b/y', 'src/c/z', 'src/d', 'src/e', 'src/f'],
    });
  });

  it('nodenext ESM leaves extensionless and directory imports unresolved', () => {
    expect(edges(repo('arch-check-ts-resolve-nodenext'))).toEqual({
      'src/a/x': ['src/b/y', 'src/c/z', 'src/d', 'src/e/index', 'src/f'],
    });
  });

  it('node16 resolves per file format', () => {
    expect(edges(repo('arch-check-ts-resolve-node16'))).toEqual({
      'src/a/c': ['src/c'],
      'src/a/m': ['src/d/index', 'src/e/k'],
      'src/a/x': ['src/b'],
    });
  });

  it('paths and baseUrl resolve internally; an alias resolving nowhere is external', () => {
    expect(edges(repo('arch-check-ts-resolve-paths-baseurl'))).toEqual({ 'src/a/x': ['src/b/y', 'src/c/z'] });
  });

  it.each([
    ['arch-check-ts-tsconfig-key', 'the section key'],
    ['arch-check-ts-tsconfig-nearest', 'the nearest tsconfig.json'],
    ['arch-check-ts-tsconfig-extends', 'extends'],
  ])('%s: %s selects the options', (caseName) => {
    expect(edges(repo(caseName))).toEqual({ 'src/a/x': ['src/b/y'] });
  });

  it('source_root: prefix-free module ids, nearest tsconfig searched from under it', () => {
    expect(edges(repo('arch-check-ts-source-root'))).toEqual({ 'src/a/x': ['src/b/y', 'src/c/z'] });
  });

  it('project references map declaration outputs to sources, built or not', () => {
    expect(edges(repo('arch-check-ts-project-references'))).toEqual({
      'src/app/x': ['src/lib', 'src/lib/cjs', 'src/lib/esm', 'src/lib/extra', 'src/lib2'],
    });
  });

  it('a file resolves with its first owning project in depth-first order, else the root config', () => {
    expect(edges(repo('arch-check-ts-project-references-ownership'))).toEqual({
      'src/a/x': ['src/b/y'],
      'src/d/w': ['src/e/y'],
      'src/shared/s': ['src/c/y'],
    });
  });

  it('a tsconfig holding JavaScript is a setup error naming it', () => {
    const layout = repo('arch-check-ts-tsconfig-never-executed');
    expect(() => moduleImports(layout)).toThrow(LangError);
    expect(() => moduleImports(layout)).toThrow(/config\/tsconfig\.js/);
  });
});

describe('inline repos', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-lang-inline-'));
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));
  let count = 0;

  function inline(files: Record<string, string>, extra: Partial<TsLayout> = {}): TsLayout {
    const root = join(tmp, String(count++));
    for (const [rel, text] of Object.entries(files)) {
      mkdirSync(dirname(join(root, rel)), { recursive: true });
      writeFileSync(join(root, rel), text);
    }
    return { repoRoot: root, sourceRoot: root, rootPackage: 'src', tsconfig: null, ...extra };
  }

  it('a missing tsconfig key is a setup error naming it', () => {
    const layout = inline({ 'src/a.ts': '' }, { tsconfig: 'nope.json' });
    expect(() => moduleImports(layout)).toThrow(/nope\.json/);
  });

  it('a reference cycle is tolerated', () => {
    const layout = inline({
      'tsconfig.json': '{"files": [], "references": [{"path": "./a.json"}]}',
      'a.json': '{"compilerOptions": {"composite": true}, "include": ["src/**/*"], "references": [{"path": "./tsconfig.json"}]}',
      'src/a/x.ts': "import '../b/y';",
      'src/b/y.ts': '',
    });
    expect(edges(layout)).toEqual({ 'src/a/x': ['src/b/y'] });
  });

  it('a target resolved into node_modules under root_package is external', () => {
    const layout = inline({
      'src/a/x.ts': "import 'dep';",
      'src/node_modules/dep/index.js': '',
      'src/node_modules/dep/package.json': '{"name": "dep", "main": "index.js"}',
    });
    expect(edges(layout)).toEqual({});
  });

  it('a resolved declaration file is unattributed', () => {
    const layout = inline({ 'src/a/x.ts': "import '../b/y';", 'src/b/y.d.ts': 'export {};' });
    expect(edges(layout)).toEqual({});
  });
});

describe('runtimeSpecifiers', () => {
  const specs = (text: string): string[] =>
    runtimeSpecifiers(ts.createSourceFile('x.ts', text, ts.ScriptTarget.Latest, true)).map((s) => s.text);

  it.each([
    ["import type { T } from 'a';", []],
    ["import { type T, type U } from 'a';", []],
    ["import { type T, v } from 'a';", ['a']],
    ["import {} from 'a';", ['a']],
    ["import d, { type T } from 'a';", ['a']],
    ["import * as ns from 'a';", ['a']],
    ["import 'a';", ['a']],
    ["export type { T } from 'a';", []],
    ["export { type T } from 'a';", []],
    ["export type * from 'a';", []],
    ["export * from 'a';", ['a']],
    ["export * as ns from 'a';", ['a']],
    ["export {} from 'a';", ['a']],
    ["export { v } from 'a';", ['a']],
    ["import type x = require('a');", []],
    ["import x = require('a');", ['a']],
    ["let t: typeof import('a');", []],
    ["const m = import('a');", ['a']],
    ["const m = require('a');", ['a']],
    ['const m = import(name);', []],
    ["const m = o.require('a');", []],
    ["/// <reference path='a.ts' />\nexport {};", []],
  ])('%s', (text, expected) => {
    expect(specs(text)).toEqual(expected);
  });
});
