// dr-refactor phases: the map loader's every invalid entry, the keep text check, and what the conflicts phase is
// charged with.
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { message } from '../src/contract/index.js';
import { MapError, loadMap } from '../src/refactor/map.js';
import { nearestLine, spelledLines } from '../src/refactor/sites.js';
import { entryRefusal, finalReport, refactorRaw, tsProject } from './refactor-project.js';

const SECOND = 1_000_000_000n;

// A fake clock that only building the named findings advances, by 100 s each.
const slow = vi.hoisted(() => ({ now: 0n, keys: new Set<string>() }));
vi.mock(import('../src/contract/index.js'), async (importOriginal) => {
  const contract = await importOriginal();
  return {
    ...contract,
    message: (id: string, values?: Record<string, unknown>): string => {
      if (slow.keys.has(id)) slow.now += 100n * SECOND;
      return contract.message(id, values);
    },
  };
});

const CHECKS = '[resolve]\n[checks]\n';
const FOO = 'export function foo(): number {\n  return 1;\n}\n';

describe('the map loader', () => {
  it('names every invalid entry', () => {
    const root = tsProject({});
    const path = join(root, 'map.yaml');
    writeFileSync(
      path,
      '- {file: a.ts, symbol: f, new_name: g}\n- {file: a.ts, symbol: f}\n- {file: a.ts, symbol: h, new_name: i}\n- {file: a.ts, new_name: j}\n',
    );
    const expected = [2, 4].map((index) => message('refactor.map-invalid', { map: 'map.yaml', index })).join('\n');
    expect(() => loadMap(path, 'map.yaml')).toThrow(new MapError(expected));
  });
  it('loads module entries as written', () => {
    const root = tsProject({});
    const path = join(root, 'map.yaml');
    writeFileSync(path, '- {module: src/a.ts, new_name: b}\n- {file: src/c.ts, symbol: f, new_name: g}\n');
    expect(loadMap(path, 'map.yaml')).toEqual([{ module: 'src/a.ts', new_name: 'b' }, { file: 'src/c.ts', symbol: 'f', new_name: 'g' }]);
  });

  it('names every invalid module entry', () => {
    const root = tsProject({});
    const path = join(root, 'map.yaml');
    writeFileSync(
      path,
      '- {module: a.ts, symbol: f, new_name: g}\n- {module: a.ts, retarget: f}\n- {module: a.ts, file: a.ts, new_name: g}\n- {module: a.ts, new_name: g}\n',
    );
    const expected = [1, 2, 3].map((index) => message('refactor.map-invalid', { map: 'map.yaml', index })).join('\n');
    expect(() => loadMap(path, 'map.yaml')).toThrow(new MapError(expected));
  });
});

describe('the keep text check', () => {
  it.each([
    ['as written', 'const a = 1;\nconst b = load();\n', [2]],
    ['absent', 'const x = 1;\n', []],
    ['string escape', 'const n = "lo\\x61d";\n', [1]],
    ['identifier escape', 'store.lo\\u0061d();\n', [1]],
    ['comment', '// load the store\n', [1]],
    ['no NFKC', 'const ｌoad = 1;\n', []],
  ])('%s', (_kind, text, lines) => {
    expect([...spelledLines(text, new Set(['load']))].sort()).toEqual(lines);
  });

  it.each([
    ['comment', '// load the store\n', []],
    ['block comment line', '/* the store\n   load reads it */\n', []],
    ['JSDoc param', '/**\n * @param load the loader\n */\n', []],
    ['trailing comment', 'const x = 1; // load\n', []],
    ['code and comment', 'const y = load(); // load\n', [1]],
    ['comment marker in a string', 'const s = "// load";\n', [1]],
    ['template', 'const t = `/* ${x} load */`;\n', [1]],
  ])('without comments: %s', (_kind, text, lines) => {
    expect([...spelledLines(text, new Set(['load']), true, false)].sort()).toEqual(lines);
  });

  it('parses a .tsx file as TSX, so JSX text is not read as a comment', () => {
    const text = 'const a = <div>http://example.test {load()}</div>;\n';
    expect([...spelledLines(text, new Set(['load']), true, false, 'lib/a.tsx')]).toEqual([1]);
  });

  it.each([
    ['before', [4, 30], 9, 4],
    ['after', [2, 12], 9, 12],
    ['tie takes the earlier', [12, 6], 9, 6],
    ['none', [], 9, null],
    ['same line', [9], 9, 9],
  ])('nearest edited line: %s', (_kind, edited, line, nearest) => {
    expect(nearestLine(edited, line)).toBe(nearest);
  });

  it('matches an old name written with an identifier escape', () => {
    expect([...spelledLines('// load the store\n', new Set([String.raw`lo\u0061d`]))]).toEqual([1]);
  });

  it('leaves an out-of-range escape as written', () => {
    expect([...spelledLines(String.raw`// \u{110000} then load` + '\n', new Set(['load']))]).toEqual([1]);
  });

  it('is skipped when an unresolved entry spells no name', () => {
    const root = tsProject({
      'src/a.ts': FOO,
      'README.md': '# Nothing here\n',
      'map.yaml': '- {file: src/a.ts, symbol: foo, new_name: bar}\n- {file: src/a.ts, line: 99, new_name: baz}\n',
    });
    expect(refactorRaw(root, 'rename-map', 'map.yaml', '--keep', 'README.md')).toEqual({
      code: 1,
      out: '',
      err: `${CHECKS}${entryRefusal('src/a.ts:99', message('refactor.line-out-of-range', { line: 99, count: 3 }), 2)}\n`,
    });
  });

  it('skips a whole-path keep, which warns at site resolution', () => {
    const root = tsProject({ 'src/a.ts': FOO, 'docs/x.ts': 'export const y = 1;\n' });
    const result = refactorRaw(root, 'rename', '--file', 'src/a.ts', '--symbol', 'foo', '--new-name', 'bar', '--keep', 'docs');
    expect(result.code).toBe(0);
    const err = result.err.split('\n');
    const warning = message('refactor.keep-unneeded', { site: 'docs' });
    expect(err).toContain('[references]');
    expect(err.indexOf(warning)).toBeGreaterThan(-1);
    expect(err.indexOf(warning)).toBeLessThan(err.indexOf(message('refactor.progress-phase', { phase: 'conflicts' })));
  });
});

