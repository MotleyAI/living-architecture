// A failed scaffold write leaves the repo as it was.
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { writeScaffold } from '../src/archcheck/scaffold.js';

describe('writeScaffold', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-scaffold-'));
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  it('restores the index and removes new files and directories when a write fails', () => {
    const arch = join(tmp, 'architecture');
    mkdirSync(join(arch, 'views.c4'), { recursive: true });
    writeFileSync(join(arch, 'index.yaml'), 'python: {}\r\n');
    const files = new Map([
      ['architecture/model/specification.c4', 'spec'],
      ['architecture/index.yaml', 'changed\n'],
      ['architecture/views.c4', 'v'],
    ]);
    expect(() => writeScaffold(tmp, files)).toThrow();
    expect(readFileSync(join(arch, 'index.yaml'), 'utf8')).toBe('python: {}\r\n');
    expect(existsSync(join(arch, 'model'))).toBe(false);
    expect(statSync(join(arch, 'views.c4')).isDirectory()).toBe(true);
  });

  it('keeps a target it did not create', () => {
    const repo = join(tmp, 'race');
    const arch = join(repo, 'architecture');
    mkdirSync(arch, { recursive: true });
    writeFileSync(join(arch, 'index.yaml'), 'python: {}\r\n');
    writeFileSync(join(arch, 'views.c4'), 'theirs');
    const files = new Map([
      ['architecture/model/specification.c4', 'spec'],
      ['architecture/views.c4', 'v'],
    ]);
    expect(() => writeScaffold(repo, files)).toThrow(/EEXIST/);
    expect(readFileSync(join(arch, 'views.c4'), 'utf8')).toBe('theirs');
    expect(existsSync(join(arch, 'model'))).toBe(false);
  });
});
