/** The engine; see {@link Engine#persistModel} and `persistModel()`. */
export class Engine {
  /** Saves; see `persistModel`. */
  persistModel(name: string): void {
    // then saveModel runs
    throw new Error(`persistModel: ${name}`);
  }
}
