// Python's str semantics shared by the twins, through src/contract/index.ts.
import { describe, expect, it } from 'vitest';
import { decodeUtf8 } from '../src/contract/index.js';

describe('decodeUtf8', () => {
  it('keeps a BOM, like bytes.decode("utf-8")', () => {
    expect(decodeUtf8(Buffer.from('﻿model {}', 'utf8'))).toBe('﻿model {}');
  });

  it('throws a TypeError on invalid UTF-8', () => {
    const bytes = Buffer.from([0x6d, 0xff, 0x0a]);
    expect(() => decodeUtf8(bytes)).toThrow(TypeError);
  });
});
