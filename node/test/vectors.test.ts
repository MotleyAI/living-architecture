// Every shared vector, through src/contract/index.ts: canonicalRepr(value): string, normalize(value),
// loadYaml(text) (the YAML 1.1 profile), globMatch(pattern, path): boolean, isPortableRegex(pattern): boolean,
// materializeDefaults(schema, data | null), validate(schema, data): string[] (empty when valid).
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  canonicalRepr,
  globMatch,
  isPortableRegex,
  loadYaml,
  materializeDefaults,
  normalize,
  validate,
} from '../src/contract/index.js';
import { SHARED, VECTORS, field, loadYamlFile, plain, readJson, vectors } from './helpers.js';

const CONFIG_SCHEMA = readJson(join(SHARED, 'schema', 'living-architecture.schema.json'));
const LANGUAGES = loadYamlFile(join(SHARED, 'languages.yaml'));

function present(name: string, cases: unknown[] | undefined): unknown[] {
  it(`${name} has vectors`, () => {
    expect(cases?.length ?? 0).toBeGreaterThan(0);
  });
  return cases ?? [];
}

describe('repr.yaml', () => {
  // Each `value` is read with the twin's YAML profile; the expected `repr` as plain text.
  const text = readFileSync(join(VECTORS, 'repr.yaml'), 'utf8');
  const cases = present('repr.yaml', vectors('repr.yaml', true)?.cases) as { repr: string }[];
  cases.forEach((vector, i) => {
    it(`repr ${vector.repr}`, () => {
      const value = field(field(loadYaml(text), 'cases')[i], 'value');
      expect(canonicalRepr(value)).toBe(vector.repr);
    });
  });
});

describe('glob.yaml', () => {
  for (const v of present('glob.yaml', vectors('glob.yaml')?.cases) as { pattern: string; path: string; match: boolean }[]) {
    it(`${v.pattern} | ${v.path}`, () => {
      expect(globMatch(v.pattern, v.path)).toBe(v.match);
    });
  }
});

describe('test-files.yaml', () => {
  for (const lang of ['python', 'typescript']) {
    const globs: string[] = LANGUAGES?.[lang]?.test_globs ?? [];
    it(`languages.yaml declares ${lang} test globs`, () => {
      expect(globs.length).toBeGreaterThan(0);
    });
    for (const v of present(`test-files.yaml ${lang}`, vectors('test-files.yaml')?.[lang]) as { path: string; test: boolean }[]) {
      it(`${lang}: ${v.path}`, () => {
        expect(globs.some((g) => globMatch(g, v.path))).toBe(v.test);
      });
    }
  }
});

describe('yaml.yaml', () => {
  for (const v of present('yaml.yaml', vectors('yaml.yaml')?.cases) as { name: string; text: string; json?: string; repr?: string }[]) {
    it(v.name, () => {
      expect((v.json === undefined) !== (v.repr === undefined)).toBe(true);
      if (v.json !== undefined) expect(plain(loadYaml(v.text))).toEqual(JSON.parse(v.json));
      else expect(canonicalRepr(normalize(loadYaml(v.text)))).toBe(v.repr);
    });
  }
});

describe('defaults.yaml', () => {
  for (const v of present('defaults.yaml', vectors('defaults.yaml')?.cases) as { name: string; config: string | null; resolved: unknown }[]) {
    it(v.name, () => {
      const data = v.config === null ? null : loadYaml(v.config);
      expect(plain(materializeDefaults(CONFIG_SCHEMA, data))).toEqual(v.resolved);
    });
  }
});

describe('materialize.yaml', () => {
  for (const v of present('materialize.yaml', vectors('materialize.yaml')?.cases) as { name: string; schema: object; input: unknown; output: unknown }[]) {
    it(v.name, () => {
      expect(plain(materializeDefaults(v.schema, v.input))).toEqual(v.output);
    });
  }

  it('does not mutate its input', () => {
    const data = { reviewers: { coderabbit: true } };
    materializeDefaults(CONFIG_SCHEMA, data);
    expect(data).toEqual({ reviewers: { coderabbit: true } });
  });
});

describe('regex-subset.yaml', () => {
  const v = vectors('regex-subset.yaml') ?? {};
  for (const pattern of present('regex-subset.yaml accept', v.accept) as string[]) {
    it(`accepts ${pattern}`, () => {
      expect(isPortableRegex(pattern)).toBe(true);
    });
  }
  for (const pattern of present('regex-subset.yaml reject', v.reject) as string[]) {
    it(`rejects ${pattern}`, () => {
      expect(isPortableRegex(pattern)).toBe(false);
    });
  }
});

describe('facts.yaml', () => {
  const v = vectors('facts.yaml') ?? {};
  const schemaFile = join(SHARED, 'schema', 'facts.schema.json');
  for (const { name, document } of present('facts.yaml accept', v.accept) as { name: string; document: unknown }[]) {
    it(`accepts ${name}`, () => {
      expect(validate(readJson(schemaFile), document)).toEqual([]);
    });
  }
  for (const { name, document } of present('facts.yaml reject', v.reject) as { name: string; document: unknown }[]) {
    it(`rejects ${name}`, () => {
      expect(validate(readJson(schemaFile), document)).not.toEqual([]);
    });
  }
});