const CONFLICTS = message('refactor.progress-phase', { phase: 'conflicts' });
const TIMING = new RegExp(
  `^${message('refactor.timing', { phase: 'PHASE', seconds: '0.00' })
    .replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`)
    .replace('PHASE', String.raw`(\S+)`)
    .replace(String.raw`0\.00`, String.raw`(\d+\.\d\d)`)}$`,
);
// `fetch` is inherited, so only the conflicts phase finds it.
const STORE = 'export class Base {\n  fetch(): number {\n    return 2;\n  }\n}\n\nexport class Store extends Base {\n  load(): number {\n    return 1;\n  }\n}\n';
const HIER =
  'export class Base {\n  ping(): number {\n    return 1;\n  }\n}\n\nexport class Sub extends Base {\n  override ping(): number {\n    return 2;\n  }\n}\n';

function times(err: string): Map<string, string> {
  return new Map(err.split('\n').flatMap((line) => {
    const m = TIMING.exec(line);
    return m === null ? [] : [[m[1] as string, m[2] as string] as const];
  }));
}

describe('the conflicts phase', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    slow.keys.clear();
  });

  it.each([
    ['member', { 'src/store.ts': STORE }, ['rename', '--file', 'src/store.ts', '--symbol', 'Store.load', '--new-name', 'fetch'], 'refactor.name-conflict'],
    [
      'binding',
      { 'src/a.ts': `${FOO}\nexport function use(): number {\n  const bar = 2;\n  return foo() + bar;\n}\n` },
      ['rename', '--file', 'src/a.ts', '--symbol', 'foo', '--new-name', 'bar'],
      'refactor.name-conflict',
    ],
    [
      'map',
      { 'src/hier.ts': HIER, 'map.yaml': '- {file: src/hier.ts, symbol: Base.ping, new_name: a}\n- {file: src/hier.ts, symbol: Sub.ping, new_name: b}\n' },
      ['rename-map', 'map.yaml'],
      'refactor.map-conflict',
    ],
  ])('charges a %s conflict check to conflicts, announced before its finding', (_kind, files, argv, finding) => {
    const root = tsProject(files);
    slow.now = 0n;
    vi.spyOn(process.hrtime, 'bigint').mockImplementation(() => slow.now);
    slow.keys.add(finding);
    const { code, out, err } = refactorRaw(root, '--timings', ...argv);
    expect([code, out]).toEqual([1, '']);
    const lines = err.split('\n');
    const first = finalReport(err).split('\n')[0] ?? '';
    expect(lines).toContain(CONFLICTS);
    expect(lines.indexOf(CONFLICTS)).toBeLessThan(lines.indexOf(first));
    const spent = times(err);
    expect(spent.get('conflicts') ?? '0.00').not.toBe('0.00');
    expect([...spent].filter(([phase, s]) => phase !== 'conflicts' && phase !== 'total' && s !== '0.00')).toEqual([]);
  });

  it.each([
    ['announces conflicts after every group', [], true],
    ['skips conflicts after a --fail-fast stop', ['--fail-fast'], false],
  ])('%s', (_title, flags, announced) => {
    const root = tsProject({
      'src/store.ts': 'export class Store {\n  drop(): number {\n    return 1;\n  }\n\n  load(): number {\n    return 2;\n  }\n}\n',
      'src/loose.ts': 'export function loose(s: any): number {\n  return s.drop();\n}\n',
      'map.yaml': '- {file: src/store.ts, symbol: Store.drop, new_name: discard}\n- {file: src/store.ts, symbol: Store.load, new_name: fetch}\n',
    });
    const { code, out, err } = refactorRaw(root, 'rename-map', 'map.yaml', ...flags);
    expect([code, out]).toEqual([1, '']);
    expect(err.split('\n').includes(CONFLICTS)).toBe(announced);
  });
});
