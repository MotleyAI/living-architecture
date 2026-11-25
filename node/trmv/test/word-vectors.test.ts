// The shared word-replacement vectors, through the npm twin.
import { describe, expect, it } from 'vitest';
import { heldWords, replaceWords } from '../src/refactor/words.js';
import { vectors } from './helpers.js';

interface Name {
  name: string;
  held: string[];
  new_name: string;
}
interface Case {
  name: string;
  words: Record<string, string>;
  names: Name[];
}

const CASES = (vectors('refactor-words.yaml', true) as { cases: Case[] }).cases;
const NAMES = CASES.flatMap((c) => c.names.map((vector) => ({ id: `${c.name}: ${vector.name}`, table: c.words, vector })));

describe('refactor-words vectors', () => {
  it('cover every case form', () => {
    expect(NAMES.length).toBeGreaterThan(40);
  });

  it.each(NAMES)('held: $id', ({ table, vector }) => {
    expect(heldWords(vector.name, table)).toEqual(vector.held);
  });

  it.each(NAMES)('new name: $id', ({ table, vector }) => {
    expect(replaceWords(vector.name, table)).toBe(vector.new_name);
  });
});
