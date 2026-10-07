// la-arch-migrate: all-or-nothing writes under injected filesystem failures, and the verification guard.
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative, resolve, sep } from 'node:path';
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest';
import { run as runMigrate } from '../src/c4/migrate.js';

const faults = vi.hoisted(() => ({
  root: '',
  failAt: -1,
  after: false,
  skewViews: false,
  ops: [] as [string, string][],
}));

vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  const { O_WRONLY, O_RDWR, O_CREAT, O_APPEND, O_TRUNC } = actual.constants;
  const writeFlags = O_WRONLY | O_RDWR | O_CREAT | O_APPEND | O_TRUNC;
  const mine = (path: unknown): string | null => {
    if (!faults.root || (typeof path !== 'string' && !(path instanceof URL) && !Buffer.isBuffer(path))) return null;
    const full = resolve(String(path instanceof URL ? path.pathname : path));
    return full === faults.root || full.startsWith(faults.root + '/') ? full : null;
  };
  const hit = (op: string, path: string): boolean => {
    faults.ops.push([op, relative(faults.root, path)]);
    return faults.ops.length - 1 === faults.failAt;
  };
  const injected = (op: string, path: string) => Object.assign(new Error(`injected failure: ${op} ${path}`), { code: 'EIO' });
  const writes = (flag: unknown): boolean =>
    typeof flag === 'number' ? (flag & writeFlags) !== 0 : typeof flag === 'string' && /[wxa+]/.test(flag);
  const flagOf = (options: unknown): unknown =>
    options && typeof options === 'object' && 'flag' in options ? (options as { flag: unknown }).flag : 'w';
  const guard =
    <A extends unknown[], R>(op: string, real: (...args: A) => R, at = 0) =>
    (...args: A): R => {
      const path = mine(args[at]);
      if (path && hit(op, path)) throw injected(op, path);
      return real(...args);
    };
  const wrapped = {
    writeFileSync: (file: unknown, data: unknown, options?: unknown) => {
      const path = mine(file);
      if (path && writes(flagOf(options)) && hit('open', path)) {
        if (faults.after) actual.writeFileSync(file as string, '', options as never);
        throw injected('open', path);
      }
      return actual.writeFileSync(file as string, data as string, options as never);
    },
    appendFileSync: guard('open', actual.appendFileSync),
    openSync: (file: unknown, flags?: unknown, mode?: unknown) => {
      const path = mine(file);
      if (path && writes(flags ?? 'r') && hit('open', path)) {
        if (faults.after) actual.closeSync(actual.openSync(file as string, flags as never, mode as never));
        throw injected('open', path);
      }
      return actual.openSync(file as string, flags as never, mode as never);
    },
    unlinkSync: guard('unlink', actual.unlinkSync),
    rmSync: guard('rm', actual.rmSync),
    rmdirSync: guard('rmdir', actual.rmdirSync),
    mkdirSync: guard('mkdir', actual.mkdirSync),
    renameSync: guard('rename', actual.renameSync),
    copyFileSync: guard('copy', actual.copyFileSync, 1),
  };
  return { ...actual, ...wrapped, default: { ...actual, ...wrapped } };
});

vi.mock('../src/c4/views.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/c4/views.js')>();
  const { existsSync: exists } = await import('node:fs');
  const { join: joinPath } = await import('node:path');
  return {
    ...actual,
    parseViews: (root: string, model: Parameters<typeof actual.parseViews>[1]) => {
      const parsed = actual.parseViews(root, model);
      return faults.skewViews && exists(joinPath(root, 'architecture', 'model.c4'))
        ? { ...parsed, findings: [...parsed.findings, 'skewed'] }
        : parsed;
    },
  };
});

const SPEC = 'specification {\n  element system\n  element node\n}\n';
const PYTHON = "model {\n  python = system 'Python' {\n    core = node 'Core'\n    db = node 'DB'\n    core -> db\n  }\n}\n";
const VIEWS = 'views {\n  view land of python {\n    include *\n  }\n}\n';
const MISMATCH = 'la-arch-migrate: the merged files would not parse to the same model and views; nothing written\n';

