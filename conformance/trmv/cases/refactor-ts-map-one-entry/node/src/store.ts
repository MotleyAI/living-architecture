export class Store {
  getModel(name: string): number {
    return name.length;
  }

  saveModel(name: string): void {
    console.log(name);
  }
}

export function getModel(): number {
  return 0;
}
