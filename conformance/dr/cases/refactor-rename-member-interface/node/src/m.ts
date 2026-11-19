export interface I {
  old(): number;
}

export class C implements I {
  old(): number {
    return 1;
  }
}

export function f(i: I): number {
  return i.old();
}
