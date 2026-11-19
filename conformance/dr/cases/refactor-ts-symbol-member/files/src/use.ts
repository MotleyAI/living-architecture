import { Store } from './store';

export function load(s: Store): number {
  return s.loadModel('m');
}
