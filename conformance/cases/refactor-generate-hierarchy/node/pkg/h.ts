export class Base {
  measures(): number {
    return 1;
  }
}

export class Sub extends Base {
  override measures(): number {
    return 2;
  }
}
