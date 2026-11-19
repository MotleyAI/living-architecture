export class Base {
  ping(): number {
    return 1;
  }
}

export class Sub extends Base {
  override ping(): number {
    return 2;
  }
}

export class Base2 {
  pong(): number {
    return 3;
  }
}

export class Sub2 extends Base2 {
  override pong(): number {
    return 4;
  }
}
