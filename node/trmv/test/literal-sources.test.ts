// The literal sources of a name: the plain string literals a supported binding gives it, in project sources only.
import { join, relative } from 'node:path';
import type * as TS from 'typescript';
import { beforeAll, describe, expect, it } from 'vitest';
import { byCodePoint } from '../src/contract/index.js';
import { posix, ts } from '../src/lang/index.js';
import { literalSources } from '../src/refactor/literal-sources.js';
import { walk } from '../src/refactor/members.js';
import { Refactor } from '../src/refactor/session.js';
import { tsProject } from './refactor-project.js';

const DS = `export class Ds {
  columns: string[] = [];
  name = '';
}

export type Kind = 'formula' | 'sql';

export function take(k: Kind): Kind {
  return k;
}
`;
const HEAD = "import { Ds, take } from './ds';\n\nexport const d = new Ds();\nexport const used = take;\n";

const FILES: Record<string, string> = {
  'src/ds.ts': DS,
  'src/const.ts': `${HEAD}const v = 'formula';\ntake(v);\n`,
  'src/let-once.ts': `${HEAD}let s = 'columns';\nReflect.get(d, s);\n`,
  'src/static.ts': `${HEAD}export class K {\n  static readonly FORMULA = 'formula';\n}\ntake(K.FORMULA);\n`,
  'src/for-literal.ts': `${HEAD}for (const s of ['columns', 'name'] as const) Reflect.get(d, s);\n`,
  'src/for-name.ts': `${HEAD}const SECTIONS = ['columns', 'name'] as const;\nfor (const s of SECTIONS) Reflect.get(d, s);\n`,
  'src/callback-literal.ts': `${HEAD}(['columns', 'name'] as const).forEach((s) => {\n  void d[s];\n});\n`,
  'src/callback-name.ts': `${HEAD}const SECTIONS = ['columns'] as const;\nexport const read = SECTIONS.map((s) => d[s]);\n`,
  'src/parameter.ts': `${HEAD}export function f(s: 'columns'): unknown {\n  return d[s];\n}\nf('columns');\n`,
  'src/conditional.ts': `${HEAD}export function f(c: boolean): void {\n  const v = c ? 'formula' : 'sql';\n  take(v);\n}\n`,
  'src/computed.ts': `${HEAD}const s = 'col' + 'umns';\nReflect.get(d, s);\n`,
  'src/let-twice.ts': `${HEAD}let s = 'name';\ns = 'columns';\nReflect.get(d, s);\n`,
  'src/destructured-array.ts': `${HEAD}const [s] = ['columns'] as const;\nvoid d[s];\n`,
  'src/destructured-object.ts': `${HEAD}const { s } = { s: 'columns' } as const;\nvoid d[s];\n`,
  'src/plain-array.ts': `${HEAD}const NAMES = ['columns'];\nfor (const s of NAMES) Reflect.get(d, s);\n`,
  'src/plain-array-callback.ts': `${HEAD}const NAMES = ['columns'];\nNAMES.forEach((s) => Reflect.get(d, s));\n`,
  'src/decl.d.ts': "export declare const DEFAULT = 'formula';\n",
  'src/from-declaration.ts': `${HEAD}import { DEFAULT } from './decl';\ntake(DEFAULT);\n`,
  'node_modules/dep/package.json': '{"name": "dep", "version": "1.0.0", "main": "index.ts"}\n',
  'node_modules/dep/index.ts': "export const DEP = 'formula';\n",
  'src/from-dependency.ts': `${HEAD}import { DEP } from 'dep';\ntake(DEP);\n`,
  'src/chain.ts': `${HEAD}const A = 'columns';\nconst B = A;\nconst C = B;\nvoid d[C];\n`,
  'src/chain-a.ts': "export const A = 'columns';\n",
  'src/chain-b.ts': "import { A } from './chain-a';\n\nexport const B = A;\n",
  'src/imported.ts': `${HEAD}import { A as Z } from './chain-a';\nimport { B } from './chain-b';\nvoid d[Z];\nvoid d[B];\n`,
  'src/barrel.ts': "export { A as R } from './chain-a';\nexport * from './chain-b';\n",
  'src/reexported.ts': `${HEAD}import { B, R } from './barrel';\nvoid d[R];\nvoid d[B];\n`,
  'src/chain-broken.ts': `${HEAD}let a = 'name';\na = 'columns';\nconst b = a;\nReflect.get(d, b);\n`,
};

let root: string;
let refactor: Refactor;

beforeAll(() => {
  root = tsProject(FILES);
  refactor = new Refactor({ project: root, apply: false, subcommand: 'rename' });
});

