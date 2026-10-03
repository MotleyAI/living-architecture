// The vendored snapshot and the contract hash, through src/contract/index.ts: computeHash(dir): string,
// contractHash(): string (the recorded hash), snapshotDir(): string, schema(name), manifest() (cli.yaml
// `commands`), language(id) (a languages.yaml entry).
import { createHash } from 'node:crypto';
import {
  chmodSync,
  cpSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { computeHash, contractHash, language, manifest, schema, snapshotDir } from '../src/contract/index.js';
import { HASH_FILE, SHARED, SNAPSHOT, loadYamlFile, plain, readJson } from './helpers.js';

const TMP = mkdtempSync(join(tmpdir(), 'la-contract-'));
afterAll(() => rmSync(TMP, { recursive: true, force: true }));

function sharedCopy(): string {
  const dir = mkdtempSync(join(TMP, 'shared-'));
  cpSync(SHARED, dir, { recursive: true });
  return dir;
}

describe('vendored snapshot', () => {
  it('records the hash of shared/', () => {
    const recorded = readFileSync(join(SNAPSHOT, HASH_FILE), 'utf8');
    expect(recorded, 'the snapshot hash is stale; run scripts/sync-shared').toBe(`${computeHash(SHARED)}\n`);
    expect(contractHash()).toBe(computeHash(SHARED));
  });

  it('is what the contract loads from', () => {
    expect(realpathSync(snapshotDir())).toBe(realpathSync(SNAPSHOT));
  });

  it('serves the shared data files', () => {
    expect(plain(schema('living-architecture'))).toEqual(readJson(join(SHARED, 'schema', 'living-architecture.schema.json')));
    expect(Object.keys(plain(manifest())).sort()).toEqual(Object.keys(loadYamlFile(join(SHARED, 'cli.yaml')).commands).sort());
    expect(plain(language('typescript')).test_globs).toEqual(loadYamlFile(join(SHARED, 'languages.yaml')).typescript.test_globs);
  });
});

describe('computeHash', () => {
  it('follows the README formula: byte-ordered POSIX paths, executable bit, length, bytes', () => {
    const dir = mkdtempSync(join(TMP, 'tree-'));
    mkdirSync(join(dir, 'a'));
    writeFileSync(join(dir, 'a', 'b'), 'x');
    writeFileSync(join(dir, 'a-b'), 'yz\n');
    writeFileSync(join(dir, 'Z.sh'), '');
    chmodSync(join(dir, 'Z.sh'), 0o755);
    writeFileSync(join(dir, HASH_FILE), 'ignored\n');
    const stream = 'Z.sh\x001\x000\x00' + 'a-b\x000\x003\x00yz\n' + 'a/b\x000\x001\x00x';
    expect(computeHash(dir)).toBe(createHash('sha256').update(stream).digest('hex'));
  });

  it.each(['bytes', 'mode', 'path'])('changes when a file changes its %s', (change) => {
    const dir = sharedCopy();
    const target = join(dir, 'findings.yaml');
    if (change === 'bytes') writeFileSync(target, Buffer.concat([readFileSync(target), Buffer.from('\n')]));
    if (change === 'mode') chmodSync(target, statSync(target).mode ^ 0o100);
    if (change === 'path') renameSync(target, join(dir, 'findings2.yaml'));
    expect(computeHash(dir)).not.toBe(computeHash(SHARED));
  });

  it('ignores non-executable mode bits', () => {
    const dir = sharedCopy();
    const target = join(dir, 'findings.yaml');
    chmodSync(target, statSync(target).mode ^ 0o020);
    expect(computeHash(dir)).toBe(computeHash(SHARED));
  });

  it('ignores the hash file itself', () => {
    const dir = sharedCopy();
    writeFileSync(join(dir, HASH_FILE), 'anything\n');
    expect(computeHash(dir)).toBe(computeHash(SHARED));
  });
});
