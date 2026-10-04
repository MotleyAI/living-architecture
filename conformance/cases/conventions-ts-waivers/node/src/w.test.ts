import { expect, it } from 'vitest';

it('waives', () => {
  expect(a && b).toBe(true); // ALLOW(composite-assert): one fact
  expect(() => { // ALLOW(raises-single-throw): setup is pure
    parse(load());
  }).toThrow();
  expect(() => {
    parse(load()); // ALLOW(raises-single-throw): not the start line
  }).toThrow();
  expect(() => parse(load())).toThrow(); // ALLOW(composite-assert): wrong rule
});
