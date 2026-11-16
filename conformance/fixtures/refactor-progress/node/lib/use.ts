import { Store } from './store';

export function run(store: Store): number {
  return store.load() + store.drop() + store.size() + store.clear();
}
