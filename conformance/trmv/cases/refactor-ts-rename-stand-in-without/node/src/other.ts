export interface Other {
  getModel(): string;
}

export class Unrelated {
  getModel(): string {
    return '';
  }
}
