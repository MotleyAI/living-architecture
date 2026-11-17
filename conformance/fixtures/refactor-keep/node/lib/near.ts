import { Store } from './store';

export function f(store: Store): number {
  return store.load();
}

export function load(): number {
  return 0;
}
export const x = new Store().load();
