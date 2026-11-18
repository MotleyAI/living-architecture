// la's packed tarball reaches dr only through the `deterministic-refactor` package, never through dr's sources.
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { REPO_ROOT } from './helpers.js';

const TIMEOUT = 600_000;
const TMP = mkdtempSync(join(tmpdir(), 'la-pack-la-'));
const UNPACKED = join(TMP, 'unpacked');
const PREFIX = join(TMP, 'prefix');
const SPECIFIER = /(?:from\s*|import\s*\(\s*|require\s*\(\s*)['"]([^'"]+)['"]/g;
const TARBALLS: Record<string, string> = {};

beforeAll(() => {
  const packed = spawnSync('npm', ['pack', '--json', '--pack-destination', TMP, '-w', 'dr', '-w', 'la'], {
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

describe('packed living-architecture', () => {
  it('imports dr by its package name only', () => {
    const all = specifiers();
    expect(all.filter((s) => s.split('/')[0] === 'deterministic-refactor').length).toBeGreaterThan(0);
    expect(all.filter((s) => s.includes('dr/src'))).toEqual([]);
  });

  it.each([
    ['la-doctor', 'living_architecture'],
    ['dr-doctor', 'deterministic_refactor'],
  ])('installed with dr, %s --contract-hash prints the PyPI twin hash', (doctor, module) => {
    const proc = spawnSync(join(PREFIX, 'bin', doctor), ['--contract-hash'], {
      cwd: TMP,
      encoding: 'utf8',
    });
    expect(proc.status, proc.stderr).toBe(0);
    const pkg = module === 'deterministic_refactor' ? 'dr' : 'la';
    const hash = readFileSync(
      join(REPO_ROOT, 'python', pkg, 'src', module, 'contract', 'data', 'CONTRACT_HASH'),
      'utf8',
    );
    expect(proc.stdout).toBe(hash);
  });

  it('declares its dependency on deterministic-refactor', () => {
    const manifest = JSON.parse(readFileSync(join(UNPACKED, 'package', 'package.json'), 'utf8'));
    expect(manifest.dependencies['deterministic-refactor']).toMatch(/^~\d+\.\d+\.0$/);
  });
});
