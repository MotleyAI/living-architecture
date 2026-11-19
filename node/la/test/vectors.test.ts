// la's shared vectors, through la's contract: materializeDefaults and validate over la's schemas, whose `$ref`s into
// dr's schemas resolve.
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { loadYaml, materializeDefaults, validate } from '../src/contract/index.js';
import { LA_SHARED, LA_VECTORS, loadYamlFile, plain, readJson } from '../../dr/test/helpers.js';

const CONFIG_SCHEMA = readJson(join(LA_SHARED, 'schema', 'living-architecture.schema.json'));
const vectors = (name: string): any => loadYamlFile(join(LA_VECTORS, name));

function present(name: string, cases: unknown[] | undefined): unknown[] {
  it(`${name} has vectors`, () => {
    expect(cases?.length ?? 0).toBeGreaterThan(0);
  });
  return cases ?? [];
}

describe('defaults.yaml', () => {
  for (const v of present('defaults.yaml', vectors('defaults.yaml')?.cases) as { name: string; config: string | null; resolved: unknown }[]) {
    it(v.name, () => {
      const data = v.config === null ? null : loadYaml(v.config);
      expect(plain(materializeDefaults(CONFIG_SCHEMA, data))).toEqual(v.resolved);
    });
  }
});

for (const [file, schemaName] of [
  ['facts.yaml', 'facts.schema.json'],
  ['conventions-facts.yaml', 'conventions-facts.schema.json'],
] as const) {
  describe(file, () => {
    const v = vectors(file) ?? {};
    const schemaFile = join(LA_SHARED, 'schema', schemaName);
    for (const { name, document } of present(`${file} accept`, v.accept) as { name: string; document: unknown }[]) {
      it(`accepts ${name}`, () => {
        expect(validate(readJson(schemaFile), document)).toEqual([]);
      });
    }
    for (const { name, document } of present(`${file} reject`, v.reject) as { name: string; document: unknown }[]) {
      it(`rejects ${name}`, () => {
        expect(validate(readJson(schemaFile), document)).not.toEqual([]);
      });
    }
  });
}

describe('validation messages', () => {
  it('name the offending value', () => {
    expect(validate(CONFIG_SCHEMA, { tracker: 'jira', exempt: 'a', conventions: { rules: ['no-such-rule'] } })).toEqual([
      "conventions.rules.0: 'no-such-rule' is not one of ['import-not-top', 'text-ratio', 'composite-assert', 'raises-single-throw']",
      "exempt: 'a' is not of type 'array'",
      "tracker: 'jira' is not one of ['linear', 'github', 'none']",
    ]);
  });
});
