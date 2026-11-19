export type next = string;

export const old = 1;

export function f(s: next): number {
  return old + s.length;
}
