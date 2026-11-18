// Python's orderings: str by code point, (src, dst) tuples.

/** Python's str order (by code point). */
export function compareStrings(a: string, b: string): number {
  const [x, y] = [[...a], [...b]];
  for (let i = 0; i < Math.min(x.length, y.length); i += 1) {
    const d = (x[i]?.codePointAt(0) ?? 0) - (y[i]?.codePointAt(0) ?? 0);
    if (d !== 0) return d;
  }
  return x.length - y.length;
}

/** Python's tuple order on `src\0dst` element-edge keys. */
export function compareEdge(a: string, b: string): number {
  const [as = '', ad = ''] = a.split('\0');
  const [bs = '', bd = ''] = b.split('\0');
  return compareStrings(as, bs) || compareStrings(ad, bd);
}
