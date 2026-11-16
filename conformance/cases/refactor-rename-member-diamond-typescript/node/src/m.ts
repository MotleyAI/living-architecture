export interface A {
  old(): number;
}

export interface B {
  old(): number;
}

export interface D extends A, B {}

export function f(d: D): number {
  return d.old();
}
