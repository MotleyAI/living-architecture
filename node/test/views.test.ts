// Views: nested includes and predicate anchors reach view_depth levels below themselves.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { parseModel, parseViews } from '../src/c4/index.js';

const NESTED_MODEL = `specification { element system  element node  tag legacy }
model {
  python = system 'Python' {
    api = node 'API' {
      handlers = node 'Handlers' {
        x = node 'X' {
          y = node 'Y'
          w = node 'W'
        }
      }
      other = node 'Other' {
        z = node 'Z'
      }
    }
    core = node 'Core' {
      store = node 'Store' {
        sql = node 'SQL'
      }
    }
    api.handlers.x -> core.store.sql
    api.handlers -> core
    api.other.z -> core
    api.other -> core #legacy
    api.handlers.x.y -> api.handlers.x.w
  }
}
`;

type EdgeTuple = [string, string, boolean];

describe('nested view selections', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'la-views-'));
  let count = 0;
  afterAll(() => rmSync(tmp, { recursive: true, force: true }));

  function parsed(include: string, depth: number) {
    const root = join(tmp, `repo-${count++}`);
    mkdirSync(join(root, 'architecture'), { recursive: true });
    writeFileSync(join(root, 'architecture', 'model.c4'), NESTED_MODEL);
    writeFileSync(join(root, 'architecture', 'views.c4'), `views {\n  view v of python {\n    title 'V'\n    include ${include}\n  }\n}\n`);
    writeFileSync(join(root, 'architecture', 'index.yaml'), `python:\n  root_package: pkg\nview_depth:\n  v: ${depth}\n`);
    return parseViews(root, parseModel(root));
  }

  it.each<[string, string, number, string[], EdgeTuple[]]>([
    ['include reach', 'api.handlers', 2, ['api.handlers', 'api.handlers.x'], []],
    [
      'include deeper',
      'api.handlers',
      3,
      ['api.handlers', 'api.handlers.x', 'api.handlers.x.y', 'api.handlers.x.w'],
      [['api.handlers.x.y', 'api.handlers.x.w', false]],
    ],
    ['overlapping includes', 'api, api.handlers', 2, ['api', 'api.handlers', 'api.handlers.x', 'api.other'], []],
    [
      'nested src anchor',
      'api.handlers -> *',
      2,
      ['api', 'api.handlers', 'api.handlers.x', 'core', 'core.store', 'core.store.sql'],
      [
        ['api.handlers.x', 'core.store.sql', false],
        ['api.handlers', 'core', false],
      ],
    ],
    ['anchor is endpoint', '* -> core', 1, ['api', 'core'], [['api', 'core', false]]],
    ['nested dst anchor', '* -> core.store', 1, ['api', 'api.handlers', 'core', 'core.store'], [['api.handlers', 'core.store', false]]],
    ['unrelated sources excluded', 'api.other -> *', 1, ['api', 'api.other', 'core'], [['api.other', 'core', false]]],
    [
      'legacy-only contributor',
      'api.other -> *',
      2,
      ['api', 'api.other', 'api.other.z', 'core'],
      [
        ['api.other.z', 'core', false],
        ['api.other', 'core', true],
      ],
    ],
  ])('%s', (_, include, depth, nodes, edges) => {
    const { views, findings } = parsed(include, depth);
    expect(findings).toEqual([]);
    expect(views.map((v) => v.nodeIds)).toEqual([nodes]);
    expect(views.map((v) => v.edges.map((e) => [e.src, e.dst, e.legacy]))).toEqual([edges]);
  });

  it.each([
    ['python.api', 'view v includes unknown id python.api'],
    ['python.api -> *', 'view include python.api -> * references unknown id python.api'],
    ['* -> python.api.handlers', 'view include * -> python.api.handlers references unknown id python.api.handlers'],
    ['handlers', 'view v includes unknown id handlers'],
  ])('a name not relative to the root is unknown: %s', (include, finding) => {
    expect(parsed(include, 2).findings).toEqual([finding]);
  });
});
