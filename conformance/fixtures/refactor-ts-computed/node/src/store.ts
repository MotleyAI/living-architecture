const KEY = 'getModel';

export interface Store {
  getModel(name: string): number;
}

export class Keyed {
  [KEY](name: string): number {
    return name.length;
  }
}

export function use(s: Store): number {
  return s.getModel('a');
}
