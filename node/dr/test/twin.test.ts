// Twin discovery: the invoking twin's own `trmv-doctor` is never probed; without one, nothing is skipped. The entry
// point (`process.argv[1]`) and every spawned executable are set up by the test.
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, join } from 'node:path';
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { contractHash } from '../src/contract/index.js';
import { VERSION } from '../src/index.js';

const TMP = mkdtempSync(join(tmpdir(), 'la-twin-'));
const PYTHON_IDENTITY = `python ${VERSION} ${contractHash()}`;
const saved = { argv1: process.argv[1], path: process.env.PATH, forwarded: process.env.LA_FORWARDED };
let root = '';
let log = '';

function executable(path: string, body: string): void {
  writeFileSync(path, `#!/bin/sh\n${body}`);
  chmodSync(path, 0o755);
}

/** A directory whose `trmv-doctor --twin` qualifies as the Python twin; each run appends `<tag>:<command>` to the log. */
function stubTwin(dir: string, tag: string, doctorName = 'trmv-doctor'): string {
  mkdirSync(dir, { recursive: true });
  executable(join(dir, doctorName), `echo '${tag}:trmv-doctor' >> '${log}'\necho '${PYTHON_IDENTITY}'\n`);
  executable(join(dir, 'trmv-compliance'), `echo '${tag}:trmv-compliance' >> '${log}'\n`);
  return dir;
}

async function forwardFrom(entry: string, path: string[]): Promise<{ status: number; spawns: string[] }> {
  process.argv[1] = entry;
  process.env.PATH = [...path, ...(saved.path ?? '').split(delimiter)].join(delimiter);
  vi.resetModules();
  const { forward } = await import('../src/twin/index.js');
  const status = forward('trmv-compliance', 'python', [], root);
  return { status, spawns: existsSync(log) ? readFileSync(log, 'utf8').trim().split('\n') : [] };
}

beforeEach(() => {
  root = mkdtempSync(join(TMP, 'case-'));
  log = join(root, 'spawns.log');
  delete process.env.LA_FORWARDED;
});

afterEach(() => {
  process.argv[1] = saved.argv1 ?? '';
  process.env.PATH = saved.path;
  if (saved.forwarded !== undefined) process.env.LA_FORWARDED = saved.forwarded;
});

afterAll(() => rmSync(TMP, { recursive: true, force: true }));

describe('twin discovery', () => {
  it('skips the directory whose trmv-doctor is the entry point sibling, even if it would qualify', async () => {
    const own = stubTwin(join(root, 'own'), 'own', 'trmv-doctor.js');
    writeFileSync(join(own, 'trmv-compliance.js'), '');
    const links = join(root, 'links');
    mkdirSync(links);
    symlinkSync(join(own, 'trmv-doctor.js'), join(links, 'trmv-doctor'));
    const other = stubTwin(join(root, 'other'), 'other');
    expect(await forwardFrom(join(own, 'trmv-compliance.js'), [links, other])).toEqual({
      status: 0,
      spawns: ['other:trmv-doctor', 'other:trmv-compliance'],
    });
  });

  it.each(['missing', 'dangling', 'directory', 'entry-missing'])(
    'skips nothing without a resolvable own trmv-doctor (%s)',
    async (sibling) => {
      const first = stubTwin(join(root, 'first'), 'first');
      const second = stubTwin(join(root, 'second'), 'second');
      const entry = join(first, 'trmv-compliance.js');
      if (sibling !== 'entry-missing') writeFileSync(entry, '');
      if (sibling === 'dangling') symlinkSync(join(root, 'nowhere'), join(first, 'trmv-doctor.js'));
      if (sibling === 'directory') mkdirSync(join(first, 'trmv-doctor.js'));
      expect(await forwardFrom(entry, [first, second])).toEqual({
        status: 0,
        spawns: ['first:trmv-doctor', 'first:trmv-compliance'],
      });
    },
  );
});
