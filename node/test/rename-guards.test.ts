// The TS rename's pure pieces: `--keep` / `--with` sites and the `--docs` mention rules.
import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type * as TS from 'typescript';
import { describe, expect, it } from 'vitest';
import { ts } from '../src/lang/index.js';
import { codeMarked, mentions, qualified, sourceRegions } from '../src/refactor/mentions.js';
import { run, tempRepo } from './cli-run.js';
import { memberDeclarations } from '../src/refactor/members.js';
import { Site } from '../src/refactor/sites.js';

describe('Site', () => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'la-sites-')));
  mkdirSync(join(root, 'tests', 'compat'), { recursive: true });
  for (const file of ['tests/compat/old.ts', 'tests/compatible.ts', 'tests/shim.ts']) writeFileSync(join(root, file), '');

  it('matches a directory by whole path components', () => {
    const site = Site.parse('tests/compat', root, root);
    expect(site.covers('tests/compat/old.ts', 1)).toBe(true);
    expect(site.covers('tests/compatible.ts', 1)).toBe(false);
  });

  it('matches a line of a file, normalized', () => {
    const site = Site.parse('./tests/../tests/shim.ts:4', root, root);
    expect([site.covers('tests/shim.ts', 4), site.covers('tests/shim.ts', 5)]).toEqual([true, false]);
  });

  it('matches nothing for a missing path or one outside the project', () => {
    expect(Site.parse('tests/missing.ts', root, root).covers('tests/missing.ts', 1)).toBe(false);
    expect(Site.parse('..', root, root).parts).toBeNull();
  });
});

describe('mentions', () => {
  const owners = [{ path: ['src', 'engine', 'Engine'], member: true }];
  const source = (text: string) => ts().createSourceFile('a.ts', text, ts().ScriptTarget.Latest, true);
  const found = (text: string) => mentions(text, 'saveModel', sourceRegions(source(text)));

  it('finds comment, string and template text, not code or longer words', () => {
    const text = "// saveModel\nconst a = 'saveModel'; const b = `x ${saveModel} saveModel`; saveModelX();\n";
    expect(found(text).map((m) => m.where)).toEqual(['comment', 'string', 'string']);
  });

  it('qualifies by owner, module suffix and collisions', () => {
    const at = (text: string) => text.lastIndexOf('saveModel');
    for (const text of ['Engine.saveModel', 'Engine#saveModel', 'engine.Engine.saveModel', 'src.engine.Engine#saveModel']) {
      expect(qualified(text, at(text), owners, [])).toBe(true);
    }
    expect(qualified('other.Engine.saveModel', at('other.Engine.saveModel'), owners, [])).toBe(false);
    expect(qualified('Engine.saveModel', 7, owners, [['lib', 'Engine']])).toBe(false);
    expect(qualified('e.saveModel', 2, owners, [])).toBe(false);
    const libEngine = [['lib', 'engine', 'Engine']];
    expect(qualified('engine.Engine.saveModel', at('engine.Engine.saveModel'), owners, libEngine)).toBe(false);
    expect(qualified('src.engine.Engine.saveModel', at('src.engine.Engine.saveModel'), owners, libEngine)).toBe(true);
  });

  it('marks backticks, links and a string opening with the name', () => {
    const marked = (text: string) => found(text).map((m) => codeMarked(text, m));
    expect(marked('// `saveModel` and `saveModel()` and {@link saveModel} and saveModel\n')).toEqual([true, true, true, false]);
    expect(marked("const a = 'saveModel: x'; const b = 'x saveModel: y';\n")).toEqual([true, false]);
    expect(marked('const t = `saveModel: ${1} saveModel: `;\n')).toEqual([true, false]);
  });
});

