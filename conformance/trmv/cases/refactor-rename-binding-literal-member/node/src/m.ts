export type Kind = 'fast' | 'slow';

export function f(k: Kind): boolean {
  const nxt = 1;
  return k === 'fast' && nxt > 0;
}
