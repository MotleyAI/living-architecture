// `la-affected-tests` through the npm twin, the change set (src/changes) and the contract pieces it uses:
// resolveBaseRef(base, repoRoot): string, changedPaths({ baseRef, repoRoot, deletions, untracked }): string[],
// isTestFile(rel): boolean.
import { execFileSync } from 'node:child_process';
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, dirname, join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { changedPaths, prBaseBranch, resolveBaseRef } from '../src/changes/index.js';
import { ConfigError } from '../src/config/index.js';
import { baseFetchTimeout, contractHash, isTestFile, language, message, schema, validate } from '../src/contract/index.js';
import { VERSION } from '../src/index.js';
import { run, tempRepo, type Run } from './cli-run.js';
import { SHARED, loadYamlFile, vectors } from './helpers.js';

// Every test drives real git repos: the default 5 s is too tight under a parallel run.
vi.setConfig({ testTimeout: 30_000 });

const PYTHON_IDENTITY = `python ${VERSION} ${contractHash()}`;
const LANGUAGES = loadYamlFile(join(SHARED, 'languages.yaml'));
const BASE = {
  'src/a.ts': "import { b } from './b';\nexport const a = b;\n",
  'src/b.ts': 'export const b = 1;\n',
  'test/a.test.ts': "import { a } from '../src/a';\nexport const t = a;\n",
  'test/c.test.ts': 'export const c = 1;\n',
};
const JSON_TSCONFIG = '{"compilerOptions": {"module": "esnext", "moduleResolution": "bundler", "resolveJsonModule": true}}\n';
const savedPath = process.env.PATH;
const CAT = execFileSync('sh', ['-c', 'command -v cat'], { encoding: 'utf8' }).trim();

afterEach(() => {
  process.env.PATH = savedPath;
});

function git(root: string, ...args: string[]): void {
  execFileSync('git', args, { cwd: root, stdio: 'ignore' });
}

function write(root: string, files: Record<string, string>): void {
  for (const [rel, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, rel)), { recursive: true });
    writeFileSync(join(root, rel), text);
  }
}

function commit(root: string, msg = 'work'): void {
  git(root, 'add', '-A');
  git(root, '-c', 'user.email=t@example.com', '-c', 'user.name=t', 'commit', '-q', '-m', msg);
}

/** A repo whose `origin/main` is a commit of `files`, on branch `feat`. */
function repo(files: Record<string, string> = BASE): string {
  const root = tempRepo(files);
  commit(root, 'base');
  git(root, 'update-ref', 'refs/remotes/origin/main', 'HEAD');
  git(root, 'checkout', '-q', '-b', 'feat');
  return root;
}

const affected = (root: string, ...args: string[]): Run => run(root, 'la-affected-tests', args);
const lines = (text: string): string[] => text.split('\n').filter((line) => line !== '');

function ok(root: string): string[] {
  const result = affected(root, '--base', 'main');
  expect({ code: result.code, err: result.err }).toEqual({ code: 0, err: '' });
  return lines(result.out);
}

/** PATH holding only `git` (and `extra` dirs first): no other twin and no runner is reachable. */
function gitOnlyPath(...extra: string[]): void {
  const dir = mkdtempSync(join(tmpdir(), 'la-git-only-'));
  symlinkSync(execFileSync('sh', ['-c', 'command -v git'], { encoding: 'utf8' }).trim(), join(dir, 'git'));
  process.env.PATH = [...extra, dir].join(delimiter);
}

