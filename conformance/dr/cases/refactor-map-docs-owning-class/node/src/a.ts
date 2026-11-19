/** A table and its `columns`. */
export class Table {
  columns: string[] = [];

  /** The number of `columns`. */
  width(): number {
    return this.columns.length;
  }
}

/** A result and its `columns`. */
export class Result {
  columns: string[] = [];

  width(): number {
    // `columns` are counted
    return this.columns.length;
  }
}
