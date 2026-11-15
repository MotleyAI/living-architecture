// dr-mock-lint as a parsed command: --help, and --base printing only the findings the base branch lacks.
import { execFileSync } from 'node:child_process';
import { mkdtempSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { run, type Run } from './cli-run.js';
import { commitAll, tsProject } from './refactor-project.js';

const API = 'export function get(): number {\n  return 1;\n}\n';
const BASE_TEST = "import { vi } from 'vitest';\n\nexport const a = vi.fn();\n";
const TSCONFIG = '{\n  "compilerOptions": {"strict": true, "noEmit": true, "module": "esnext", "moduleResolution": "bundler"},\n  "include": ["src", "tests"]\n}\n';

const fn = (path: string, line: number): string => message('mock-lint.fn', { path, line, call: 'vi.fn' });
const lint = (root: string, ...argv: string[]): Run => run(root, 'dr-mock-lint', argv);

/** A repo whose `main` (pushed to a bare origin) holds `tests/a.test.ts` as BASE_TEST, checked out on `feat`. */
function based(): string {
  const root = tsProject({ 'tsconfig.json': TSCONFIG, 'src/api.ts': API, 'tests/a.test.ts': BASE_TEST });
  commitAll(root);
  const origin = join(mkdtempSync(join(tmpdir(), 'la-origin-')), 'origin.git');
  execFileSync('git', ['init', '-q', '--bare', origin]);
  execFileSync('git', ['remote', 'add', 'origin', origin], { cwd: root });
  execFileSync('git', ['push', '-q', 'origin', 'main'], { cwd: root });
  execFileSync('git', ['checkout', '-q', '-b', 'feat'], { cwd: root });
  return root;
}

describe('dr-mock-lint', () => {
  it('--help prints the help and exits 0', () => {
    const root = tsProject({});
    const result = lint(root, '--help');
    expect(result.code).toBe(0);
    expect(result.out).toContain('dr-mock-lint');
    expect(result.out).toContain('--base');
    expect(result.err).toBe('');
  });

  it('without --base still prints every finding', () => {
    const root = based();
    expect(lint(root, 'tests/a.test.ts')).toEqual({ code: 1, out: `${fn('tests/a.test.ts', 3)}\n`, err: '' });
  });
});

describe('dr-mock-lint --base', () => {
  it('prints only the added finding when the old one moved down', () => {
    const root = based();
    writeFileSync(join(root, 'tests', 'a.test.ts'), "import { vi } from 'vitest';\n\n// one\n// two\n// three\nexport const a = vi.fn();\nexport const b = vi.fn();\n");
    expect(lint(root, '--base', 'main', 'tests/a.test.ts')).toEqual({ code: 1, out: `${fn('tests/a.test.ts', 7)}\n`, err: '' });
  });

  it('maps a renamed file to its base path', () => {
    const root = based();
    renameSync(join(root, 'tests', 'a.test.ts'), join(root, 'tests', 'b.test.ts'));
    commitAll(root, 'rename');
    expect(lint(root, '--base', 'main', 'tests/b.test.ts')).toEqual({ code: 0, out: '', err: '' });
  });

  it('does not print a double that was already untyped at the base', () => {
    const root = based();
    writeFileSync(join(root, 'src', 'api.ts'), `${API}\nexport const extra = 2;\n`);
    expect(lint(root, '--base', 'main', 'tests')).toEqual({ code: 0, out: '', err: '' });
  });

  it('reports a finding whose parameters changed on the same line', () => {
    const root = based();
    writeFileSync(join(root, 'tests', 'a.test.ts'), "import { vi } from 'vitest';\n\nexport const a = jest.fn();\n");
    const jest = message('mock-lint.fn', { path: 'tests/a.test.ts', line: 3, call: 'jest.fn' });
    expect(lint(root, '--base', 'main', 'tests/a.test.ts')).toEqual({ code: 1, out: `${jest}\n`, err: '' });
  });

  it('resolves the base pass\'s mock modules against the base, so a module deleted since is a new finding', () => {
    const root = based();
    writeFileSync(join(root, 'tests', 'm.test.ts'), "import { vi } from 'vitest';\n\nvi.mock(import('../src/api'), () => ({}));\n");
    commitAll(root, 'mock');
    execFileSync('git', ['push', '-q', 'origin', 'feat:main'], { cwd: root });
    rmSync(join(root, 'src', 'api.ts'));
    const module = message('mock-lint.module', { path: 'tests/m.test.ts', line: 3, call: 'vi.mock' });
    expect(lint(root, '--base', 'main', 'tests/m.test.ts')).toEqual({ code: 1, out: `${module}\n`, err: '' });
  });

  it('reads the base pass\'s tsconfig at the base', () => {
    const root = based();
    const aliased = TSCONFIG.replace('"moduleResolution": "bundler"', '"moduleResolution": "bundler", "paths": {"@app/*": ["./src/*"]}');
    writeFileSync(join(root, 'tsconfig.json'), aliased);
    writeFileSync(join(root, 'tests', 'm.test.ts'), "import { vi } from 'vitest';\n\nvi.mock(import('@app/api'), () => ({}));\n");
    commitAll(root, 'alias');
    execFileSync('git', ['push', '-q', 'origin', 'feat:main'], { cwd: root });
    writeFileSync(join(root, 'tsconfig.json'), TSCONFIG);
    const module = message('mock-lint.module', { path: 'tests/m.test.ts', line: 3, call: 'vi.mock' });
    expect(lint(root, '--base', 'main', 'tests/m.test.ts')).toEqual({ code: 1, out: `${module}\n`, err: '' });
  });

  it('compares with origin/BRANCH as it stands when the fetch fails', () => {
    const root = based();
    execFileSync('git', ['remote', 'set-url', 'origin', join(root, 'no-such-origin.git')], { cwd: root });
    writeFileSync(join(root, 'tests', 'a.test.ts'), `${BASE_TEST}export const b = vi.fn();\n`);
    expect(lint(root, '--base', 'main', 'tests/a.test.ts')).toEqual({ code: 1, out: `${fn('tests/a.test.ts', 4)}\n`, err: '' });
  });

  it('exits 2 when origin/BRANCH does not resolve', () => {
    const root = based();
    const result = lint(root, '--base', 'nope', 'tests/a.test.ts');
    expect(result.code).toBe(2);
    expect(result.out).toBe('');
  });
});
