// Compound names: a declaration whose name contains the renamed name as a word sequence.
const isUpper = (char: string | undefined): boolean => char !== undefined && /^\p{Lu}$/u.test(char);
const isDigit = (char: string): boolean => /^\p{Nd}$/u.test(char);

/** `name` split at `_`, before a capital after a non-capital, and before the last capital of a run that a letter
 * other than a capital follows. */
export function words(name: string): string[] {
  const out: string[] = [];
  for (const chunk of name.split('_')) {
    const chars = [...chunk];
    let start = 0;
    for (let i = 1; i < chars.length; i += 1) {
      if (!isUpper(chars[i])) continue;
      const next = chars[i + 1];
      const follows = next !== undefined && !isUpper(next) && !isDigit(next);
      if (!isUpper(chars[i - 1]) || follows) {
        out.push(chars.slice(start, i).join(''));
        start = i;
      }
    }
    if (chars.length > 0) out.push(chars.slice(start).join(''));
  }
  return out;
}

/** `name` holds `old`'s words in sequence, without case, the last also with an `s` or `es` suffix. */
export function isCompound(name: string, old: string): boolean {
  const wanted = words(old).map((w) => w.toLowerCase());
  const found = words(name).map((w) => w.toLowerCase());
  const last = wanted.at(-1);
  if (last === undefined || name === old) return false;
  const lasts = [last, `${last}s`, `${last}es`];
  for (let i = 0; i + wanted.length <= found.length; i += 1) {
    const head = wanted.slice(0, -1).every((w, k) => found[i + k] === w);
    if (head && lasts.includes(found[i + wanted.length - 1] ?? '')) return true;
  }
  return false;
}
