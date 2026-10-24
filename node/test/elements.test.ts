// Element ids at any depth: spec ownership, touches, metadata by variety, and arc42 docs named by element id.
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, unlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterAll, afterEach, describe, expect, it, vi } from 'vitest';
import { run as runArchCheck } from '../src/archcheck/index.js';
import { REPO_ROOT } from './helpers.js';

const FIXTURE = join(REPO_ROOT, 'conformance', 'fixtures', 'arch-ts');
const MODEL = 'architecture/model.c4';
const INDEX = 'architecture/index.yaml';
const ROOT_OPEN = "  typescript = system 'Web' {\n";
const API_PKG = "        package 'src/api'\n";
const CORE_PKG = "        package 'src/core'\n";
const HANDLERS = "      handlers = node 'Handlers'\n";
const LEGACY_PKGS = "        packages ['src/old']\n";
const SPEC_MD = '# spec\n';
const OK = 'arch_check: OK\n';
const RETIRED = (e: string) =>
  `model element ${e}: the arc42 key is retired; its doc is architecture/${e}.arc42.md — run la-arch-migrate`;
const ORPHAN = 'is orphaned — not architecture/system.arc42.md, the doc of a model element, or in cross_cutting_arc42';
const NOT_FLAT = 'must sit directly in architecture/';

type Result = { code: number; out: string; err: string };

function handlersWith(body: string): string {
  return `      handlers = node 'Handlers' {\n        metadata {\n${body}        }\n      }\n`;
}