describe('selection', () => {
  it('nothing changed', () => {
    expect(ok(repo())).toEqual([]);
  });

  it('a changed test only', () => {
    const root = repo();
    write(root, { 'test/c.test.ts': 'export const c = 2;\n' });
    commit(root);
    expect(ok(root)).toEqual(['test/c.test.ts']);
  });

  it('transitive reach leaves unrelated tests out', () => {
    const root = repo();
    write(root, { 'src/b.ts': 'export const b = 2;\n' });
    commit(root);
    expect(ok(root)).toEqual(['test/a.test.ts']);
  });

  it('a changed test helper selects its importers', () => {
    const root = repo({ ...BASE, 'test/helpers.ts': 'export const h = 1;\n', 'test/x.test.ts': "import { h } from './helpers';\n" });
    write(root, { 'test/helpers.ts': 'export const h = 2;\n' });
    expect(ok(root)).toEqual(['test/helpers.ts', 'test/x.test.ts']);
  });

  it('a type-only import counts', () => {
    const root = repo({ ...BASE, 'test/t.test.ts': "import type { B } from '../src/types';\n", 'src/types.ts': 'export type B = 1;\n' });
    write(root, { 'src/types.ts': 'export type B = 2;\n' });
    expect(ok(root)).toEqual(['test/t.test.ts']);
  });

  it('a deleted module still imported', () => {
    const root = repo();
    git(root, 'rm', '-q', 'src/b.ts');
    commit(root);
    expect(ok(root)).toEqual(['test/a.test.ts']);
  });

  it('a deleted test is not printed', () => {
    const root = repo();
    git(root, 'rm', '-q', 'test/c.test.ts');
    commit(root);
    expect(ok(root)).toEqual([]);
  });

  it('a rename selects the importers of the old path', () => {
    const root = repo();
    git(root, 'mv', 'src/b.ts', 'src/b2.ts');
    commit(root);
    expect(ok(root)).toEqual(['test/a.test.ts']);
  });

  it('an untracked test is listed, an ignored one is not', () => {
    const root = repo();
    write(root, { 'test/new.test.ts': '', 'test/ignored.test.ts': '', '.gitignore': 'test/ignored.test.ts\n' });
    expect(ok(root)).toEqual(['test/new.test.ts']);
  });

  it('staged-only and unstaged-only edits', () => {
    const root = repo();
    write(root, { 'test/a.test.ts': `${BASE['test/a.test.ts']}// staged\n`, 'test/c.test.ts': 'export const c = 3;\n' });
    git(root, 'add', 'test/a.test.ts');
    expect(ok(root)).toEqual(['test/a.test.ts', 'test/c.test.ts']);
  });

  it('the output does not depend on the working directory', () => {
    const root = repo();
    write(root, { 'src/b.ts': 'export const b = 2;\n' });
    expect(ok(join(root, 'src'))).toEqual(ok(root));
  });

  it('an import cycle terminates', () => {
    const root = repo({ ...BASE, 'src/b.ts': "import { a } from './a';\nexport const b = 1;\nexport const x = a;\n" });
    write(root, { 'src/b.ts': "import { a } from './a';\nexport const b = 2;\nexport const x = a;\n" });
    expect(ok(root)).toEqual(['test/a.test.ts']);
  });

  it('an architecture index changes nothing', () => {
    const root = repo();
    write(root, { 'src/b.ts': 'export const b = 2;\n' });
    const without = ok(root);
    write(root, { 'architecture/index.yaml': 'typescript:\n  root_package: src\n' });
    commit(root);
    expect(ok(root)).toEqual(without);
  });

  it('code-point order and unusual names', () => {
    const root = repo();
    git(root, 'config', 'core.quotePath', 'true');
    write(root, Object.fromEntries(['test/é.test.ts', 'test/my file.test.ts', 'test/a2.test.ts', 'test/B.test.ts'].map((p) => [p, ''])));
    expect(ok(root)).toEqual(['test/B.test.ts', 'test/a2.test.ts', 'test/my file.test.ts', 'test/é.test.ts']);
  });

  it('a YAML-only change prints nothing', () => {
    const root = repo({ 'tests/test_a.py': 'import os\n', 'config.yaml': 'a: 1\n' });
    gitOnlyPath();
    write(root, { 'config.yaml': 'a: 2\n' });
    expect(ok(root)).toEqual([]);
  });

  it('a JSON-only change selects its importers natively', () => {
    const root = repo({ ...BASE, 'src/data.json': '{}\n', 'test/d.test.ts': "import data from '../src/data.json';\n", 'tsconfig.json': JSON_TSCONFIG });
    gitOnlyPath();
    write(root, { 'src/data.json': '{"a": 1}\n' });
    expect(ok(root)).toEqual(['test/d.test.ts']);
  });
});

