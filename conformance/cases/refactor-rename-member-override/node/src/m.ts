export class Base {
  old(): number {
    return 1;
  }
}

export class Sub extends Base {
  old(): number {
    return 2;
  }
}

export function f(b: Base): number {
  return b.old();
}
