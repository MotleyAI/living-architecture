export class A {
  save(): number {
    return 1;
  }
}

export class Other {
  save(): number {
    return 2;
  }
}

export function use(a: A, o: Other): number {
  return a.save() + o.save();
}
