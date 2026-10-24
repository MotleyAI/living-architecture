// Python's str semantics shared by the twins, through src/contract/index.ts.
import { describe, expect, it } from 'vitest';
import { decodeUtf8, splitLinesKeepEnds } from '../src/contract/index.js';

describe('decodeUtf8', () => {
  it('keeps a BOM, like bytes.decode("utf-8")', () => {
    expect(decodeUtf8(Buffer.from('﻿model {}', 'utf8'))).toBe('﻿model {}');
  });

  it('throws a TypeError on invalid UTF-8', () => {
    const bytes = Buffer.from([0x6d, 0xff, 0x0a]);
    expect(() => decodeUtf8(bytes)).toThrow(TypeError);
  });
});

describe('splitLinesKeepEnds', () => {
  it.each([
    ['a\nb\r\nc\rd', ['a\n', 'b\r\n', 'c\r', 'd']],
    ['a\n', ['a\n']],
    ['a\u2028b\x85', ['a\u2028', 'b\x85']],
    ['', []],
    ['\n\n', ['\n', '\n']],
    ['x\x0by\x0cz', ['x\x0b', 'y\x0c', 'z']],
  ])('splits %j like str.splitlines(keepends=True)', (text, expected) => {
    expect(splitLinesKeepEnds(text)).toEqual(expected);
  });
});
