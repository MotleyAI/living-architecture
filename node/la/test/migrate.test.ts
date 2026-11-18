// la-arch-migrate: all-or-nothing writes under injected filesystem failures, and the verification guard.
import {
  chmodSync,
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
import { dirname, join, relative, resolve, sep } from 'node:path';
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest';
import {
  MigrateError,
  type MigrationStep,
  STEPS,
  type Transaction,
  migrate,
  run as runMigrate,
} from '../src/c4/migrate.js';
import { compareVersions, currentFormat, releasedFormats } from '../src/config/index.js';
import { message } from '../src/contract/index.js';

const faults = vi.hoisted(() => ({
  root: '',
  failAt: -1,
  after: false,
  failFrom: false,
  skewRoot: '',
  unreadable: '',
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
    const index = faults.ops.length - 1;
    return faults.failAt >= 0 && (faults.failFrom ? index >= faults.failAt : index === faults.failAt);
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
    readFileSync: (file: unknown, ...rest: unknown[]) => {
      const path = mine(file);
      if (path && faults.unreadable && relative(faults.root, path) === faults.unreadable) throw injected('read', path);
      return (actual.readFileSync as (...args: unknown[]) => unknown)(file, ...rest);
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
  const { resolve: resolvePath } = await import('node:path');
  return {
    ...actual,
    parseViews: (root: string, model: Parameters<typeof actual.parseViews>[1]) => {
      const parsed = actual.parseViews(root, model);
      return faults.skewRoot && resolvePath(root) !== faults.skewRoot
        ? { ...parsed, findings: [...parsed.findings, 'skewed'] }
        : parsed;
    },
  };
});

const SPEC = 'specification {\n  element system\n  element node\n}\n';
const PYTHON = "model {\n  python = system 'Python' {\n    core = node 'Core'\n    db = node 'DB'\n    core -> db\n  }\n}\n";
const VIEWS = 'views {\n  view land of python {\n    include *\n  }\n}\n';
const MISMATCH = 'la-arch-migrate: the merged files would not parse to the same model and views; nothing written\n';
const CONFIG = 'living-architecture.yaml';
const UNVERSIONED = '# repo config\ntracker: linear\n';

function legacyRepo(where: string, views: boolean): string {
  const repo = join(where, 'repo');
  mkdirSync(join(repo, 'architecture', 'model'), { recursive: true });
  writeFileSync(join(repo, 'architecture', 'model', 'specification.c4'), SPEC);
  writeFileSync(join(repo, 'architecture', 'model', 'python.c4'), PYTHON);
  // Non-default modes, so a rollback that loses them changes the snapshot.
  for (const name of ['specification.c4', 'python.c4']) chmodSync(join(repo, 'architecture', 'model', name), 0o600);
  chmodSync(join(repo, 'architecture', 'model'), 0o700);
  writeFileSync(join(repo, 'architecture', 'index.yaml'), 'python:\n  root_package: pkg\n');
  writeFileSync(join(repo, CONFIG), UNVERSIONED);
  if (views) writeFileSync(join(repo, 'architecture', 'views.c4'), VIEWS);
  return repo;
}

const ARC42_PYTHON = PYTHON.replace(
  "    core = node 'Core'\n",
  "    core = node 'Core' {\n      metadata {\n        arc42 'architecture/core.arc42.md'\n      }\n    }\n",
);
const ARC42_DONE = PYTHON.replace("    core = node 'Core'\n", "    core = node 'Core' {\n    }\n");
const ARC42_INDEX =
  'python:\n  root_package: pkg  # kept\n' +
  'cross_cutting_arc42:\n- architecture/rules/rules.arc42.md\n' +
  'diagrams:\n  architecture/core.arc42.md: [land]\n';
const ARC42_REPORT =
  'moved architecture/core.arc42.md to architecture/python.core.arc42.md\n' +
  'moved architecture/rules/rules.arc42.md to architecture/rules.arc42.md\n';

/** A repo whose model sets an arc42 key and whose index lists a nested cross-cutting doc. */
function arc42Repo(where: string, legacy: boolean): string {
  const repo = join(where, 'repo');
  const files: Record<string, string> = {
    'architecture/index.yaml': ARC42_INDEX,
    'architecture/views.c4': VIEWS,
    'architecture/core.arc42.md': '# Core\n',
    'architecture/rules/rules.arc42.md': '# Rules\n',
    ...(legacy
      ? { 'architecture/model/specification.c4': SPEC, 'architecture/model/python.c4': ARC42_PYTHON }
      : { 'architecture/model.c4': SPEC + ARC42_PYTHON }),
  };
  for (const [rel, text] of Object.entries({ ...files, [CONFIG]: UNVERSIONED })) {
    mkdirSync(dirname(join(repo, rel)), { recursive: true });
    writeFileSync(join(repo, rel), text);
    // Non-default modes, so a rollback that loses them changes the snapshot.
    chmodSync(join(repo, rel), 0o600);
  }
  return repo;
}

const REPOS: Record<string, (where: string) => string> = {
  'views-created': (where) => legacyRepo(where, false),
  'views-kept': (where) => legacyRepo(where, true),
  'arc42-canonical': (where) => arc42Repo(where, false),
  'arc42-legacy': (where) => arc42Repo(where, true),
};

/** Every directory's mode and every file's mode and bytes under `root`. */
function snapshot(root: string): { dirs: Record<string, number>; files: Record<string, string> } {
  const dirs: Record<string, number> = {};
  const files: Record<string, string> = {};
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir).sort()) {
      const path = join(dir, name);
      const rel = relative(root, path).split(sep).join('/');
      const stats = statSync(path);
      if (stats.isDirectory()) {
        dirs[rel] = stats.mode & 0o7777;
        walk(path);
      } else {
        files[rel] = `${stats.mode & 0o7777}:${readFileSync(path).toString('base64')}`;
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

function armed(root: string, failAt: number, after: boolean, failFrom = false): void {
  Object.assign(faults, { root: resolve(root), failAt, after, failFrom, ops: [] });
}

/** The directories and files that differ between two snapshots. */
function changedPaths(before: ReturnType<typeof snapshot>, after: ReturnType<typeof snapshot>): string[] {
  const differing = (a: Record<string, unknown>, b: Record<string, unknown>): string[] =>
    [...new Set([...Object.keys(a), ...Object.keys(b)])].filter((rel) => a[rel] !== b[rel]);
  return [...differing(before.dirs, after.dirs), ...differing(before.files, after.files)].sort();
}

describe('la-arch-migrate', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-migrate-'));
  afterEach(() => {
    Object.assign(faults, { root: '', failAt: -1, after: false, failFrom: false, skewRoot: '', unreadable: '', ops: [] });
    vi.restoreAllMocks();
  });
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  it.each(Object.entries(REPOS))('leaves the repo unchanged when any mutation fails (%s)', (label, make) => {
    const output = capture();
    const probe = make(join(tmp, `${label}-probe`));
    armed(probe, -1, false);
    expect(runMigrate(probe)).toBe(0);
    const ops = [...faults.ops];
    faults.root = '';
    output();
    expect(ops.length).toBeGreaterThan(0);
    if (label !== 'views-created') expect(ops).not.toContainEqual(['open', 'architecture/views.c4']);
    ops.forEach(([op, path], failAt) => {
      for (const after of op === 'open' ? [false, true] : [false]) {
        const repo = make(join(tmp, `${label}-${failAt}-${after}`));
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

  /** The mutations of one successful migration of a legacy repo without views. */
  function recordedOps(label: string): [string, string][] {
    const output = capture();
    const probe = legacyRepo(join(tmp, `${label}-probe`), false);
    armed(probe, -1, false);
    expect(runMigrate(probe)).toBe(0);
    const ops = [...faults.ops];
    faults.root = '';
    output();
    return ops;
  }

  it('replaces the config last, from a temp file beside it', () => {
    const ops = recordedOps('last');
    const [op, path] = ops[ops.length - 1] ?? ['', ''];
    expect(op).toBe('rename');
    expect(path.includes('/') || path === CONFIG).toBe(false);
    expect(ops.slice(0, -1)).toContainEqual(['open', path]);
    expect(ops.slice(0, -1).filter(([, p]) => p === CONFIG)).toEqual([]);
  });

  it('names every path a failed restore left changed', () => {
    const ops = recordedOps('restore');
    let namedAny = false;
    ops.forEach((_, failAt) => {
      const output = capture();
      const repo = legacyRepo(join(tmp, `restore-${failAt}`), false);
      const before = snapshot(repo);
      armed(repo, failAt, false, true);
      const code = runMigrate(repo);
      faults.root = '';
      const { out, err } = output();
      const left = changedPaths(before, snapshot(repo));
      expect([code, out], String(failAt)).toEqual([2, '']);
      expect(err, String(failAt)).toMatch(/^la-arch-migrate: /);
      expect(left.filter((rel) => !err.includes(rel)), err).toEqual([]);
      expect(err.includes('left changed'), err).toBe(left.length > 0);
      namedAny ||= left.length > 0;
    });
    expect(namedAny).toBe(true);
  });

  it('removes the emptied model directory', () => {
    const output = capture();
    const repo = legacyRepo(join(tmp, 'success'), true);
    expect(runMigrate(repo)).toBe(0);
    expect(output().out).toBe(
      'wrote architecture/model.c4\n' +
        'wrote living-architecture.yaml\n' +
        'deleted architecture/model/python.c4\n' +
        'deleted architecture/model/specification.c4\n' +
        'deleted architecture/model\n',
    );
    expect(existsSync(join(repo, 'architecture', 'model'))).toBe(false);
    expect(readFileSync(join(repo, 'architecture', 'model.c4'), 'utf8')).toBe(SPEC + PYTHON);
    expect(readFileSync(join(repo, CONFIG), 'utf8')).toBe(`# repo config\nformat: ${currentFormat()}\ntracker: linear\n`);
  });

  it.each(Object.entries(REPOS))('writes nothing when the staged files would parse differently (%s)', (label, make) => {
    const output = capture();
    const repo = make(join(tmp, `mismatch-${label}`));
    const before = snapshot(repo);
    faults.skewRoot = resolve(repo);
    expect(runMigrate(repo)).toBe(2);
    expect(output()).toEqual({ out: '', err: MISMATCH });
    expect(snapshot(repo)).toEqual(before);
  });

  it('converts arc42 keys in a canonical repo', () => {
    const output = capture();
    const repo = arc42Repo(join(tmp, 'arc42-canonical'), false);
    expect(runMigrate(repo)).toBe(0);
    expect(output().out).toBe('wrote architecture/model.c4\nwrote architecture/index.yaml\nwrote living-architecture.yaml\n' + ARC42_REPORT);
    const read = (rel: string) => readFileSync(join(repo, rel), 'utf8');
    expect(read('architecture/model.c4')).toBe(SPEC + ARC42_DONE);
    expect(read('architecture/index.yaml')).toBe(
      ARC42_INDEX.replace('architecture/rules/rules.arc42.md', 'architecture/rules.arc42.md').replace(
        'architecture/core.arc42.md:',
        'architecture/python.core.arc42.md:',
      ),
    );
    expect(read('architecture/python.core.arc42.md')).toBe('# Core\n');
    expect(read('architecture/rules.arc42.md')).toBe('# Rules\n');
    expect(existsSync(join(repo, 'architecture', 'core.arc42.md'))).toBe(false);
    expect(statSync(join(repo, 'architecture', 'rules')).isDirectory()).toBe(true);
  });

  it('converts the legacy layout and arc42 keys in one run, then has nothing to migrate', () => {
    const output = capture();
    const repo = arc42Repo(join(tmp, 'arc42-legacy'), true);
    expect(runMigrate(repo)).toBe(0);
    expect(output().out).toBe(
      'wrote architecture/model.c4\nwrote architecture/index.yaml\nwrote living-architecture.yaml\n' +
        ARC42_REPORT +
        'deleted architecture/model/python.c4\ndeleted architecture/model/specification.c4\ndeleted architecture/model\n',
    );
    expect(readFileSync(join(repo, 'architecture', 'model.c4'), 'utf8')).toBe(SPEC + ARC42_DONE);
    const before = snapshot(repo);
    expect(runMigrate(repo)).toBe(0);
    expect(output().out).toMatch(/^nothing to migrate: /);
    expect(snapshot(repo)).toEqual(before);
  });
});

// ---- the chain of steps keyed by source format, with a fake registry and format list

const [F1, F2, F3] = ['1.0.0', '2.0.0', '3.0.0'] as const;
type Apply = (root: string, tx: Transaction) => void;
const noop: Apply = () => {};
const wrote = (rel: string): string => `wrote ${rel}`;

/** One step per apply: the unversioned step to formats[0], then each released format to the next. */
function chain(applies: Apply[], formats: string[], log?: (string | null)[]): MigrationStep[] {
  const sources: (string | null)[] = [null, ...formats.slice(0, -1)];
  return applies.map((apply, i) => ({
    source: sources[i] ?? null,
    target: formats[i] as string,
    apply: (root: string, tx: Transaction) => {
      log?.push(sources[i] ?? null);
      apply(root, tx);
    },
  }));
}

function chainRepo(where: string, configText: string, files: Record<string, string> = {}): string {
  const root = join(where, 'repo');
  mkdirSync(root, { recursive: true });
  writeFileSync(join(root, CONFIG), configText);
  for (const [rel, text] of Object.entries(files)) writeFileSync(join(root, rel), text);
  return root;
}

/** The error `fn` throws. */
function thrown(fn: () => unknown): Error {
  try {
    fn();
  } catch (error) {
    return error as Error;
  }
  throw new Error('nothing was thrown');
}

const ROLLBACK_FILES = { 'moved.txt': 'moved\n', 'doomed.txt': 'doomed\n', 'replaced.txt': 'replaced\n' };

function rollbackRepo(where: string): string {
  const root = chainRepo(where, UNVERSIONED, ROLLBACK_FILES);
  // Non-default modes, so a rollback that loses them changes the snapshot.
  const modes: Record<string, number> = { 'moved.txt': 0o600, 'doomed.txt': 0o640, 'replaced.txt': 0o604, [CONFIG]: 0o640 };
  for (const [rel, mode] of Object.entries(modes)) chmodSync(join(root, rel), mode);
  mkdirSync(join(root, 'gone'));
  chmodSync(join(root, 'gone'), 0o750);
  return root;
}

const everyChange: Apply = (_root, tx) => {
  tx.create('created.txt', 'created\n');
  tx.move('moved.txt', 'arrived.txt');
  tx.delete('doomed.txt');
  tx.replace('replaced.txt', 'new\n');
  tx.removeDir('gone');
};

describe('la-arch-migrate step chain', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-migrate-chain-'));
  let n = 0;
  const fresh = (): string => join(tmp, String(n++));
  afterEach(() => {
    Object.assign(faults, { root: '', failAt: -1, after: false, failFrom: false, skewRoot: '', unreadable: '', ops: [] });
    vi.restoreAllMocks();
  });
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  it('has every released older format step to the next one', () => {
    const formats = releasedFormats();
    expect(STEPS.filter((s) => s.source === null).map((s) => s.target)).toEqual([formats[0]]);
    const versioned = STEPS.filter((s) => s.source !== null).map((s) => [s.source, s.target]);
    const pairs = formats.slice(1).map((target, i) => [formats[i], target]);
    const order = (a: unknown[], b: unknown[]): number => compareVersions(String(a[0]), String(b[0]));
    expect(versioned.sort(order)).toEqual(pairs);
  });

  it('runs every step on an unversioned repo, each on what the earlier left', () => {
    const root = chainRepo(fresh(), 'tracker: linear\n');
    const log: (string | null)[] = [];
    const second: Apply = (where, tx) => {
      expect(readFileSync(join(where, 'a.txt'), 'utf8')).toBe('a\n');
      tx.create('b.txt', 'b\n');
    };
    const steps = chain([(_r, tx) => tx.create('a.txt', 'a\n'), second], [F1, F2], log);
    expect(migrate(root, { steps, formats: [F1, F2] })).toEqual([wrote('a.txt'), wrote('b.txt'), wrote(CONFIG)]);
    expect(log).toEqual([null, F1]);
    expect(readFileSync(join(root, CONFIG), 'utf8')).toBe(`format: ${F2}\ntracker: linear\n`);
  });

  it.each([
    [F1, [F1, F2]],
    [F2, [F2]],
  ])('runs only the steps from a released older format (%s)', (declared, ran) => {
    const root = chainRepo(fresh(), `tracker: linear\nformat: ${declared}  # repo format\n`);
    const log: (string | null)[] = [];
    const steps = chain([noop, noop, noop], [F1, F2, F3], log);
    expect(migrate(root, { steps, formats: [F1, F2, F3] })).toEqual([wrote(CONFIG)]);
    expect(log).toEqual(ran);
    expect(readFileSync(join(root, CONFIG), 'utf8')).toBe(`tracker: linear\nformat: ${F3}  # repo format\n`);
  });

  it.each(['2.0.0', '0.5.0'])('refuses the unreleased older format %s', (declared) => {
    const root = chainRepo(fresh(), `format: ${declared}\n`);
    const before = snapshot(root);
    const log: (string | null)[] = [];
    const steps = chain([(_r, tx) => tx.create('a.txt', 'a\n'), (_r, tx) => tx.create('b.txt', 'b\n')], [F1, F3], log);
    const error = thrown(() => migrate(root, { steps, formats: [F1, F3] }));
    expect(error).toBeInstanceOf(MigrateError);
    expect(error.message).toBe(message('arch-migrate.unknown-format', { declared, current: F3 }));
    expect(log).toEqual([]);
    expect(snapshot(root)).toEqual(before);
  });

  it('has nothing to migrate at the current format of the injected list', () => {
    const root = chainRepo(fresh(), `format: ${F2}\n`);
    const log: (string | null)[] = [];
    const steps = chain([noop, noop], [F1, F2], log);
    expect(migrate(root, { steps, formats: [F1, F2] })).toEqual([message('arch-migrate.nothing', { current: F2 })]);
    expect(log).toEqual([]);
  });

  it('refuses a format newer than the injected list', () => {
    const root = chainRepo(fresh(), `format: ${F3}\n`);
    const error = thrown(() => migrate(root, { steps: chain([noop, noop], [F1, F2]), formats: [F1, F2] }));
    expect(error.message).toBe(message('format.newer', { declared: F3, current: F2 }));
  });

  it.each(['{tracker: linear}\n', `format:\n  ${F1}\n`])('decides the stamp before any step writes (%j)', (text) => {
    const root = chainRepo(fresh(), text, { 'kept.txt': 'kept\n' });
    const before = snapshot(root);
    const steps = chain([(_r, tx) => tx.create('a.txt', 'a\n'), (_r, tx) => tx.delete('kept.txt')], [F1, F2]);
    const error = thrown(() => migrate(root, { steps, formats: [F1, F2] }));
    expect(error.message).toBe(message('arch-migrate.stamp-mismatch', { current: F2 }));
    expect(snapshot(root)).toEqual(before);
  });

  // ---- one transaction and one rollback across the chain

  const mismatch = (): string => MISMATCH.replace(/^la-arch-migrate: /, '').replace(/\n$/, '');
  it.each<[string, Apply, boolean, () => string]>([
    [
      'planning',
      () => {
        throw new MigrateError('the second step refuses');
      },
      true,
      () => 'the second step refuses',
    ],
    [
      'verification',
      () => {
        throw new MigrateError(message('arch-migrate.mismatch'));
      },
      true,
      mismatch,
    ],
    [
      'application',
      (_root, tx) => {
        tx.create('later.txt', 'later\n');
        tx.replace('arrived.txt', 'rewritten\n');
        tx.move('missing.txt', 'elsewhere.txt');
      },
      false,
      () => 'missing.txt',
    ],
  ])('rolls back the earlier steps when a later one fails in %s', (_, second, refusal, text) => {
    const root = rollbackRepo(fresh());
    const before = snapshot(root);
    const error = thrown(() => migrate(root, { steps: chain([everyChange, second], [F1, F2]), formats: [F1, F2] }));
    if (refusal) {
      expect(error).toBeInstanceOf(MigrateError);
      expect(error.message).toBe(text());
    } else {
      expect(error).not.toBeInstanceOf(MigrateError);
      expect(error.message).toContain(text());
    }
    expect(snapshot(root)).toEqual(before);
  });

  it('rolls back the chain when a step throws an unexpected error', () => {
    const root = rollbackRepo(fresh());
    const before = snapshot(root);
    const crash: Apply = (_root, tx) => {
      tx.create('later.txt', 'later\n');
      throw new TypeError('the second step crashes');
    };
    const error = thrown(() => migrate(root, { steps: chain([everyChange, crash], [F1, F2]), formats: [F1, F2] }));
    expect(error).toBeInstanceOf(TypeError);
    expect(error.message).toBe('the second step crashes');
    expect(snapshot(root)).toEqual(before);
  });

  it('restores a read-only replaced file on rollback', () => {
    const root = chainRepo(fresh(), UNVERSIONED, { 'locked.txt': 'locked\n' });
    chmodSync(join(root, 'locked.txt'), 0o444);
    const before = snapshot(root);
    const refuse: Apply = () => {
      throw new MigrateError('the second step refuses');
    };
    const steps = chain([(_root, tx) => tx.replace('locked.txt', 'new\n'), refuse], [F1, F2]);
    expect(thrown(() => migrate(root, { steps, formats: [F1, F2] })).message).toBe('the second step refuses');
    expect(snapshot(root)).toEqual(before);
  });

  it('names a path whose restore cannot be verified, having inspected the rest', () => {
    const root = rollbackRepo(fresh());
    const before = snapshot(root);
    armed(root, -1, false);
    const unreadable: Apply = () => {
      faults.unreadable = 'replaced.txt';
      throw new MigrateError('the second step refuses');
    };
    const error = thrown(() => migrate(root, { steps: chain([everyChange, unreadable], [F1, F2]), formats: [F1, F2] }));
    faults.unreadable = '';
    expect(error.message).toBe(
      message('arch-migrate.rollback-failed', { error: 'the second step refuses', paths: 'replaced.txt' }),
    );
    expect(snapshot(root)).toEqual(before);
  });

  /** The mutations of one successful run of the fake chain. */
  function recordedChainOps(): [string, string][] {
    const probe = rollbackRepo(fresh());
    armed(probe, -1, false);
    migrate(probe, { steps: chain([everyChange, noop], [F1, F2]), formats: [F1, F2] });
    const ops = [...faults.ops];
    faults.root = '';
    expect(ops).toContainEqual(['rename', 'moved.txt']);
    return ops;
  }

  it('leaves the repo unchanged when any mutation of a chain fails', () => {
    const ops = recordedChainOps();
    expect(ops[ops.length - 1]?.[0]).toBe('rename');
    ops.forEach(([op, path], failAt) => {
      for (const after of op === 'open' ? [false, true] : [false]) {
        const root = rollbackRepo(fresh());
        const before = snapshot(root);
        armed(root, failAt, after);
        thrown(() => migrate(root, { steps: chain([everyChange, noop], [F1, F2]), formats: [F1, F2] }));
        faults.root = '';
        expect(snapshot(root), `${failAt} ${op} ${path} after=${after}`).toEqual(before);
      }
    });
  });

  it('names every path a failed restore of a chain left changed', () => {
    const ops = recordedChainOps();
    let namedAny = false;
    ops.forEach((_, failAt) => {
      const root = rollbackRepo(fresh());
      const before = snapshot(root);
      armed(root, failAt, false, true);
      const error = thrown(() => migrate(root, { steps: chain([everyChange, noop], [F1, F2]), formats: [F1, F2] }));
      faults.root = '';
      const left = changedPaths(before, snapshot(root));
      expect(left.filter((rel) => !error.message.includes(rel)), error.message).toEqual([]);
      expect(error.message.includes('left changed'), error.message).toBe(left.length > 0);
      namedAny ||= left.length > 0;
    });
    expect(namedAny).toBe(true);
  });

  // ---- the net-effect report

  const NET_EFFECT: [string, Record<string, string>, Apply, Apply, string[]][] = [
    ['one move', { a: 'A\n' }, (_r, tx) => tx.move('a', 'b'), noop, [wrote(CONFIG), 'moved a to b']],
    [
      'consecutive moves composed',
      { a: 'A\n' },
      (_r, tx) => tx.move('a', 'b'),
      (_r, tx) => tx.move('b', 'c'),
      [wrote(CONFIG), 'moved a to c'],
    ],
    ['moved back', { a: 'A\n' }, (_r, tx) => tx.move('a', 'b'), (_r, tx) => tx.move('b', 'a'), [wrote(CONFIG)]],
    [
      'moved then deleted',
      { a: 'A\n' },
      (_r, tx) => tx.move('a', 'b'),
      (_r, tx) => tx.delete('b'),
      [wrote(CONFIG), 'deleted a'],
    ],
    ['created then deleted', {}, (_r, tx) => tx.create('x', 'X\n'), (_r, tx) => tx.delete('x'), [wrote(CONFIG)]],
    [
      'rewritten then deleted',
      { x: 'X\n' },
      (_r, tx) => tx.replace('x', 'Y\n'),
      (_r, tx) => tx.delete('x'),
      [wrote(CONFIG), 'deleted x'],
    ],
    [
      'rewritten twice',
      { x: 'X\n' },
      (_r, tx) => tx.replace('x', 'Y\n'),
      (_r, tx) => tx.replace('x', 'Z\n'),
      [wrote('x'), wrote(CONFIG)],
    ],
    [
      'moved then rewritten',
      { a: 'A\n' },
      (_r, tx) => tx.move('a', 'b'),
      (_r, tx) => tx.replace('b', 'B\n'),
      [wrote('b'), wrote(CONFIG), 'moved a to b'],
    ],
    [
      'moved source recreated',
      { a: 'A\n' },
      (_r, tx) => tx.move('a', 'b'),
      (_r, tx) => tx.create('a', 'new\n'),
      [wrote('a'), wrote(CONFIG), 'moved a to b'],
    ],
  ];

  it.each(NET_EFFECT)('reports the net effect: %s', (_, files, first, second, report) => {
    const root = chainRepo(fresh(), UNVERSIONED, files);
    const log: (string | null)[] = [];
    expect(migrate(root, { steps: chain([first, second], [F1, F2], log), formats: [F1, F2] })).toEqual(report);
    expect(log).toEqual([null, F1]);
    expect(Object.keys(snapshot(root).files).filter((rel) => rel.endsWith('.tmp'))).toEqual([]);
  });

  it('reports writes, then moves, then deletes', () => {
    const root = chainRepo(fresh(), UNVERSIONED, { d: 'D\n', m: 'M\n' });
    mkdirSync(join(root, 'e'));
    const first: Apply = (_r, tx) => {
      tx.delete('d');
      tx.move('m', 'n');
      tx.create('w1', '1\n');
    };
    const second: Apply = (_r, tx) => {
      tx.removeDir('e');
      tx.create('w2', '2\n');
    };
    expect(migrate(root, { steps: chain([first, second], [F1, F2]), formats: [F1, F2] })).toEqual([
      wrote('w1'),
      wrote('w2'),
      wrote(CONFIG),
      'moved m to n',
      'deleted d',
      'deleted e',
    ]);
  });
});
