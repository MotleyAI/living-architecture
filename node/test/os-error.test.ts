// OS errors print the runtime's own message after the contract prefix, never CPython's wording.
import { copyFileSync, cpSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest';
import { run as runArchCheck } from '../src/archcheck/index.js';
import { run as runDiagrams } from '../src/c4/index.js';

const cases = join(import.meta.dirname, '..', '..', 'conformance');

function captureStderr(): () => string {
  const spy = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
  return () => spy.mock.calls.map((call) => String(call[0])).join('');
}

describe('OS error passthrough', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-os-error-'));
  afterEach(() => vi.restoreAllMocks());
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  function diagramsRepo(name: string): string {
    const repo = join(tmp, name);
    cpSync(join(cases, 'fixtures', 'arch-diagrams', 'repo'), repo, { recursive: true });
    copyFileSync(
      join(cases, 'cases', 'arch-diagrams-doc-missing', 'repo', 'architecture', 'index.yaml'),
      join(repo, 'architecture', 'index.yaml'),
    );
    return repo;
  }

  it('la-arch-check: a missing index.yaml', () => {
    const repo = join(tmp, 'no-index');
    mkdirSync(repo);
    const stderr = captureStderr();
    expect(runArchCheck(repo, null, null)).toBe(2);
    expect(stderr()).toMatch(/^arch_check: /);
    expect(stderr()).toContain(join(repo, 'architecture', 'index.yaml'));
    expect(stderr()).not.toContain('[Errno');
  });

  it('la-arch-diagrams: a missing mapped doc', () => {
    const repo = diagramsRepo('doc-missing');
    const stderr = captureStderr();
    expect(runDiagrams(repo)).toBe(1);
    expect(stderr()).toMatch(/^la-arch-diagrams: /);
    expect(stderr()).toContain(join(repo, 'architecture', 'gone.arc42.md'));
    expect(stderr()).not.toContain('[Errno');
  });

  it('la-arch-diagrams: a mapped doc that is a directory', () => {
    const repo = diagramsRepo('doc-is-directory');
    mkdirSync(join(repo, 'architecture', 'gone.arc42.md'));
    const stderr = captureStderr();
    expect(runDiagrams(repo)).toBe(1);
    expect(stderr()).toMatch(/^la-arch-diagrams: /);
    expect(stderr()).not.toContain('[Errno');
  });
});
