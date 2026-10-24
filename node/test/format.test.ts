// The declared repo format: version rules, the stamp, the check, and which commands run it.
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { checkFormat, compareVersions, currentFormat, isVersion, stampFormat } from '../src/config/index.js';
import { loadYaml, renderTemplate } from '../src/contract/index.js';
import { run, tempRepo } from './cli-run.js';
import { NODE_ROOT, REPO_ROOT, SHARED, VECTORS, field, loadYamlFile, readJson } from './helpers.js';

// Read with the twin's own YAML profile, so each value has the shape the check receives.
const VECTOR_FILE = loadYaml(readFileSync(join(VECTORS, 'format.yaml'), 'utf8'));
const vector = (key: string): any[] => [...(field(VECTOR_FILE, key) as Iterable<any>)];
const MANIFEST = loadYamlFile(join(SHARED, 'cli.yaml')).commands as Record<string, { format?: string }>;
const CURRENT: string = loadYamlFile(join(SHARED, 'config.yaml')).format;
const FINDINGS = loadYamlFile(join(SHARED, 'findings.yaml')).findings as Record<string, string>;
const CONFIG = 'living-architecture.yaml';

const refusal = (id: string, values: Record<string, unknown> = {}): string =>
  renderTemplate(FINDINGS[id] ?? '', { current: CURRENT, ...values });

function repo(committed?: string | Buffer, local?: string): string {
  const root = mkdtempSync(join(tmpdir(), 'la-format-'));
  if (committed !== undefined) writeFileSync(join(root, CONFIG), committed);
  if (local !== undefined) writeFileSync(join(root, 'living-architecture.local.yaml'), local);
  return root;
}

describe('format versions', () => {
  it('the current format comes from the contract', () => {
    expect(currentFormat()).toBe(CURRENT);
  });

  it.each(vector('valid'))('%s is a version', (value) => {
    expect(isVersion(value)).toBe(true);
  });

  it.each(vector('invalid').map((value) => [JSON.stringify(value instanceof Map ? [...value] : value), value]))(
    '%s is not a version',
    (_, value) => {
      expect(isVersion(value)).toBe(false);
    },
  );

  it.each(vector('compare').map((entry) => [...(entry as Iterable<any>)]))('%s vs %s is %s', (a, b, sign) => {
    expect([compareVersions(a, b), compareVersions(b, a)]).toEqual([Number(sign), -Number(sign)]);
  });

  it('the current format is at most every package version', () => {
    const versions = [
      readJson(join(NODE_ROOT, 'package.json')).version,
      readJson(join(REPO_ROOT, 'plugin', '.claude-plugin', 'plugin.json')).version,
    ];
    for (const version of versions) expect(compareVersions(currentFormat(), version), version).toBeLessThanOrEqual(0);
  });
});

describe('stampFormat', () => {
  const cases = vector('stamp').map((v) => ({
    name: String(field(v, 'name')),
    text: String(field(v, 'text')),
    stamped: field(v, 'stamped') as string | null,
  }));

  it.each(cases)('$name', ({ text, stamped }) => {
    expect(stampFormat(text)).toBe(stamped === null ? null : stamped.replaceAll('<FORMAT>', CURRENT));
  });

  it.each(cases.filter((c) => c.stamped !== null))('$name adds only the format', ({ text }) => {
    const before = loadYaml(text);
    const after = loadYaml(stampFormat(text) ?? '');
    const entries = (value: unknown) => (value instanceof Map ? Object.fromEntries(value) : (value ?? {}));
    expect(entries(after)).toEqual({ ...entries(before), format: CURRENT });
  });
});

describe('checkFormat', () => {
  it.each([
    ['no file', undefined, undefined],
    ['local only', undefined, 'tracker: github\n'],
    ['invalid yaml', 'reviewers: [\n', undefined],
    ['not utf-8', Buffer.from([0xff, 0xfe, 0x0a]), undefined],
    ['list', '- a\n', undefined],
    ['empty', '', undefined],
  ])('passes a config it cannot judge (%s)', (_, committed, local) => {
    expect(checkFormat(repo(committed, local))).toBeNull();
  });

  it('passes an unreadable config', () => {
    const root = repo();
    mkdirSync(join(root, CONFIG));
    expect(checkFormat(root)).toBeNull();
  });

  it('ignores the local file', () => {
    expect(checkFormat(repo(`format: ${CURRENT}\n`, 'format: 9.0.0\n'))).toBeNull();
    expect(checkFormat(repo('tracker: linear\n', `format: ${CURRENT}\n`))).toBe(refusal('format.missing'));
  });

  it.each([
    ['missing', 'tracker: linear\n', 'format.missing', {}],
    ['newer', 'format: 9.0.0\n', 'format.newer', { declared: '9.0.0' }],
    ['older', 'format: 0.0.1\n', 'format.older', { declared: '0.0.1' }],
    ['invalid', 'format: 0.4\n', 'format.invalid', { value: 0.4 }],
    ['null', 'format:\n', 'format.invalid', { value: null }],
  ])('refuses a %s format', (_, text, id, values) => {
    expect(checkFormat(repo(text))).toBe(refusal(id, values));
  });

  it('passes the current format', () => {
    expect(checkFormat(repo(`format: ${CURRENT}\nbogus: 1\n`))).toBeNull();
  });
});

// A real invocation of each command; the shims only print their help, so none reaches GitHub.
const ARGV: Record<string, string[]> = {
  'la-config': ['show'],
  'la-doctor': [],
  'la-arch-check': [],
  'la-arch-scaffold': [],
  'la-arch-diagrams': [],
  'la-arch-migrate': [],
  'la-check-conventions': ['--base', 'main'],
  'la-count-comments': ['a.ts'],
  'la-typecheck': [],
  'la-fetch-coderabbit-threads': ['--help'],
  'la-reply-invalid-coderabbit': ['--help'],
  'la-reply-to-pr-thread': ['--help'],
  'la-fetch-failed-pr-checks': ['--help'],
  'la-wait-for-reviews': ['--help'],
  'la-pr-reviewers': ['--help'],
  'dr-refactor': ['rename', '--file', 'a.ts', '--name', 'f', '--new-name', 'g'],
  'dr-compliance': ['a.ts'],
  'dr-mock-lint': ['a.ts'],
};

describe('the format check in dispatch', () => {
  it('has an invocation for every manifest command', () => {
    expect(Object.keys(ARGV).sort()).toEqual(Object.keys(MANIFEST).sort());
  });

  it.each(Object.keys(MANIFEST).sort())('%s runs the check unless the manifest exempts it', (command) => {
    const root = tempRepo({ [CONFIG]: 'tracker: linear\n', 'a.ts': 'export function f(): void {}\n' });
    const result = run(root, command, ARGV[command] ?? []);
    const missing = `${refusal('format.missing')}\n`;
    if (command === 'la-doctor') expect(result.err).not.toContain(missing);
    else if (MANIFEST[command]?.format === 'exempt') expect(result.out + result.err).not.toContain(missing.trim());
    else expect(result).toEqual({ code: 2, out: '', err: missing });
  });
});
