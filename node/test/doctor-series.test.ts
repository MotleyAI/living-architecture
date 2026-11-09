// la-doctor --plugin's series comparison against a prerelease-style installed version, which no installed twin has.
import { chmodSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { runChecks } from '../src/doctor/index.js';

vi.mock('../src/index.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/index.js')>()),
  VERSION: '1.2.3-rc.1',
}));

/** A directory outside git holding a plugin whose plugin.json declares `version`; returns [root, plugin dir]. */
function pluginAt(version: string): [string, string] {
  const root = mkdtempSync(join(tmpdir(), 'la-doctor-series-'));
  mkdirSync(join(root, 'plugin', '.claude-plugin'), { recursive: true });
  writeFileSync(join(root, 'plugin', '.claude-plugin', 'plugin.json'), JSON.stringify({ version }));
  return [root, join(root, 'plugin')];
}

describe('la-doctor series with a prerelease-style installed version', () => {
  beforeEach(() => {
    const bin = mkdtempSync(join(tmpdir(), 'la-doctor-bin-'));
    for (const exe of ['git', 'gh']) {
      writeFileSync(join(bin, exe), '#!/bin/sh\nexit 0\n');
      chmodSync(join(bin, exe), 0o755);
    }
    vi.stubEnv('PATH', bin);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it.each(['1.2.0', '1.2.3-rc.1', '01.002.9rc1'])('plugin %s is the installed series', (version) => {
    const [root, plugin] = pluginAt(version);
    expect(runChecks(root, plugin)).toEqual([]);
  });

  it('plugin 1.3.0 is another series', () => {
    const [root, plugin] = pluginAt('1.3.0');
    expect(runChecks(root, plugin)).toEqual([
      'installed la tools are 1.2.3-rc.1, but plugin 1.3.0 needs 1.3.x; reinstall them with: npm install -g living-architecture@1.3.0',
    ]);
  });
});
