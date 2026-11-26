// The leak-token matcher and the token list of stealth mode.
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { findTokens, leakTokens } from '../src/leaks/index.js';
import { tempRepo } from './cli-run.js';
import { LA_SHARED, SHARED, loadYamlFile } from '../../trmv/test/helpers.js';

const CORE = ['living-architecture', 'type-rename-move', 'trmv', '/la:', '/trmv:', 'ALLOW('];
const WAIVABLE = ['arc42', 'LikeC4', 'OpenSpec', 'reset point', 'decisions log', 'pr-plan', 'pr-tests', 'pr-implement', 'pr-review'];
const REGISTRY = [
  'living-architecture.yaml',
  'living-architecture.local.yaml',
  'architecture/index.yaml',
  'trmv.yaml',
  '.tsc-baseline.json',
  '.basedpyright/baseline.json',
];
const TOKENS = [...CORE, ...WAIVABLE, ...REGISTRY, 'la-doctor', 'trmv-typecheck'];

const commands = (dir: string): string[] => Object.keys((loadYamlFile(join(dir, 'cli.yaml')) as { commands: object }).commands);

function committed(files: Record<string, string>): string {
  const root = tempRepo(files);
  if (Object.keys(files).length > 0) {
    execFileSync('git', ['add', '-A'], { cwd: root });
    execFileSync('git', ['-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--no-gpg-sign', '-q', '-m', 'init'], { cwd: root });
  }
  return root;
}

describe('findTokens', () => {
  const cases: [string, string[]][] = [
    ['Ran **LA-DOCTOR**, then the `trmv-typecheck` gate', ['la-doctor', 'trmv-typecheck', 'trmv']],
    ['retrmvx', []],
    ['xarc42y', []],
    ['pr_plan and trmv_x', []],
    ['my-trmv', ['trmv']],
    ['cat living-architecture.yaml', ['living-architecture.yaml', 'living-architecture']],
    ['# ALLOW(import-not-top): x', ['ALLOW(']],
    ['run /la:pr then /trmv:init', ['/la:', '/trmv:', 'trmv']],
    ['[LikeC4](https://likec4.dev) and **openspec**', ['LikeC4', 'OpenSpec']],
    ['Reset Point 2', ['reset point']],
    ['reset  point', []],
    ['trmv, trmv and TRMV', ['trmv']],
    ['see .basedpyright/baseline.json', ['.basedpyright/baseline.json']],
    ['nothing here', []],
  ];
  for (const [line, hits] of cases) {
    it(`matches ${JSON.stringify(line)}`, () => {
      expect(findTokens(line, TOKENS)).toEqual(hits);
    });
  }
});

describe('leakTokens', () => {
  it('holds every core, waivable, command and registry token', () => {
    const tokens = new Set(leakTokens(committed({}), []));
    const expected = [...CORE, ...WAIVABLE, ...REGISTRY, ...commands(LA_SHARED), ...commands(SHARED)];
    expect(expected.filter((t) => !tokens.has(t))).toEqual([]);
  });

  it('drops only the allowed waivable tokens', () => {
    const tokens = leakTokens(committed({}), ['arc42', 'pr-plan']);
    expect([tokens.includes('arc42'), tokens.includes('pr-plan'), tokens.includes('LikeC4')]).toEqual([false, false, true]);
  });

  for (const token of CORE) {
    it(`keeps core token ${token} even when allowed`, () => {
      expect(leakTokens(committed({}), [token])).toContain(token);
    });
  }

  it('drops OpenSpec when the repo tracks openspec/', () => {
    expect(leakTokens(committed({ 'openspec/specs/a/spec.md': '# a\n' }), [])).not.toContain('OpenSpec');
  });

  it('keeps OpenSpec for an untracked openspec/ directory', () => {
    const root = committed({ 'README.md': 'x\n' });
    mkdirSync(join(root, 'openspec', 'specs'), { recursive: true });
    writeFileSync(join(root, 'openspec', 'specs', 'spec.md'), '# a\n');
    expect(leakTokens(root, [])).toContain('OpenSpec');
  });
});
