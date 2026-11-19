export interface A {
  n: number;
}

export function B(): number {
  return 1;
}

export class C {
  static b = 1;
  run(): number {
    return 2;
  }
}

export function blocks(flag: boolean): number {
  if (flag) {
    let x = 1;
    x += 1;
    return x;
  } else {
    let y = 2;
    y += 1;
    return y;
  }
}

export function scoped(): number {
  var v = 1;
  {
    let w = 2;
    w += 1;
  }
  return v;
}

export class E {
  private held = 0;
  get value(): number {
    return this.held;
  }
  set value(next: number) {
    this.held = next;
  }
}

export class G {
  count: number;
  constructor(size: number) {
    this.count = size;
  }
}

export function over(arg: string): string;
export function over(arg: number): number;
export function over(arg: string | number): string | number {
  return arg;
}

export function spare(): number {
  return 0;
}

export const made: A = { n: 1 };

export class H {
  constructor(public width: number) {}
  area(height: number): number {
    return this.width * height;
  }
}

export interface Shape {
  w: number;
}

export interface Shape {
  h: number;
}

export interface Box {
  d: number;
}

export const unit: Shape = { w: 1, h: 1 };
export const cube: Box = { d: 1 };
