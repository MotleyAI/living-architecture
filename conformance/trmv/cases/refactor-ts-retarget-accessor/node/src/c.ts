export class C {
  value = 1;

  /** @deprecated */
  get old(): number {
    return this.value;
  }
}
