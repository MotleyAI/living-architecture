// `which` follows Python's `shutil.which` on POSIX: the PyPI twin's doctor and runner probe use it.
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { which } from '../src/contract/index.js';

describe('which', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-which-'));
  const bin = join(tmp, 'bin');
  const cwd = process.cwd();
  beforeAll(() => {
    mkdirSync(join(bin, 'dir-tool'), { recursive: true });
    writeFileSync(join(bin, 'tool'), '#!/bin/sh\n');
    chmodSync(join(bin, 'tool'), 0o755);
    writeFileSync(join(bin, 'plain'), '');
    chmodSync(join(bin, 'plain'), 0o644);
  });
  afterEach(() => process.chdir(cwd));
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  it('finds an executable in a PATH directory', () => {
    expect(which('tool', { PATH: `/nonexistent:${bin}` })).toBe(true);
  });

  it('skips non-executable files and directories', () => {
    expect(which('plain', { PATH: bin })).toBe(false);
    expect(which('dir-tool', { PATH: bin })).toBe(false);
  });

  it('an empty PATH segment is the cwd', () => {
    process.chdir(bin);
    expect(which('tool', { PATH: '/nonexistent:' })).toBe(true);
    expect(which('tool', { PATH: '/nonexistent' })).toBe(false);
  });

  it('an empty PATH finds nothing, even in the cwd', () => {
    process.chdir(bin);
    expect(which('tool', { PATH: '' })).toBe(false);
  });

  it('an unset PATH searches the system default', () => {
    expect(which('sh', {})).toBe(true);
    expect(which('tool', {})).toBe(false);
  });

  it('a name with a directory part is checked as given', () => {
    process.chdir(tmp);
    expect(which('./bin/tool', { PATH: '' })).toBe(true);
    expect(which(join(bin, 'tool'), { PATH: '/nonexistent' })).toBe(true);
    expect(which('./bin/plain', { PATH: bin })).toBe(false);
  });
});
