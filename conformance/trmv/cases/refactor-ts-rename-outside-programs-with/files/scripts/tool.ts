export function g(o: any): number {
  return o.getModel('m');
}

export class FakeStorage {
  getDataset(name: string): number {
    return name.length;
  }
}
