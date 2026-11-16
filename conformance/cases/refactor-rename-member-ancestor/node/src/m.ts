export class Base {
  next(): number {
    return 2;
  }
}

export class C extends Base {
  old(): number {
    return 1;
  }
}
