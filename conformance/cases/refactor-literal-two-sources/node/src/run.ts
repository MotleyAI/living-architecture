import { take } from './kinds';

export function run(c: boolean): void {
  const v = c ? 'edit_model' : 'drop';
  take(v);
}
