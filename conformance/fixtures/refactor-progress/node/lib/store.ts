export class Store {
  load(): number {
    return 1;
  }

  drop(): number {
    return 2;
  }

  size(): number {
    return 3;
  }

  clear(): number {
    return 4;
  }

  save(): number {
    return 5;
  }
}

export class Other {
  save(): number {
    return 6;
  }
}
