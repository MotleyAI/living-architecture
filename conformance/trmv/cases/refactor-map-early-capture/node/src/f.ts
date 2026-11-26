export class Q {
  measures(): number {
    return 1;
  }
  metrics(): number {
    return 2;
  }
}

export function f(x: number, y: number): number {
  return x - y;
}

export function g(): number {
  const a = 1;
  const b = 2;
  return a - b;
}

export const one = 1;
export const two = 2;