describe('setup and git failures', () => {
  const failure = (result: Run): [number, string, boolean] => [result.code, result.out, result.err.startsWith('la-affected-tests: ')];

  it('a missing --base is a usage error', () => {
    expect(affected(repo()).code).toBe(2);
  });

  it('a missing base ref', () => {
    const result = affected(repo(), '--base', 'nope');
    expect([result.code, result.out, result.err]).toEqual([2, '', 'la-affected-tests: git rev-parse --verify --quiet origin/nope failed\n']);
  });

  it('git missing from PATH', () => {
    const root = repo();
    process.env.PATH = mkdtempSync(join(tmpdir(), 'la-empty-'));
    const result = affected(root, '--base', 'main');
    expect([result.code, result.out, result.err]).toEqual([2, '', 'la-affected-tests: git rev-parse --verify --quiet origin/main failed\n']);
  });

  it.skipIf(process.platform === 'win32')('a stalled fetch is bounded, never prompts and leaves no helper behind', () => {
    const root = repo();
    const which = (tool: string): string => execFileSync('sh', ['-c', `command -v ${tool}`], { encoding: 'utf8' }).trim();
    const sleep = which('sleep');
    const fake = mkdtempSync(join(tmpdir(), 'la-slow-git-'));
    writeFileSync(
      join(fake, 'git'),
      `#!/bin/sh\nif [ "$1" = fetch ]; then echo "$GIT_TERMINAL_PROMPT|\${GIT_ASKPASS-unset}|\${SSH_ASKPASS-unset}|$SSH_ASKPASS_REQUIRE" > "${fake}/prompt"\n` +
        `  "${sleep}" 30 & echo $! > "${fake}/helper"; wait; fi\nexec "${which('git')}" "$@"\n`,
    );
    chmodSync(join(fake, 'git'), 0o755);
    process.env.PATH = fake;
    const start = Date.now();
    expect(resolveBaseRef('main', root, 0.5)).toBe('origin/main');
    const elapsed = Date.now() - start;
    const helper = Number(readFileSync(join(fake, 'helper'), 'utf8'));
    const alive = (): boolean => {
      try {
        process.kill(helper, 0);
        return true;
      } catch {
        return false;
      }
    };
    const deadline = Date.now() + 5000;
    while (alive() && Date.now() < deadline) execFileSync(sleep, ['0.05']);
    expect([elapsed < 10_000, readFileSync(join(fake, 'prompt'), 'utf8'), alive()]).toEqual([true, '0|||never\n', false]);
  });

  it('the fetch timeout comes from the shared contract', () => {
    expect(baseFetchTimeout()).toBe(30);
  });

  it('gh missing from PATH', () => {
    const root = repo();
    process.env.PATH = mkdtempSync(join(tmpdir(), 'la-empty-'));
    expect(() => prBaseBranch('7', null, root)).toThrow(new ConfigError('could not resolve the base branch of PR 7'));
  });

  it.skipIf(process.platform === 'win32' || process.getuid?.() === 0)('an unreadable importer fails', () => {
    const root = repo();
    write(root, { 'src/b.ts': 'export const b = 2;\n' });
    chmodSync(join(root, 'src/a.ts'), 0);
    const result = affected(root, '--base', 'main');
    expect([...failure(result), result.err.includes('a.ts')]).toEqual([2, '', true, true]);
  });

  it('not a git repository', () => {
    expect(failure(affected(mkdtempSync(join(tmpdir(), 'la-nogit-')), '--base', 'main'))).toEqual([2, '', true]);
  });

  it('an unborn HEAD', () => {
    const root = repo();
    git(root, 'checkout', '-q', '--orphan', 'fresh');
    expect(failure(affected(root, '--base', 'main'))).toEqual([2, '', true]);
  });

  it('a changed path with a newline names it', () => {
    const root = repo();
    write(root, { 'test/new\nline.test.ts': '' });
    const result = affected(root, '--base', 'main');
    expect([...failure(result), result.err.includes('new')]).toEqual([2, '', true, true]);
  });

  it('a graph path with a newline', () => {
    const root = repo({ ...BASE, 'src/odd\nname.ts': '' });
    write(root, { 'src/b.ts': 'export const b = 2;\n' });
    const result = affected(root, '--base', 'main');
    expect([result.code, result.out, result.err.includes('odd')]).toEqual([2, '', true]);
  });

  it('a changed path that is not UTF-8', () => {
    const root = repo();
    writeFileSync(Buffer.concat([Buffer.from(`${root}/test/`), Buffer.from([0xff]), Buffer.from('.test.ts')]), '');
    expect(failure(affected(root, '--base', 'main'))).toEqual([2, '', true]);
  });
});

