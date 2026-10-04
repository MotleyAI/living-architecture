import assert from 'node:assert';

export function check(a: boolean, b: boolean): void {
  assert(a && b);
}
