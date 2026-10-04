import { expect, it } from 'vitest';

it('x', () => {
  expect(a && b).toBe(true);
  expect(() => parse(load())).toThrow();
});