describe('the other language', () => {
  function stubTwin(response: string): string {
    const dir = mkdtempSync(join(tmpdir(), 'la-pypi-'));
    const doctor = join(dir, 'la-doctor');
    const command = join(dir, 'la-affected-tests');
    writeFileSync(doctor, `#!/bin/sh\necho '${PYTHON_IDENTITY}'\n`);
    writeFileSync(
      command,
      `#!/bin/sh\necho "$* $LA_FORWARDED" > '${dir}/argv'\n${CAT} > '${dir}/stdin'\n${CAT} <<'EOF'\n${response}\nEOF\n`,
    );
    chmodSync(doctor, 0o755);
    chmodSync(command, 0o755);
    return dir;
  }

  const response = (tests: string[], overrides: Record<string, unknown> = {}): string =>
    JSON.stringify({ language: 'python', version: VERSION, contract_hash: contractHash(), tests, ...overrides });

  it('an own-language change needs no twin', () => {
    const root = repo();
    gitOnlyPath();
    write(root, { 'src/b.ts': 'export const b = 2;\n' });
    expect(ok(root)).toEqual(['test/a.test.ts']);
  });

  it('the other twin unreachable', () => {
    const root = repo();
    gitOnlyPath();
    write(root, { 'tests/test_x.py': 'import os\n' });
    const result = affected(root, '--base', 'main');
    const hint = `la-affected-tests: the python twin (living-architecture ${VERSION}) is not reachable; install it with: uv tool install living-architecture==${VERSION}\n`;
    expect([result.code, result.out, result.err]).toEqual([2, '', hint]);
  });

  it('two languages are unioned and the request carries the changed paths', () => {
    const root = repo();
    const stub = stubTwin(response(['tests/test_x.py', 'tests/test_b.py']));
    gitOnlyPath(stub);
    write(root, { 'src/b.ts': 'export const b = 2;\n', 'pkg/x.py': 'X = 1\n' });
    git(root, 'rm', '-q', 'test/c.test.ts');
    expect(ok(root)).toEqual(['test/a.test.ts', 'tests/test_b.py', 'tests/test_x.py']);
    expect(readFileSync(join(stub, 'argv'), 'utf8')).toBe('--language python 1\n');
    const request = JSON.parse(readFileSync(join(stub, 'stdin'), 'utf8'));
    expect(validate(schema('affected-request'), request)).toEqual([]);
    expect(request).toEqual({
      changes: [
        { path: 'pkg/x.py', deleted: false },
        { path: 'src/b.ts', deleted: false },
        { path: 'test/c.test.ts', deleted: true },
      ],
    });
  });

  it.each([
    ['wrong version', response(['tests/test_x.py'], { version: '0.0.0' })],
    ['wrong language', response(['tests/test_x.py'], { language: 'typescript' })],
    ['wrong contract hash', response(['tests/test_x.py'], { contract_hash: '0'.repeat(64) })],
    ['not JSON', 'not json'],
    ['schema-invalid', JSON.stringify({ tests: ['tests/test_x.py'] })],
    ['absolute path', response(['/abs/test_x.py'])],
  ])('an invalid twin response (%s) exits 2 with empty stdout', (_name, body) => {
    const root = repo();
    gitOnlyPath(stubTwin(body));
    write(root, { 'src/b.ts': 'export const b = 2;\n', 'pkg/x.py': 'X = 1\n' });
    const result = affected(root, '--base', 'main');
    expect([result.code, result.out, result.err.startsWith('la-affected-tests: ')]).toEqual([2, '', true]);
  });
});

