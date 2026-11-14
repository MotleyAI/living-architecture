// The TS rename's pure pieces: `--keep` / `--with` sites and the `--docs` mention rules.
import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ts } from '../src/lang/index.js';
import { codeMarked, mentions, qualified, sourceRegions } from '../src/refactor/mentions.js';
import { Site } from '../src/refactor/sites.js';

describe('Site', () => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'la-sites-')));
  mkdirSync(join(root, 'tests', 'compat'), { recursive: true });
  for (const file of ['tests/compat/old.ts', 'tests/compatible.ts', 'tests/shim.ts']) writeFileSync(join(root, file), '');

  it('matches a directory by whole path components', () => {
    const site = Site.parse('tests/compat', root, root);
    expect(site.covers('tests/compat/old.ts', 1)).toBe(true);
    expect(site.covers('tests/compatible.ts', 1)).toBe(false);
  });

  it('matches a line of a file, normalized', () => {
    const site = Site.parse('./tests/../tests/shim.ts:4', root, root);
    expect([site.covers('tests/shim.ts', 4), site.covers('tests/shim.ts', 5)]).toEqual([true, false]);
  });

  it('matches nothing for a missing path or one outside the project', () => {
    expect(Site.parse('tests/missing.ts', root, root).covers('tests/missing.ts', 1)).toBe(false);
    expect(Site.parse('..', root, root).parts).toBeNull();
  });
});

describe('mentions', () => {
  const owners = [{ path: ['src', 'engine', 'Engine'], member: true }];
  const source = (text: string) => ts().createSourceFile('a.ts', text, ts().ScriptTarget.Latest, true);
  const found = (text: string) => mentions(text, 'saveModel', sourceRegions(source(text)));

  it('finds comment, string and template text, not code or longer words', () => {
    const text = "// saveModel\nconst a = 'saveModel'; const b = `x ${saveModel} saveModel`; saveModelX();\n";
    expect(found(text).map((m) => m.where)).toEqual(['comment', 'string', 'string']);
  });

  it('qualifies by owner, module suffix and collisions', () => {
    const at = (text: string) => text.lastIndexOf('saveModel');
    for (const text of ['Engine.saveModel', 'Engine#saveModel', 'engine.Engine.saveModel', 'src.engine.Engine#saveModel']) {
      expect(qualified(text, at(text), owners, [])).toBe(true);
    }
    expect(qualified('other.Engine.saveModel', at('other.Engine.saveModel'), owners, [])).toBe(false);
    expect(qualified('Engine.saveModel', 7, owners, [['lib', 'Engine']])).toBe(false);
    expect(qualified('e.saveModel', 2, owners, [])).toBe(false);
    const libEngine = [['lib', 'engine', 'Engine']];
    expect(qualified('engine.Engine.saveModel', at('engine.Engine.saveModel'), owners, libEngine)).toBe(false);
    expect(qualified('src.engine.Engine.saveModel', at('src.engine.Engine.saveModel'), owners, libEngine)).toBe(true);
  });

  it('marks backticks, links and a string opening with the name', () => {
    const marked = (text: string) => found(text).map((m) => codeMarked(text, m));
    expect(marked('// `saveModel` and `saveModel()` and {@link saveModel} and saveModel\n')).toEqual([true, true, true, false]);
    expect(marked("const a = 'saveModel: x'; const b = 'x saveModel: y';\n")).toEqual([true, false]);
    expect(marked('const t = `saveModel: ${1} saveModel: `;\n')).toEqual([true, false]);
  });
});
