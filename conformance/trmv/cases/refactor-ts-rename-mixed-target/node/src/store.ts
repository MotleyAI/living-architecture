export class A {
  saveModel(): number {
    return 1;
  }
}

export class B {
  saveModel(): number {
    return 2;
  }
}

export function read(x: A | B): unknown {
  return Reflect.get(x, 'saveModel');
}
