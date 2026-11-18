export interface B {
  n: number;
}

export function B(): number {
  return 1;
}

export class C {
  static b = 1;
  b(): number {
    return 2;
  }
}

export function blocks(flag: boolean): number {
  if (flag) {
    let y = 1;
    y += 1;
    return y;
  } else {
    let y = 2;
    y += 1;
    return y;
  }
}

export function scoped(): number {
  var v = 1;
  {
    let v = 2;
    v += 1;
  }
  return v;
}

export class E {
  private value = 0;
  get amount(): number {
    return this.value;
  }
  set amount(next: number) {
    this.value = next;
  }
}

export class G {
  size: number;
  constructor(size: number) {
    this.size = size;
  }
}

export function fresh(arg: string): string;
export function fresh(arg: number): number;
export function fresh(arg: string | number): string | number {
  return arg;
}

export function over(): number {
  return 0;
}

export const made: B = { n: 1 };

export class H {
  constructor(public height: number) {}
  area(height: number): number {
    return this.height * height;
  }
}

export interface Solid {
  w: number;
}

export interface Solid {
  h: number;
}

export interface Shape {
  d: number;
}

export const unit: Solid = { w: 1, h: 1 };
export const cube: Shape = { d: 1 };
