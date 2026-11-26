// Rows carry `field`.
// field is plain here
export const ROWS = 1;

export class A {
  field = '';
}

/** Formats `field` values. */
export class Helper {}

/** Returns `field`. */
export function show(a: A): string {
  return a.field;
}
