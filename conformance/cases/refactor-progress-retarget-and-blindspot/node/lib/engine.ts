export class Engine {
  persistModel(): number {
    return 1;
  }

  persist(): number {
    return this.persistModel();
  }
}

export class Fast extends Engine {
  override persist(): number {
    return 2;
  }
}
