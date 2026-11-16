export class Store {
  saveModel(): void {}
}

export class Engine {
  saveModel(): void {}

  /** @deprecated */
  save(): void {
    return this.saveModel();
  }
}
