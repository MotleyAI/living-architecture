import { take } from './c';

export function viaLoop(): void {
  for (const t of ['formula', 'sql'] as const) {
    take(t);
  }
}
