import { Storage } from './store';

export function f(s: Storage): number {
  return s.getDataset('a');
}
