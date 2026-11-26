// OS errors render from the shared os.* templates; only a missing path counts as absent.
import { chmodSync, copyFileSync, cpSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest';
import { run as runArchCheck } from '../src/archcheck/index.js';
import { run as runDiagrams } from '../src/c4/index.js';
import { isRegularFile, osErrorReason, osErrorText, readFile } from '../../trmv/src/contract/index.js';
import { REPO_ROOT, vectors } from '../../trmv/test/helpers.js';

const cases = join(REPO_ROOT, 'conformance');
const VECTORS = vectors('os-errors.yaml') as {
  reasons: [string | null, string][];
  cases: { name: string; code: string | null; error_path: unknown; error_dest?: string; path: string | null; root: string; text: string }[];
};
const unprivileged = process.platform !== 'win32' && process.getuid?.() !== 0;

/** An error as Node's fs raises it, with runtime wording the renderer must not print. */
function fsError(code: string | null, path?: unknown, dest?: string): Error {
  const error = new Error('runtime wording') as NodeJS.ErrnoException & { dest?: string };
  if (code !== null) Object.assign(error, { code, errno: -1, syscall: 'open' });
  if (path !== null && path !== undefined) Object.assign(error, { path });
  if (dest !== undefined) error.dest = dest;
  return error;
}

function thrown(action: () => unknown): NodeJS.ErrnoException {
  try {
    action();
  } catch (error) {
    return error as NodeJS.ErrnoException;
  }
  throw new Error('expected an error');
}

function captureStderr(): () => string {
  const spy = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
  return () => spy.mock.calls.map((call) => String(call[0])).join('');
}

describe('os-errors.yaml', () => {
  it.each(VECTORS.reasons)('reason of %s', (code, reason) => {
    expect(osErrorReason(fsError(code, '/r/a'))).toBe(reason);
  });

  for (const v of VECTORS.cases) {
    it(v.name, () => {
      const error = fsError(v.code, v.error_path, v.error_dest);
      expect(osErrorText(error, v.root, v.path ?? undefined)).toBe(v.text.replace('<CWD>', process.cwd()));
    });
  }
});

describe('isRegularFile', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-probe-'));
  writeFileSync(join(tmp, 'f'), 'x');
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  it('a regular file is present', () => {
    expect(isRegularFile(join(tmp, 'f'))).toBe(true);
  });

  it('a missing path is absent', () => {
    expect(isRegularFile(join(tmp, 'missing'))).toBe(false);
    expect(isRegularFile(join(tmp, 'missing', 'f'))).toBe(false);
  });

  it('a directory is absent', () => {
    mkdirSync(join(tmp, 'd'));
    expect(isRegularFile(join(tmp, 'd'))).toBe(false);
  });

  it('a symlink to a regular file is present', () => {
    symlinkSync('f', join(tmp, 'link'));
    expect(isRegularFile(join(tmp, 'link'))).toBe(true);
  });

  it('a path under a regular file raises ENOTDIR', () => {
    expect(thrown(() => isRegularFile(join(tmp, 'f', 'index.yaml'))).code).toBe('ENOTDIR');
  });

  it('a symlink loop raises ELOOP', () => {
    symlinkSync('loop', join(tmp, 'loop'));
    expect(thrown(() => isRegularFile(join(tmp, 'loop'))).code).toBe('ELOOP');
  });

  it.skipIf(!unprivileged)('an untraversable directory raises EACCES', () => {
    const locked = join(tmp, 'locked');
    mkdirSync(locked);
    writeFileSync(join(locked, 'f'), 'x');
    chmodSync(locked, 0);
    try {
      expect(thrown(() => isRegularFile(join(locked, 'f'))).code).toBe('EACCES');
    } finally {
      chmodSync(locked, 0o755);
    }
  });
});

describe('readFile', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-read-'));
  writeFileSync(join(tmp, 'f'), 'text');
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  it('returns a Buffer, or a string with utf8', () => {
    expect(Buffer.isBuffer(readFile(join(tmp, 'f')))).toBe(true);
    expect(readFile(join(tmp, 'f'), 'utf8')).toBe('text');
  });

  it('a directory raises EISDIR carrying the path', () => {
    const error = thrown(() => readFile(tmp, 'utf8'));
    expect([error.code, error.path]).toEqual(['EISDIR', tmp]);
    expect(osErrorText(error, tmp)).toBe('.: is a directory');
  });

  it('a missing file raises ENOENT carrying the path', () => {
    const error = thrown(() => readFile(join(tmp, 'missing')));
    expect([error.code, error.path]).toEqual(['ENOENT', join(tmp, 'missing')]);
  });
});

describe('commands print the template texts', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-os-error-'));
  afterEach(() => vi.restoreAllMocks());
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  function diagramsRepo(name: string): string {
    const repo = join(tmp, name);
    cpSync(join(cases, 'fixtures', 'arch-diagrams', 'repo'), repo, { recursive: true });
    copyFileSync(
      join(cases, 'la', 'cases', 'arch-diagrams-doc-missing', 'repo', 'architecture', 'index.yaml'),
      join(repo, 'architecture', 'index.yaml'),
    );
    return repo;
  }

  it('la-arch-check: a missing index.yaml', () => {
    const repo = join(tmp, 'no-index');
    mkdirSync(repo);
    const stderr = captureStderr();
    expect(runArchCheck(repo, null, null)).toBe(2);
    expect(stderr()).toBe('arch_check: architecture/index.yaml: no such file or directory\n');
  });

  it('la-arch-diagrams: a missing mapped doc', () => {
    const repo = diagramsRepo('doc-missing');
    const stderr = captureStderr();
    expect(runDiagrams(repo)).toBe(1);
    expect(stderr()).toBe('la-arch-diagrams: architecture/gone.arc42.md: no such file or directory\n');
  });

  it('la-arch-diagrams: a mapped doc that is a directory', () => {
    const repo = diagramsRepo('doc-is-directory');
    mkdirSync(join(repo, 'architecture', 'gone.arc42.md'));
    const stderr = captureStderr();
    expect(runDiagrams(repo)).toBe(1);
    expect(stderr()).toBe('la-arch-diagrams: architecture/gone.arc42.md: is a directory\n');
  });
});
