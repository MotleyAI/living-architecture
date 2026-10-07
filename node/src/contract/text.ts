// Python's str semantics the twins share: splitlines, strip, ordering, and `\w` (Unicode letters, digits, underscore).

// eslint-disable-next-line no-control-regex -- Python's splitlines breaks on these
const LINE_BREAK = /\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/;

/** Python's str.splitlines(): no trailing empty line. */
export function splitLines(text: string): string[] {
  if (text === '') return [];
  const lines = text.split(LINE_BREAK);
  if (LINE_BREAK.test(text.slice(-2)) && lines[lines.length - 1] === '') lines.pop();
  return lines;
}

/** Python's `\w` for str patterns, for use inside a `u`-flagged RegExp. */
export const WORD = '[\\p{L}\\p{N}_]';

/** Python's str.isalnum() for one character, or `_`. */
export function isWordStart(ch: string): boolean {
  return new RegExp(`^${WORD}$`, 'u').test(ch);
}

/** Python's `bytes.decode('utf-8')`: keeps a BOM, throws a TypeError on invalid UTF-8. */
export function decodeUtf8(bytes: Uint8Array): string {
  return new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
}

/** Python's str ordering: by code point (JS's default compares UTF-16 units). */
export function byCodePoint(a: string, b: string): number {
  const [x, y] = [[...a], [...b]];
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const d = (x[i]?.codePointAt(0) ?? 0) - (y[i]?.codePointAt(0) ?? 0);
    if (d !== 0) return d;
  }
  return x.length - y.length;
}
