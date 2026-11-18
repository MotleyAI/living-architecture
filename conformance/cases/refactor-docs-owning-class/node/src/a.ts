/** Every table lists its `columns`. */
export class Table {
  columns: string[] = [];

  /** The count of `columns`. */
  size(): number {
    return this.columns.length;
  }
}

/** Carries `columns`; a different class. */
export class Result {
  columns: string[] = [];

  describe(): string {
    return `columns of ${this.columns.length}`;
  }
}