function legacyRepo(where: string, views: boolean): string {
  const repo = join(where, 'repo');
  mkdirSync(join(repo, 'architecture', 'model'), { recursive: true });
  writeFileSync(join(repo, 'architecture', 'model', 'specification.c4'), SPEC);
  writeFileSync(join(repo, 'architecture', 'model', 'python.c4'), PYTHON);
  writeFileSync(join(repo, 'architecture', 'index.yaml'), 'python:\n  root_package: pkg\n');
  if (views) writeFileSync(join(repo, 'architecture', 'views.c4'), VIEWS);
  return repo;
}

/** Every directory and every file's bytes under `root`. */
function snapshot(root: string): { dirs: string[]; files: Record<string, string> } {
  const dirs: string[] = [];
  const files: Record<string, string> = {};
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir).sort()) {
      const path = join(dir, name);
      const rel = relative(root, path).split(sep).join('/');
      if (statSync(path).isDirectory()) {
        dirs.push(rel);
        walk(path);
      } else {
        files[rel] = readFileSync(path).toString('base64');
      }
    }
  };
  walk(root);
  return { dirs, files };
}

function capture(): () => { out: string; err: string } {
  const out = vi.spyOn(process.stdout, 'write').mockImplementation(() => true);
  const err = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
  return () => {
    const text = { out: out.mock.calls.map((c) => String(c[0])).join(''), err: err.mock.calls.map((c) => String(c[0])).join('') };
    out.mockClear();
    err.mockClear();
    return text;
  };
}

function armed(root: string, failAt: number, after: boolean): void {
  Object.assign(faults, { root: resolve(root), failAt, after, ops: [] });
}

describe('la-arch-migrate', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-migrate-'));
  afterEach(() => {
    Object.assign(faults, { root: '', failAt: -1, after: false, skewViews: false, ops: [] });
    vi.restoreAllMocks();
  });
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  it.each([
    ['views-created', false],
    ['views-kept', true],
  ])('leaves the repo unchanged when any mutation fails (%s)', (label, views) => {
    const output = capture();
    const probe = legacyRepo(join(tmp, `${label}-probe`), views);
    armed(probe, -1, false);
    expect(runMigrate(probe)).toBe(0);
    const ops = [...faults.ops];
    faults.root = '';
    output();
    expect(ops.length).toBeGreaterThan(0);
    if (views) expect(ops).not.toContainEqual(['open', 'architecture/views.c4']);
    ops.forEach(([op, path], failAt) => {
      for (const after of op === 'open' ? [false, true] : [false]) {
        const repo = legacyRepo(join(tmp, `${label}-${failAt}-${after}`), views);
        const before = snapshot(repo);
        armed(repo, failAt, after);
        const code = runMigrate(repo);
        faults.root = '';
        const { out, err } = output();
        const context = `${failAt} ${op} ${path} after=${after}`;
        expect(code, context).toBe(2);
        expect(out, context).toBe('');
        expect(err, context).toMatch(/^la-arch-migrate: /);
        expect(snapshot(repo), context).toEqual(before);
      }
    });
  });

  it('removes the emptied model directory', () => {
    const output = capture();
    const repo = legacyRepo(join(tmp, 'success'), true);
    expect(runMigrate(repo)).toBe(0);
    expect(output().out).toBe(
      'wrote architecture/model.c4\n' +
        'deleted architecture/model/python.c4\n' +
        'deleted architecture/model/specification.c4\n' +
        'deleted architecture/model\n',
    );
    expect(existsSync(join(repo, 'architecture', 'model'))).toBe(false);
    expect(readFileSync(join(repo, 'architecture', 'model.c4'), 'utf8')).toBe(SPEC + PYTHON);
  });

  it('writes nothing when the merged files would parse differently', () => {
    const output = capture();
    const repo = legacyRepo(join(tmp, 'mismatch'), true);
    const before = snapshot(repo);
    faults.skewViews = true;
    expect(runMigrate(repo)).toBe(2);
    expect(output()).toEqual({ out: '', err: MISMATCH });
    expect(snapshot(repo)).toEqual(before);
  });
});
