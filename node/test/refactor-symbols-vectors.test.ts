// The shared symbol-path, compound-name and range-transform vectors, through the npm twin.
import { describe, expect, it } from 'vitest';
import { isCompound, words } from '../src/refactor/compound.js';
import { mapRange, type Replaced } from '../src/refactor/position.js';
import { parsePath } from '../src/refactor/symbols.js';
import { vectors } from './helpers.js';

interface Vectors {
  paths: { name: string; path: string; segments?: string[]; param?: string; value?: string; invalid?: boolean }[];
  words: { name: string; words: string[] }[];
  compounds: { old: string; name: string; match: boolean }[];
  ranges: { name: string; edits: Replaced[]; range: [number, number]; mapped: [number, number] }[];
}

const VECTORS = vectors('refactor-symbols.yaml') as Vectors;

describe('refactor-symbols vectors', () => {
  it.each(VECTORS.paths)('path: $name', (vector) => {
    const parsed = parsePath(vector.path);
    if (vector.invalid === true) expect(parsed).toBeNull();
    else expect(parsed).toEqual({ segments: vector.segments, param: vector.param ?? null, value: vector.value ?? null });
  });

  it.each(VECTORS.words)('words: $name', (vector) => {
    expect(words(vector.name)).toEqual(vector.words);
  });

  it.each(VECTORS.compounds)('compound: $old in $name', (vector) => {
    expect(isCompound(vector.name, vector.old)).toBe(vector.match);
  });

  it.each(VECTORS.ranges)('range: $name', (vector) => {
    expect(mapRange(vector.edits, ...vector.range)).toEqual(vector.mapped);
  });
});
