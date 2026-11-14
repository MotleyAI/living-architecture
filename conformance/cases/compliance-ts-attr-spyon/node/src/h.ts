import { vi } from 'vitest';

export function h(o: any): void {
  vi.spyOn(o, 'id');
}