describe('element ids at any depth', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-elements-'));
  let count = 0;
  afterEach(() => vi.restoreAllMocks());
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  /** The arch-ts fixture with `edits` ([path, old, new]) applied and `files` written. */
  function repo(edits: [string, string, string][] = [], files: Record<string, string> = {}): string {
    const root = join(tmp, `repo-${count++}`);
    for (const overlay of ['repo', 'node']) cpSync(join(FIXTURE, overlay), root, { recursive: true });
    for (const [rel, old, replacement] of edits) {
      const text = readFileSync(join(root, rel), 'utf8');
      expect(text.split(old).length, `${rel}: ${old}`).toBe(2);
      writeFileSync(join(root, rel), text.replace(old, replacement));
    }
    for (const [rel, text] of Object.entries(files)) {
      mkdirSync(dirname(join(root, rel)), { recursive: true });
      writeFileSync(join(root, rel), text);
    }
    return root;
  }

  function check(root: string): Result {
    let out = '';
    let err = '';
    vi.spyOn(process.stdout, 'write').mockImplementation((chunk) => ((out += String(chunk)), true));
    vi.spyOn(process.stderr, 'write').mockImplementation((chunk) => ((err += String(chunk)), true));
    const code = runArchCheck(root, null, null);
    vi.restoreAllMocks();
    return { code, out, err };
  }

  function findings(root: string, prefix: string): string[] {
    return check(root)
      .out.split('\n')
      .filter((line) => line.startsWith(`${prefix}:`));
  }

  const touches = (list: string): [string, string, string] => [INDEX, 'diagrams: {}\n', `cross_cutting_specs:\n  api:\n    touches: ${list}\ndiagrams: {}\n`];
  const crossCutting = (list: string): [string, string, string] => [INDEX, 'diagrams: {}\n', `cross_cutting_arc42: ${list}\ndiagrams: {}\n`];
  const apiSpec: Record<string, string> = { 'openspec/specs/api/spec.md': SPEC_MD };

  it('the fixture is clean', () => {
    expect(check(repo())).toEqual({ code: 0, out: OK, err: '' });
  });

  it.each(['[typescript.api.handlers]', '[typescript]'])('touches names any element: %s', (list) => {
    expect(check(repo([touches(list)], apiSpec))).toEqual({ code: 0, out: OK, err: '' });
  });

  it.each([
    ['[typescript.api.nothing]', 'typescript.api.nothing'],
    ['[api]', 'api'],
  ])('touches naming no element: %s', (list, element) => {
    expect(findings(repo([touches(list)], apiSpec), 'spec-mapping')).toEqual([
      `spec-mapping: api touches unknown element ${element}`,
    ]);
  });

  it('a nested element owns a spec group', () => {
    const root = repo([[MODEL, HANDLERS, handlersWith("          specs ['handlers']\n")]], {
      'openspec/specs/handlers/spec.md': SPEC_MD,
    });
    expect(check(root)).toEqual({ code: 0, out: OK, err: '' });
  });

  it('a root owns a spec group', () => {
    const root = repo([[MODEL, ROOT_OPEN, `${ROOT_OPEN}    metadata {\n      specs ['twin']\n    }\n`]], {
      'openspec/specs/twin/spec.md': SPEC_MD,
    });
    expect(check(root)).toEqual({ code: 0, out: OK, err: '' });
  });

  it('an element under a virtual node owns a spec group', () => {
    const old = "      old = node 'Old' {\n        metadata {\n          specs ['old']\n        }\n      }\n";
    const root = repo([[MODEL, `${LEGACY_PKGS}      }\n`, `${LEGACY_PKGS}      }\n${old}`]], { 'openspec/specs/old/spec.md': SPEC_MD });
    expect(check(root).out).toBe(
      'claims-exist: virtual node typescript.legacy may not contain elements\narch_check: 1 finding(s)\n',
    );
  });

  it('reads owners in declaration order, then cross_cutting_specs', () => {
    const root = repo(
      [
        [MODEL, ROOT_OPEN, `${ROOT_OPEN}    metadata {\n      specs ['a', 'c']\n    }\n`],
        [MODEL, API_PKG, `${API_PKG}        specs ['api']\n`],
        [MODEL, HANDLERS, handlersWith("          specs ['a', 'b']\n")],
        [MODEL, CORE_PKG, `${CORE_PKG}        specs ['b']\n`],
        [INDEX, 'diagrams: {}\n', 'cross_cutting_specs:\n  api: {touches: [typescript.api]}\n  c: {touches: [typescript]}\ndiagrams: {}\n'],
      ],
      { ...apiSpec, 'openspec/specs/a/spec.md': SPEC_MD, 'openspec/specs/b/spec.md': SPEC_MD, 'openspec/specs/c/spec.md': SPEC_MD },
    );
    expect(findings(root, 'spec-mapping')).toEqual([
      'spec-mapping: a mapped by both typescript and typescript.api.handlers',
      'spec-mapping: b mapped by both typescript.api.handlers and typescript.core',
      'spec-mapping: api mapped by both typescript.api and cross_cutting_specs',
      'spec-mapping: c mapped by both typescript and cross_cutting_specs',
    ]);
  });

  it('an unmapped group names elements', () => {
    expect(findings(repo([], apiSpec), 'spec-mapping')).toEqual([
      'spec-mapping: spec group api is mapped by no element and not cross-cutting',
    ]);
  });

  it.each([
    ['nested', [MODEL, HANDLERS, handlersWith("          package 'src/api/x'\n")], 'typescript.api.handlers', 'package'],
    ['nested', [MODEL, HANDLERS, handlersWith("          claims ['src/api/x']\n")], 'typescript.api.handlers', 'claims'],
    ['root', [MODEL, ROOT_OPEN, `${ROOT_OPEN}    metadata {\n      package 'src'\n    }\n`], 'typescript', 'package'],
    ['root', [MODEL, ROOT_OPEN, `${ROOT_OPEN}    metadata {\n      packages ['src']\n    }\n`], 'typescript', 'packages'],
  ] as [string, [string, string, string], string, string][])('a mapping key on a %s element is a setup error', (_, edit, element, key) => {
    const { code, out, err } = check(repo([edit]));
    expect(code).toBe(2);
    expect(out).toBe('');
    expect(err.startsWith(`arch_check: model element ${element}: `)).toBe(true);
    expect(err).toContain(key);
  });

  it('an empty metadata block on a nested element is fine', () => {
    expect(check(repo([[MODEL, HANDLERS, handlersWith('')]]))).toEqual({ code: 0, out: OK, err: '' });
  });

  it('the retired arc42 key on a root, node, nested element and virtual node, in model order', () => {
    const root = repo([
      [MODEL, ROOT_OPEN, `${ROOT_OPEN}    metadata {\n      arc42 'architecture/web.arc42.md'\n    }\n`],
      [MODEL, API_PKG, `${API_PKG}        arc42 ['architecture/api.arc42.md']\n`],
      [MODEL, HANDLERS, handlersWith("          arc42 'architecture/h.arc42.md'\n")],
      [MODEL, LEGACY_PKGS, `${LEGACY_PKGS}        arc42 'architecture/legacy.arc42.md'\n`],
    ]);
    const elements = ['typescript', 'typescript.api', 'typescript.api.handlers', 'typescript.legacy'];
    expect(check(root)).toEqual({ code: 2, out: '', err: `arch_check: ${elements.map(RETIRED).join('; ')}\n` });
  });

  it('the retired key comes before the schema errors of the other keys', () => {
    const root = repo([[MODEL, HANDLERS, handlersWith("          arc42 'architecture/x.arc42.md'\n          claims ['src/x']\n")]]);
    const err = check(root).err.replace(/^arch_check: /, '').trimEnd();
    const prefix = `${RETIRED('typescript.api.handlers')}; `;
    expect(err.startsWith(prefix)).toBe(true);
    const schema = err.slice(prefix.length);
    expect(schema).toMatch(/^model element typescript\.api\.handlers: .*claims/);
    expect(schema).not.toContain('; ');
  });

  it('a metadata syntax problem is reported alone', () => {
    const root = repo([[MODEL, CORE_PKG, `${CORE_PKG}        arc42 "architecture/core.arc42.md"\n`]]);
    expect(check(root).err).toBe('arch_check: element typescript.core has malformed metadata: arc42 "architecture/core.arc42.md"\n');
  });

  it('a nested element doc is recognised and tag-checked', () => {
    const root = repo([], { 'architecture/typescript.api.handlers.arc42.md': '# Handlers\n\n1. Untagged.\n' });
    expect(check(root).out).toBe(
      'enforced-tags: typescript.api.handlers.arc42.md principle item 1 has no status tag\narch_check: 1 finding(s)\n',
    );
  });

  it('a root doc is recognised', () => {
    expect(check(repo([], { 'architecture/typescript.arc42.md': '# Web\n' }))).toEqual({ code: 0, out: OK, err: '' });
  });

  it('a doc named for no element is orphaned', () => {
    const root = repo([], { 'architecture/typescript.gone.arc42.md': '# g\n', 'architecture/api.arc42.md': '# a\n' });
    expect(findings(root, 'arc42-exists')).toEqual([
      `arc42-exists: architecture/api.arc42.md ${ORPHAN}`,
      `arc42-exists: architecture/typescript.gone.arc42.md ${ORPHAN}`,
    ]);
  });

  it('reports docs in subfolders in code-point order', () => {
    const root = repo([], {
      'architecture/x/y/z.arc42.md': '# z\n',
      'architecture/a/b.arc42.md': '# b\n',
      'architecture/B/a.arc42.md': '# a\n',
      'architecture/x/notes.md': 'not a doc\n',
    });
    expect(findings(root, 'arc42-exists')).toEqual([
      `arc42-exists: architecture/B/a.arc42.md ${NOT_FLAT}`,
      `arc42-exists: architecture/a/b.arc42.md ${NOT_FLAT}`,
      `arc42-exists: architecture/x/y/z.arc42.md ${NOT_FLAT}`,
    ]);
  });

  it('follows the layout walk rules for symlinks', () => {
    const root = repo([], { 'elsewhere/x.arc42.md': '# x\n' });
    mkdirSync(join(root, 'architecture', 'sub'));
    symlinkSync('../system.arc42.md', join(root, 'architecture', 'sub', 'file.arc42.md'));
    symlinkSync('../gone.arc42.md', join(root, 'architecture', 'sub', 'broken.arc42.md'));
    symlinkSync('../elsewhere', join(root, 'architecture', 'link'));
    expect(findings(root, 'arc42-exists')).toEqual([`arc42-exists: architecture/sub/file.arc42.md ${NOT_FLAT}`]);
  });

  it('reports cross-cutting docs that are not flat, missing or an element doc, then nested docs and orphans', () => {
    const root = repo(
      [crossCutting('[docs/a.arc42.md, architecture/typescript.api.arc42.md, architecture/gone.arc42.md, architecture/s/c.arc42.md]')],
      {
        'docs/a.arc42.md': '# a\n',
        'architecture/typescript.api.arc42.md': '# api\n',
        'architecture/s/c.arc42.md': '# c\n',
        'architecture/orphan.arc42.md': '# o\n',
      },
    );
    unlinkSync(join(root, 'architecture', 'system.arc42.md'));
    expect(findings(root, 'arc42-exists')).toEqual([
      'arc42-exists: architecture/system.arc42.md is missing',
      `arc42-exists: cross_cutting_arc42 names docs/a.arc42.md, which ${NOT_FLAT}`,
      'arc42-exists: cross_cutting_arc42 names architecture/typescript.api.arc42.md, the doc of model element typescript.api',
      'arc42-exists: cross_cutting_arc42 names architecture/gone.arc42.md, which does not exist',
      `arc42-exists: cross_cutting_arc42 names architecture/s/c.arc42.md, which ${NOT_FLAT}`,
      `arc42-exists: architecture/s/c.arc42.md ${NOT_FLAT}`,
      `arc42-exists: architecture/orphan.arc42.md ${ORPHAN}`,
    ]);
  });
});
