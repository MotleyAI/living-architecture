import { take } from './c';

export class K {
  static readonly FORMULA = 'formula';
}

export function viaClass(): void {
  take(K.FORMULA);
}