describe('file universe', () => {
  it('a member rename refuses on exactly what dr-compliance reports over the project', () => {
    const loose = 'export function g(o: any): number {\n  return o.getModel();\n}\n';
    const root = tempRepo({
      'tsconfig.json': '{"compilerOptions": {"strict": true}, "include": ["src"]}\n',
      'src/store.ts': 'export class Store {\n  getModel(): number {\n    return 1;\n  }\n}\n',
      'src/loose.ts': loose,
      'scripts/tool.ts': loose,
      'build/z.ts': loose,
      'node_modules/dep/x.ts': loose,
      'src/types.d.ts': 'declare function h(o: any): void;\n',
    });
    const renamed = run(root, 'dr-refactor', ['rename', '--file', 'src/store.ts', '--name', 'getModel', '--new-name', 'fetchModel']);
    expect(renamed.code).toBe(1);
    const lines = renamed.err.trimEnd().split('\n');
    expect(lines.pop()).toMatch(/^3 blind spot/u);
    const compliance = run(root, 'dr-compliance', ['--select', 'attr-blindspot', '--attr', 'getModel', '.']);
    expect(compliance.code).toBe(1);
    expect(lines).toEqual(compliance.out.trimEnd().split('\n'));
  });
});

describe('exact-OLD literals', () => {
  it('a function rename lists none', () => {
    const root = tempRepo({
      'tsconfig.json': '{"compilerOptions": {"strict": true}, "include": ["src"]}\n',
      'src/funcs.ts': "export function saveModel(): void {}\nexport const NAME = 'saveModel';\n",
    });
    const renamed = run(root, 'dr-refactor', ['rename', '--file', 'src/funcs.ts', '--name', 'saveModel', '--new-name', 'storeModel']);
    expect([renamed.code, renamed.err]).toEqual([0, '']);
  });
});

describe('memberDeclarations', () => {
  const text = [
    "const KEY = 'saveModel';",
    'export class Base { saveModel(): void {} }',
    'export class Sub extends Base {}',
    'export class Param { constructor(public saveModel: number) {} }',
    "export class Quoted { 'saveModel'(): void {} }",
    'export class Computed { [KEY](): void {} }',
    'export class Stat { static saveModel(): void {} }',
    'export interface Merged { a: number }',
    'export interface Merged { saveModel(): void }',
    'export type Lit = { saveModel: () => void };',
    'export const obj = { saveModel() {} };',
    'export class Acc { get saveModel(): number { return 1; } }',
    'export class Priv { #saveModel = 1; }',
    '',
  ].join('\n');
  const dir = realpathSync(mkdtempSync(join(tmpdir(), 'la-members-')));
  const file = join(dir, 'a.ts');
  writeFileSync(file, text);
  const program = ts().createProgram([file], { strict: true, noEmit: true });
  const source = program.getSourceFile(file) as TS.SourceFile;
  const found = memberDeclarations(program.getTypeChecker(), source, 'saveModel', file);

  it('finds every own member declaration of classes, interfaces and type literals from the checker', () => {
    expect(found.map((d) => [d.owner, d.line, d.computed])).toEqual([
      ['Base', 2, false],
      ['Param', 4, false],
      ['Quoted', 5, false],
      ['Computed', 6, true],
      ['Stat', 7, false],
      ['Merged', 9, false],
      ['Lit', 10, false],
      ['Acc', 12, false],
    ]);
  });

  it('starts each at its name, or a computed name at its bracket', () => {
    const at = (d: { start: number }) => text.slice(d.start, d.start + 9);
    expect(found.filter((d) => !d.computed).every((d) => at(d) === 'saveModel')).toBe(true);
    expect(found.filter((d) => d.computed).map((d) => text.slice(d.start, d.start + 5))).toEqual(['[KEY]']);
  });
});

describe('--docs module paths', () => {
  it('a qualifier spelled with the full project-relative path is rewritten', () => {
    const root = tempRepo({
      'tsconfig.json': '{"compilerOptions": {"strict": true}, "include": ["src"]}\n',
      'src/pkg/engine.ts': 'export class Engine {\n  saveModel(): void {}\n}\n// see src.pkg.engine.Engine.saveModel and pkg.engine.Engine.saveModel\n',
    });
    const renamed = run(root, 'dr-refactor', ['rename', '--file', 'src/pkg/engine.ts', '--name', 'saveModel', '--new-name', 'storeModel', '--docs']);
    expect([renamed.code, renamed.err]).toEqual([0, '']);
    expect(renamed.out).toContain('+// see src.pkg.engine.Engine.storeModel and pkg.engine.Engine.storeModel');
  });
});
