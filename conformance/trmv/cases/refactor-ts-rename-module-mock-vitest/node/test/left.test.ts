import * as vitest from 'vitest';

vitest.vi.mock('../src/api');

export function local(): string {
  const vi = { mock: (p: string): string => p };
  return vi.mock('../src/api');
}
