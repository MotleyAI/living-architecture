// The portable regex subset (regex-subset.md).

const CLASS_ESCAPES = new Set('dDwWsS');
const PUNCTUATION = new Set('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~');
const BOUNDS_RE = /^\{\d+(?:,\d*)?\}/;

const escapeOk = (ch: string): boolean => CLASS_ESCAPES.has(ch) || PUNCTUATION.has(ch);

/** Index of the `]` closing the class opened at `start`, or null when not portable. */
function classEnd(pattern: string, start: number): number | null {
  let i = start + 1;
  if (pattern.startsWith('^', i)) i += 1;
  if (pattern.startsWith(']', i)) return null;
  while (i < pattern.length) {
    const ch = pattern[i];
    if (ch === ']') return i;
    if (ch === '[') return null;
    if (ch === '\\') {
      if (i + 1 >= pattern.length || !escapeOk(pattern[i + 1] ?? '')) return null;
      i += 2;
      continue;
    }
    i += 1;
  }
  return null;
}

/** Index after the quantifier at `i` (plus an optional lazy `?`), or null when not portable. */
function quantifierEnd(pattern: string, start: number): number | null {
  let i = start;
  if (pattern[i] === '{') {
    const m = BOUNDS_RE.exec(pattern.slice(i));
    if (m === null) return null;
    i += m[0].length;
  } else {
    i += 1;
  }
  if (pattern.startsWith('?', i)) i += 1;
  if (i < pattern.length && '*+?{'.includes(pattern[i] ?? '')) return null;
  return i;
}

function scan(pattern: string): boolean {
  let i = 0;
  let quantifiable = false;
  while (i < pattern.length) {
    const ch = pattern[i] ?? '';
    if ('*+?{'.includes(ch)) {
      const end: number | null = quantifiable ? quantifierEnd(pattern, i) : null;
      if (end === null) return false;
      [i, quantifiable] = [end, false];
      continue;
    }
    if (ch === '\\') {
      const next = pattern[i + 1] ?? '';
      if (next !== 'b' && !escapeOk(next)) return false;
      [i, quantifiable] = [i + 2, next !== 'b'];
    } else if (ch === '[') {
      const end: number | null = classEnd(pattern, i);
      if (end === null) return false;
      [i, quantifiable] = [end + 1, true];
    } else if (ch === '(') {
      if (pattern.startsWith('(?', i) && !pattern.startsWith('(?:', i)) return false;
      [i, quantifiable] = [i + (pattern.startsWith('(?:', i) ? 3 : 1), false];
    } else if ('}]'.includes(ch)) {
      return false;
    } else {
      [i, quantifiable] = [i + 1, !'^$|'.includes(ch)];
    }
  }
  return true;
}

export function isPortableRegex(pattern: string): boolean {
  try {
    new RegExp(pattern);
  } catch {
    return false;
  }
  return scan(pattern);
}

/** Full-match a portable pattern; a text with any non-ASCII character never matches. */
export function fullMatch(pattern: string, text: string): boolean {
  // eslint-disable-next-line no-control-regex
  return /^[\x00-\x7f]*$/.test(text) && new RegExp(`^(?:${pattern})$`).test(text);
}
