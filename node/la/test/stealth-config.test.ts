// la's stealth config: the stealth file loaded through trmv's resolver, its refusals, and the private store id.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ConfigError } from '../../trmv/src/config/index.js';
import { loadConfig, openspecStoreId } from '../src/config/index.js';

function write(path: string, text: string): string {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text);
  return path;
}

function repo(): string {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'la-stealth-')));
  execFileSync('git', ['init', '-q', '-b', 'main'], { cwd: root, stdio: 'pipe' });
  return root;
}

function stealth(root: string, text: string): string {
  return write(join(root, '.git', 'living-architecture', 'living-architecture.yaml'), `format: 0.14.0\n${text}`);
}

function configError(root: string): string {
  try {
    loadConfig(root);
  } catch (error) {
    expect(error).toBeInstanceOf(ConfigError);
    return (error as Error).message;
  }
  throw new Error('no ConfigError');
}

describe('openspecStoreId', () => {
  it('is la- and twelve hex digits of the path digest', () => {
    expect(openspecStoreId('/x/.git/living-architecture')).toBe('la-e9f5a185b6df');
  });

  it('follows the stealth dir', () => {
    const dir = join(repo(), '.git', 'living-architecture');
    expect(openspecStoreId(dir)).toBe(`la-${createHash('sha256').update(dir).digest('hex').slice(0, 12)}`);
  });
});

describe('loadConfig in stealth', () => {
  it('loads the stealth file', () => {
    const root = repo();
    stealth(root, 'tracker: none\n');
    expect(loadConfig(root).tracker).toBe('none');
  });

  it('refuses the local file', () => {
    const root = repo();
    stealth(root, 'tracker: none\n');
    write(join(root, 'living-architecture.local.yaml'), 'tracker: github\n');
    expect(configError(root)).toContain('living-architecture.local.yaml');
  });

  it('refuses architecture: true, naming the file', () => {
    const root = repo();
    const path = stealth(root, 'architecture: true\n');
    const message = configError(root);
    expect(message).toContain('architecture');
    expect(message).toContain(path);
  });

  it('refuses a core leak token', () => {
    const root = repo();
    stealth(root, 'leaks: {allow: [trmv]}\n');
    expect(configError(root)).toContain('trmv');
  });

  it('allows waivable leak tokens', () => {
    const root = repo();
    stealth(root, 'leaks: {allow: [arc42, pr-plan]}\n');
    expect(loadConfig(root).leaks.allow).toEqual(['arc42', 'pr-plan']);
  });

  it('refuses leaks in a root file', () => {
    const root = repo();
    write(join(root, 'living-architecture.yaml'), 'format: 0.14.0\nleaks: {allow: [arc42]}\n');
    expect(configError(root)).toContain('leaks');
  });
});
