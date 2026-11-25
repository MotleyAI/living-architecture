// la's packed tarball reaches trmv only through the `type-rename-move` package, never through trmv's sources.
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { REPO_ROOT } from '../../trmv/test/helpers.js';

const TIMEOUT = 600_000;
const TMP = mkdtempSync(join(tmpdir(), 'la-pack-la-'));
const UNPACKED = join(TMP, 'unpacked');
const PREFIX = join(TMP, 'prefix');
const SPECIFIER = /(?:from\s*|import\s*\(\s*|require\s*\(\s*)['"]([^'"]+)['"]/g;
const TARBALLS: Record<string, string> = {};

beforeAll(() => {
  const packed = spawnSync('npm', ['pack', '--json', '--pack-destination', TMP, '-w', 'trmv', '-w', 'la'], {
    cwd: join(REPO_ROOT, 'node'),
    encoding: 'utf8',
  });
  expect(packed.status, packed.stderr).toBe(0);
  for (const entry of JSON.parse(packed.stdout)) TARBALLS[entry.name] = join(TMP, entry.filename);
  mkdirSync(UNPACKED, { recursive: true });
  expect(spawnSync('tar', ['-xzf', TARBALLS['living-architecture'] ?? '', '-C', UNPACKED]).status).toBe(0);
  const installed = spawnSync(
    'npm',
    ['install', '-g', '--prefix', PREFIX, '--no-audit', '--no-fund', ...Object.values(TARBALLS)],
    {
      cwd: TMP,
      encoding: 'utf8',
    },
  );
  expect(installed.status, installed.stderr).toBe(0);
}, TIMEOUT);

afterAll(() => rmSync(TMP, { recursive: true, force: true }));

function specifiers(): string[] {
  const root = join(UNPACKED, 'package');
  return readdirSync(root, { recursive: true, encoding: 'utf8' })
    .filter((rel) => rel.endsWith('.js'))
    .flatMap((rel) => [...readFileSync(join(root, rel), 'utf8').matchAll(SPECIFIER)].map((m) => m[1] ?? ''));
}

/** `type-rename-move/<subpath>` for every export of the installed package. */
function trmvSubpaths(): string[] {
  const manifest = JSON.parse(readFileSync(join(PREFIX, 'lib', 'node_modules', 'type-rename-move', 'package.json'), 'utf8'));
  return Object.keys(manifest.exports).map((key) => `type-rename-move${key.slice(1)}`);
}

describe('packed living-architecture', () => {
  it('imports trmv by its package name only', () => {
    const all = specifiers();
    expect(all.filter((s) => s.split('/')[0] === 'type-rename-move').length).toBeGreaterThan(0);
    expect(all.filter((s) => s.includes('trmv/src'))).toEqual([]);
  });

  it.each([
    ['la-doctor', 'living_architecture'],
    ['trmv-doctor', 'trmv'],
  ])('installed with trmv, %s --contract-hash prints the PyPI twin hash', (doctor, module) => {
    const proc = spawnSync(join(PREFIX, 'bin', doctor), ['--contract-hash'], {
      cwd: TMP,
      encoding: 'utf8',
    });
    expect(proc.status, proc.stderr).toBe(0);
    const pkg = module === 'trmv' ? 'trmv' : 'la';
    const hash = readFileSync(
      join(REPO_ROOT, 'python', pkg, 'src', module, 'contract', 'data', 'CONTRACT_HASH'),
      'utf8',
    );
    expect(proc.stdout).toBe(hash);
  });

  it('imports type-rename-move only through its exported subpaths', () => {
    const exported = new Set(trmvSubpaths().filter((s) => s !== 'type-rename-move'));
    expect(specifiers().filter((s) => s.split('/')[0] === 'type-rename-move' && !exported.has(s))).toEqual([]);
  });

  it('resolves every exported subpath of type-rename-move from the installed tarballs', () => {
    for (const specifier of trmvSubpaths()) {
      const proc = spawnSync(process.execPath, ['--input-type=module', '-e', `await import(${JSON.stringify(specifier)});`], {
        cwd: join(PREFIX, 'lib', 'node_modules', 'living-architecture'),
        encoding: 'utf8',
      });
      expect(proc.status, `${specifier}: ${proc.stderr}`).toBe(0);
    }
  });

  it('declares its dependency on type-rename-move', () => {
    const manifest = JSON.parse(readFileSync(join(UNPACKED, 'package', 'package.json'), 'utf8'));
    expect(manifest.dependencies['type-rename-move']).toMatch(/^~\d+\.\d+\.0$/);
  });
});
