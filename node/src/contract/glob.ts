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

/** Python's fnmatch.fnmatch on POSIX (the exempt globs): `*` also matches `/`, `?` one character, `[...]` a class. */
export function fnmatch(path: string, pattern: string): boolean {
  let re = '';
  for (let i = 0; i < pattern.length; i++) {
    const ch = pattern[i] ?? '';
    if (ch === '*') re += '[\\s\\S]*';
    else if (ch === '?') re += '[\\s\\S]';
    else if (ch === '[') {
      const end = pattern.indexOf(']', i + 2);
      if (end === -1) re += '\\[';
      else {
        let body = pattern.slice(i + 1, end).replaceAll('\\', '\\\\');
        if (body.startsWith('!')) body = `^${body.slice(1)}`;
        re += `[${body}]`;
        i = end;
      }
    } else re += ch.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
  }
  return new RegExp(`^${re}$`, 'u').test(path);
}
