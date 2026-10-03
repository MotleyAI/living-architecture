// The contract glob dialect: segment-wise, `*` within a segment, `**` for zero or more segments.

const segmentCache = new Map<string, RegExp>();

function segmentRe(segment: string): RegExp {
  let re = segmentCache.get(segment);
  if (re === undefined) {
    const body = [...segment].map((ch) => (ch === '*' ? '.*' : ch.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&'))).join('');
    re = new RegExp(`^${body}$`, 's');
    segmentCache.set(segment, re);
  }
  return re;
}

function match(pattern: string[], path: string[]): boolean {
  const [head, ...rest] = pattern;
  if (head === undefined) return path.length === 0;
  if (head === '**') return path.some((_, i) => match(rest, path.slice(i))) || match(rest, []);
  const [first, ...tail] = path;
  return first !== undefined && segmentRe(head).test(first) && match(rest, tail);
}

export function globMatch(pattern: string, path: string): boolean {
  return match(pattern.split('/'), path ? path.split('/') : []);
}
