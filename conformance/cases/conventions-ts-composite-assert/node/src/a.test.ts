import assert from 'node:assert';
import { expect, it } from 'vitest';

it('checks', () => {
  expect(a && b).toBe(true);
  assert(a && b);
  assert.ok(a && b);
  expect((a && b)).toBeTruthy();
  expect(a || b).toBe(true);
  expect(a && b || c).toBe(true);
  expect(!(a && b)).toBe(true);
});
