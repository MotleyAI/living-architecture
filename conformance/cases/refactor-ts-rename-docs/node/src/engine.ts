/** The engine; see {@link Engine#saveModel} and `saveModel()`. */
export class Engine {
  /** Saves; see `saveModel`. */
  saveModel(name: string): void {
    // then saveModel runs
    throw new Error(`saveModel: ${name}`);
  }
}
