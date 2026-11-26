import assert from 'node:assert';
import { expect, it } from 'vitest';

it('throws', async () => {
  expect(() => parse(load())).toThrow();
  expect(() => parse(load())).toThrowError('bad');
  expect(() => parse(load())).toThrowErrorMatchingSnapshot();
  expect(() => parse(load())).toThrowErrorMatchingInlineSnapshot();
  await expect(fetchIt(url())).rejects.toThrow();
  assert.throws(() => parse(load()));
  await assert.rejects(async () => parse(load()));
  expect(() => new Parser(load())).toThrow();
  expect(() => {
    const raw = load();
    parse(raw);
  }).toThrow();
  expect(() => parse()).toThrow();
  await expect(fetchIt()).rejects.toThrow();
  expect(() => a(b())).not.toThrow();
  expect(parse).toThrow();
});