/** The sources of the name `target`, read at its last spelling inside `context` of `rel`, as `path:line: 'text'`. */
function sources(rel: string, context: string, target: string): string[] {
  const file = join(refactor.root, rel);
  const service = refactor.services(file)[0] as TS.LanguageService;
  const source = service.getProgram()?.getSourceFile(file) as TS.SourceFile;
  const position = source.text.indexOf(context) + context.lastIndexOf(target);
  const node = [...walk(source)].find(
    (n) => (ts().isIdentifier(n) || ts().isPropertyAccessExpression(n)) && n.getStart(source) === position && n.getText(source) === target,
  ) as TS.Node;
  return literalSources(service, node)
    .map((found) => ({ ...found, rel: posix(relative(refactor.root, found.path)) }))
    .sort((a, b) => byCodePoint(a.rel, b.rel) || a.start - b.start)
    .map((found) => {
      const text = FILES[found.rel] as string;
      const line = text.slice(0, found.start).split('\n').length;
      return `${found.rel}:${line}: ${text.slice(found.start - 1, found.end + 1)}`;
    });
}

describe('literalSources, supported bindings', () => {
  it('a const bound to a plain string literal', () => {
    expect(sources('src/const.ts', 'take(v)', 'v')).toEqual(["src/const.ts:5: 'formula'"]);
  });

  it('a let assigned exactly once', () => {
    expect(sources('src/let-once.ts', 'Reflect.get(d, s)', 's')).toEqual(["src/let-once.ts:5: 'columns'"]);
  });

  it('a static readonly class member read as K.NAME', () => {
    expect(sources('src/static.ts', 'take(K.FORMULA)', 'K.FORMULA')).toEqual(["src/static.ts:6: 'formula'"]);
  });

  it('a for…of target over an as const array literal: every element', () => {
    expect(sources('src/for-literal.ts', 'Reflect.get(d, s)', 's')).toEqual(["src/for-literal.ts:5: 'columns'", "src/for-literal.ts:5: 'name'"]);
  });

  it('a for…of target over a once-bound name holding an as const array literal', () => {
    expect(sources('src/for-name.ts', 'Reflect.get(d, s)', 's')).toEqual(["src/for-name.ts:5: 'columns'", "src/for-name.ts:5: 'name'"]);
  });

  it('the first parameter of an array-method callback over an as const array literal', () => {
    expect(sources('src/callback-literal.ts', 'd[s]', 's')).toEqual(["src/callback-literal.ts:5: 'columns'", "src/callback-literal.ts:5: 'name'"]);
  });

  it('the first parameter of an array-method callback over a once-bound name holding one', () => {
    expect(sources('src/callback-name.ts', 'd[s]', 's')).toEqual(["src/callback-name.ts:5: 'columns'"]);
  });

  it('reports the inner span of the literal, its text and its absolute path', () => {
    const file = join(refactor.root, 'src/const.ts');
    const service = refactor.services(file)[0] as TS.LanguageService;
    const source = service.getProgram()?.getSourceFile(file) as TS.SourceFile;
    const node = [...walk(source)].findLast((n) => ts().isIdentifier(n) && n.text === 'v') as TS.Node;
    const start = source.text.indexOf("'formula'") + 1;
    expect(literalSources(service, node)).toEqual([{ path: source.fileName, start, end: start + 'formula'.length, text: 'formula' }]);
  });
});

describe('literalSources, chains', () => {
  it('follows once-bound names assigned from one another', () => {
    expect(sources('src/chain.ts', 'd[C]', 'C')).toEqual(["src/chain.ts:5: 'columns'"]);
  });

  it('follows an import, aliased or not, and a name another module assigns from its import', () => {
    expect(sources('src/imported.ts', 'd[Z]', 'Z')).toEqual(["src/chain-a.ts:1: 'columns'"]);
    expect(sources('src/imported.ts', 'd[B]', 'B')).toEqual(["src/chain-a.ts:1: 'columns'"]);
  });

  it('follows a named and a star re-export', () => {
    expect(sources('src/reexported.ts', 'd[R]', 'R')).toEqual(["src/chain-a.ts:1: 'columns'"]);
    expect(sources('src/reexported.ts', 'd[B]', 'B')).toEqual(["src/chain-a.ts:1: 'columns'"]);
  });

  it('has none when a link of the chain has none', () => {
    expect(sources('src/chain-broken.ts', 'Reflect.get(d, b)', 'b')).toEqual([]);
  });
});

describe('literalSources, bindings without sources', () => {
  it.each([
    ['a parameter', 'src/parameter.ts', 'd[s]', 's'],
    ['a conditional value', 'src/conditional.ts', 'take(v)', 'v'],
    ['a computed value', 'src/computed.ts', 'Reflect.get(d, s)', 's'],
    ['a let assigned twice', 'src/let-twice.ts', 'Reflect.get(d, s)', 's'],
    ['an array destructuring', 'src/destructured-array.ts', 'd[s]', 's'],
    ['an object destructuring', 'src/destructured-object.ts', 'd[s]', 's'],
    ['a for…of target over an array literal without as const', 'src/plain-array.ts', 'Reflect.get(d, s)', 's'],
    ['a callback parameter over an array literal without as const', 'src/plain-array-callback.ts', 'Reflect.get(d, s)', 's'],
    ['a literal in a .d.ts file', 'src/from-declaration.ts', 'take(DEFAULT)', 'DEFAULT'],
    ['a literal in a dependency', 'src/from-dependency.ts', 'take(DEP)', 'DEP'],
  ])('%s', (_, rel, context, target) => {
    expect(sources(rel, context, target)).toEqual([]);
  });
});
