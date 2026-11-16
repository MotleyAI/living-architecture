export class C {
  old(): number {
    return 1;
  }
}

export class Sub extends C {
  next(): number {
    return 2;
  }
}
