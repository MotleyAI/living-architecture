// The YAML profile's duplicate-key error: the normalized key and both lines it carries.
import { describe, expect, it } from 'vitest';
import { DuplicateKeyError, YAMLError, canonicalRepr, loadYaml } from '../src/contract/index.js';

const DUPLICATE_KEYS: [string, string, number, number][] = [
  ['a: 1\n"a": 2\n', "'a'", 1, 2],
  ['1: a\ntrue: b\n', '1', 1, 2],
  ['true: a\n1: b\n', 'True', 1, 2],
  ['false: a\n0.0: b\n', 'False', 1, 2],
  ['1.0: a\n1: b\n', '1.0', 1, 2],
  ['-0.0: a\n0: b\n', '-0.0', 1, 2],
  ['~: a\nnull: b\n', 'None', 1, 2],
  ['.nan: a\n.nan: b\n', 'nan', 1, 2],
  ['-.inf: a\n-.Inf: b\n', '-inf', 1, 2],
  ['9007199254740993: a\n9007199254740993: b\n', '9007199254740993', 1, 2],
  ['2026-01-02: a\n"2026-01-02": b\n', "'2026-01-02'", 1, 2],
  ['"2026-01-02T03:04:05+00:00": a\n2026-01-02T03:04:05Z: b\n', "'2026-01-02T03:04:05+00:00'", 1, 2],
  ['x: &x {k: 1}\nz:\n  <<: *x\n  !!merge <<: *x\n', "'<<'", 3, 4],
  ['a: &k s\nm:\n  *k : 1\n  *k : 2\n', "'s'", 3, 4],
  ['r:\n  s:\n    - {t: 1,\n       t: 2}\n', "'t'", 3, 4],
];

describe('DuplicateKeyError', () => {
  for (const [text, key, first, second] of DUPLICATE_KEYS) {
    it(`${JSON.stringify(text)} repeats ${key}`, () => {
      let error: unknown;
      try {
        loadYaml(text);
      } catch (e) {
        error = e;
      }
      expect(error).toBeInstanceOf(DuplicateKeyError);
      const duplicate = error as DuplicateKeyError;
      expect(canonicalRepr(duplicate.key)).toBe(key);
      expect([duplicate.first, duplicate.second]).toEqual([first, second]);
      expect(duplicate.message).toBe(`duplicate key ${key} at lines ${first} and ${second}`);
    });
  }

  it('is a YAMLError', () => {
    expect(DuplicateKeyError.prototype).toBeInstanceOf(YAMLError);
  });
});