describe('changes', () => {
  function listing(): string {
    const root = repo({ 'kept.ts': '', 'modified.ts': '', 'deleted.ts': '', 'old.ts': '', 'staged.ts': '', 'unstaged.ts': '', 'gone.ts': '' });
    write(root, { 'modified.ts': 'x;\n', 'added.ts': '', 'notes.txt': 'x\n' });
    git(root, 'rm', '-q', 'deleted.ts');
    git(root, 'mv', 'old.ts', 'new.ts');
    commit(root);
    write(root, { 'staged.ts': 'x;\n', 'unstaged.ts': 'x;\n', 'untracked.ts': '', 'ignored.ts': '', '.gitignore': 'ignored.ts\n' });
    git(root, 'add', 'staged.ts');
    rmSync(join(root, 'gone.ts'));
    return root;
  }

  it('resolves the origin branch', () => {
    expect(resolveBaseRef('main', repo())).toBe('origin/main');
  });

  it('a missing base ref is a ConfigError with the shared text', () => {
    const root = repo();
    expect(() => resolveBaseRef('nope', root)).toThrow(new ConfigError('git rev-parse --verify --quiet origin/nope failed'));
  });

  it('lists without deletions or untracked files', () => {
    const root = listing();
    expect(changedPaths({ baseRef: 'origin/main', repoRoot: root, deletions: false, untracked: false })).toEqual([
      'added.ts',
      'modified.ts',
      'new.ts',
      'notes.txt',
      'staged.ts',
      'unstaged.ts',
    ]);
  });

  it('lists with deletions and untracked files', () => {
    const root = listing();
    expect(changedPaths({ baseRef: 'origin/main', repoRoot: root, deletions: true, untracked: true })).toEqual([
      '.gitignore',
      'added.ts',
      'deleted.ts',
      'gone.ts',
      'modified.ts',
      'new.ts',
      'notes.txt',
      'old.ts',
      'staged.ts',
      'unstaged.ts',
      'untracked.ts',
    ]);
  });

  it('the git texts moved with identical wording', () => {
    expect(message('changes.git-failed', { args: 'diff HEAD' })).toBe('git diff HEAD failed');
    expect(message('changes.pr-base-unresolved', { pr: 7 })).toBe('could not resolve the base branch of PR 7');
  });
});

describe('contract pieces', () => {
  for (const lang of ['python', 'typescript']) {
    const extensions: string[] = LANGUAGES[lang].source_extensions;
    for (const v of (vectors('test-files.yaml')?.[lang] ?? []) as { path: string; test: boolean }[]) {
      it(`isTestFile reproduces ${lang}: ${v.path}`, () => {
        expect(isTestFile(v.path)).toBe(v.test && extensions.some((ext) => v.path.endsWith(ext)));
      });
    }
  }

  it.each([
    [{ changes: [{ path: 'src/a.py', deleted: false }] }, true],
    [{ changes: [] }, true],
    [{ changes: [{ path: 'src/a.py' }] }, false],
    [{ changes: [{ path: '/abs/a.py', deleted: false }] }, false],
    [{ changes: [{ path: '../a.py', deleted: false }] }, false],
    [{ changes: [{ path: 'a/./b.py', deleted: false }] }, false],
    [{ changes: [{ path: 'a\\b.py', deleted: false }] }, false],
    [{ changes: [{ path: 'a//b.py', deleted: false }] }, false],
    [{}, false],
  ])('request schema: %j valid=%s', (document, valid) => {
    expect(validate(schema('affected-request'), document).length === 0).toBe(valid);
  });

  it('the response schema requires the identity', () => {
    const good = { language: 'typescript', version: '1.2.3', contract_hash: 'ab', tests: ['web/a.test.ts'] };
    expect(validate(schema('affected-response'), good)).toEqual([]);
    const partial = Object.fromEntries(Object.entries(good).filter(([key]) => key !== 'contract_hash'));
    expect(validate(schema('affected-response'), partial)).not.toEqual([]);
  });

  it('imports_non_source is set per language', () => {
    expect([language('python').imports_non_source, language('typescript').imports_non_source]).toEqual([false, true]);
  });
});
