import { f } from './kinds';

export function run(): void {
  let k: 'edit_model' | 'drop' | 'none' = 'drop';
  k = 'edit_model';
  f(k);
}
