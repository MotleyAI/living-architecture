// la-arch-migrate's 0.4.0 step against the shared exempt-move vectors.
import { describe, expect, it } from 'vitest';
import { ExemptNotMigratable, moveExempt } from '../src/c4/exempt-move.js';
import { vectors } from '../../dr/test/helpers.js';

interface Case {
  name: string;
  text: string;
  moved?: string;
  refused?: boolean;
}

const CASES: Case[] = vectors('exempt-move.yaml').cases;

describe('moveExempt', () => {
  it.each(CASES.filter((c) => !c.refused).map((c) => [c.name, c] as const))('%s', (_name, c) => {
    expect(moveExempt(c.text, '9.9.9')).toBe(c.moved);
  });

  it.each(CASES.filter((c) => c.refused).map((c) => [c.name, c] as const))('%s is refused', (_name, c) => {
    expect(() => moveExempt(c.text, '9.9.9')).toThrow(ExemptNotMigratable);
  });
});
