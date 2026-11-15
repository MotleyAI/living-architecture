export class A {
  save(): number {
    return 1;
  }
}

export class B {
  save(): number {
    return 2;
  }
}

export function use(x: any): number {
  return x.save();
}
